#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import boto3
from boto3.session import Session
from PyQt5.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, 
                            QHBoxLayout, QWidget, QLabel, QLineEdit, QProgressBar, 
                            QTextEdit, QFileDialog, QFrame, QMessageBox, QSystemTrayIcon,
                            QMenu, QDialog, QDateEdit, QComboBox, QListWidget, QListWidgetItem,
                            QTabWidget, QScrollArea, QGridLayout, QTextBrowser, QApplication,
                            QTableWidget, QTableWidgetItem, QHeaderView, QSpacerItem, QSizePolicy,
                            QAction)
from PyQt5.QtCore import Qt, QThread, QSettings, QDate, QTimer
from PyQt5.QtGui import QIcon

from ui.photographers_dialog import PhotographersDialog
from ui.order_selector_dialog import OrderSelectorDialog
from ui.image_preview_dialog import ImagePreviewDialog
from ui.task_editor_dialog import TaskEditorDialog
from ui.enhanced_progress_bars import EnhancedProgressBars
from utils.background_uploader import BackgroundUploader
import getmac
import uuid
import re
import mysql.connector
from mysql.connector import errorcode, pooling
from botocore.exceptions import BotoCoreError, ClientError
from utils.circuit_breaker import CircuitBreaker, circuit_breaker_decorator

class S3UploaderGUI(QMainWindow):
    """
    Main application window for S3 file uploader
    """
    def __init__(self, aws_config, db_manager, user_info, skip_state_load=False, auto_resume=False, safe_mode=False, load_all_tasks=False, no_auto_login=False):
        """
        Initialize the S3 Uploader GUI
        
        Args:
            aws_config (dict): AWS configuration loaded from secure config
            db_manager (DatabaseManager): Database manager instance
            user_info (dict): User information for current session
            skip_state_load (bool): Skip loading previous task states
            auto_resume (bool): Auto-resume tasks from saved states
            safe_mode (bool): Run in safe mode with restricted functionality
            load_all_tasks (bool): Load all tasks from database, not just today's
            no_auto_login (bool): Disable automatic login functionality
        """
        super().__init__()
        
        # Store initialization parameters
        self.aws_config = aws_config
        self.db_manager = db_manager
        self.user_info = user_info
        self.skip_state_load = skip_state_load
        self.auto_resume = auto_resume
        self.safe_mode = safe_mode
        self.load_all_tasks = load_all_tasks
        self.no_auto_login = no_auto_login
        
        # Initialize task management
        self.upload_tasks = []
        self.task_queue = []  # Queue for tasks waiting to be executed
        self.current_running_task = None  # Track the currently running task
        
        # Initialize AWS session
        self.aws_session = None
        
        # Initialize device info
        self.mac_address = self.get_mac_address()
        self.device_id = None
        self.device_name = None
        self.local_storage_path = None
        
        # Initialize UI update system
        self.pending_ui_updates = set()
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.batch_update_ui)
        self.ui_update_timer.start(1000)  # Update every second
        
        # Initialize UI
        self.init_ui()
        
        # Initialize database schema
        self.init_database_schema()
        
        # Initialize connection pool
        self.init_connection_pool()
        
        # Get device info from database
        device_info = self.db_manager.get_device_info_by_mac(self.mac_address)
        if device_info:
            self.device_id = device_info['DeviceID']
            self.device_name = device_info['DeviceName']
            # Use the correct key for storage path
            self.local_storage_path = device_info.get('storage_path') or device_info.get('StoragePath')
            print(f"Device Name: {self.device_name}")
            print(f"MAC Address: {self.mac_address}")
            print(f"Device ID: {self.device_id}")
            
            # Update device name in UI
            if hasattr(self, 'device_label'):
                self.device_label.setText(self.device_name)
        else:
            print(f"Warning: Device with MAC {self.mac_address} not found in database")
        
        # Initialize AWS session
        self.init_aws_session()
        
        # Setup system tray
        self.setup_tray()
        
        # Check for previous shutdown
        self.check_previous_shutdown()
        
        # Load tasks from database if not skipping state load
        if not skip_state_load:
            self.load_tasks_from_database()
        
        # Auto-login if not disabled
        if not no_auto_login:
            # Try to auto-login after a short delay
            QTimer.singleShot(1000, self.try_auto_login)
    
        # Initialize circuit breakers
        self.init_circuit_breakers()
    
    def init_circuit_breakers(self):
        """Initialize circuit breakers for different services"""
        self.db_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        self.aws_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    
    def check_previous_shutdown(self):
        """
        Check if the application was properly closed last time
        If not, log a warning and prepare for auto-resuming tasks
        """
        try:
            # If skip_state_load is enabled, don't auto-resume tasks regardless of previous state
            if self.skip_state_load:
                self.log_message("Skipping previous shutdown check due to state loading being disabled")
                self._auto_resume = False
                return
                
            if self.app_status_file.exists():
                with open(self.app_status_file, 'r') as f:
                    status = json.load(f)
                    
                    if status.get('state') != 'clean_shutdown':
                        # Application wasn't properly closed last time
                        last_time = status.get('timestamp', 'unknown')
                        self.log_message(f"Warning: Abnormal application shutdown detected at {last_time}")
                        self.log_message("Will attempt to automatically restore tasks...")
                        
                        # Set a flag to auto-resume tasks when loading them
                        self._auto_resume = True
                    else:
                        # Normal shutdown last time
                        self._auto_resume = False
            else:
                # First run or status file was deleted
                self._auto_resume = False
                
        except Exception as e:
            self.log_message(f"Error checking previous shutdown state: {str(e)}")
            self._auto_resume = False
            
    def update_app_status(self, state):
        """
        Update application status file
        
        Args:
            state (str): Current application state ('running', 'clean_shutdown', etc.)
        """
        try:
            status = {
                'state': state,
                'timestamp': datetime.now().isoformat(),
                'user': self.user_info.get('Emp_FullName', 'unknown'),
                'computer': os.environ.get('COMPUTERNAME', os.environ.get('HOSTNAME', 'unknown'))
            }
            
            # Use atomic write with temp file
            temp_file = self.app_status_file.with_suffix('.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
                
            # Rename for atomic update
            temp_file.replace(self.app_status_file)
            
        except Exception as e:
            self.log_message(f"Error updating application status: {str(e)}")
    
    def init_ui(self):
        """Initialize the user interface"""
        # Set default application state
        self.progress_mode = 'upload'
        self.sort_order = 'asc'
        self.sort_column = 0
        self.image_previews = []
        
        # Define app status file path
        from pathlib import Path
        self.app_status_file = Path.home() / '.aws_uploader' / 'app_status.json'
        
        # Create the status directory if it doesn't exist
        if not self.app_status_file.parent.exists():
            self.app_status_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize settings
        from PyQt5.QtCore import QSettings
        self.settings = QSettings("BALIStudios", "AWSUploader")
        
        # Load local storage path from database first, fallback to QSettings
        if self.local_storage_path is None:
            db_storage_path = self.db_manager.get_device_storage_path(self.mac_address)
            if db_storage_path:
                self.local_storage_path = db_storage_path
            else:
                # Fallback to QSettings for backward compatibility
                self.local_storage_path = self.settings.value("local_storage_path", str(Path.home() / "Documents"))
                # Save to database for future use
                if self.local_storage_path:
                    self.db_manager.update_device_storage_path(self.mac_address, self.local_storage_path)
        
        # Run initialization
        self.setWindowTitle("Secure File Uploader")
        
        # Check user authentication state
        if not self.user_info.get('is_logged_in', False):
            # Disable authenticated features on startup
            self.disable_authenticated_features()
        else:
            self.enable_authenticated_features()
        
        # Save shutdown status
        self.update_app_status("running")
        
        # Log application start
        if self.safe_mode:
            self.log_message("Running in safe mode with limited functionality")
        if self.skip_state_load:
            self.log_message("Skipping loading previous tasks and saved states")
        if self.no_auto_login:
            self.log_message("Automatic login is disabled")
        
        # Continue with the rest of UI initialization...
        # (The rest of the original init_ui code would go here)
        self.setGeometry(100, 100, 800, 450)
        
        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'Uploadicon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # Try alternative path
            icon_path = 'Uploadicon.ico'
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                print(f"Warning: Icon file not found at {icon_path}")
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # User info panel
        user_frame = QFrame()
        user_frame.setFrameShape(QFrame.StyledPanel)
        user_layout = QHBoxLayout()  # Change to horizontal layout
        
        # Display username on the left without "User:" prefix
        self.user_label = QLabel(f"{self.user_info.get('Emp_FullName', 'Guest')}")
        self.user_label.setStyleSheet("font-weight: bold;")
        user_layout.addWidget(self.user_label)
        
        # Add spacer to push device name to the right
        user_layout.addStretch()
        
        # Display device name on the right without "Device:" prefix
        self.device_label = QLabel(f"{self.device_name or 'Unknown'}")
        self.device_label.setStyleSheet("font-weight: bold;")
        user_layout.addWidget(self.device_label)
        
        user_frame.setLayout(user_layout)
        layout.addWidget(user_frame)
        
        # Add login/logout button in a separate frame below
        login_frame = QFrame()
        login_layout = QHBoxLayout()
        
        self.login_button = QPushButton("Logout" if self.user_info.get('is_logged_in', False) else "Login")
        self.login_button.clicked.connect(self.toggle_login)
        login_layout.addWidget(self.login_button)
        
        login_frame.setLayout(login_layout)
        layout.addWidget(login_frame)
        
        
        
        # Tab widget for different functions
        self.tabs = QTabWidget()
        
        # Upload tab
        upload_tab = QWidget()
        upload_layout = QVBoxLayout()
        
        # Add big Upload Photoshoot button in place of removed task details
        upload_photoshoot_frame = QFrame()
        upload_photoshoot_layout = QVBoxLayout()
        
        self.upload_photoshoot_btn = QPushButton('Upload Photoshoot')
        self.upload_photoshoot_btn.setMinimumHeight(50)  # Make button bigger
        self.upload_photoshoot_btn.setStyleSheet("font-size: 14pt;")  # Larger font
        self.upload_photoshoot_btn.clicked.connect(self.add_photoshoot_task)
        
        upload_photoshoot_layout.addWidget(self.upload_photoshoot_btn)
        upload_photoshoot_frame.setLayout(upload_photoshoot_layout)
        upload_layout.addWidget(upload_photoshoot_frame)
        
        # Task list for multiple uploads
        task_list_label = QLabel("Upload Tasks:")
        task_list_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        upload_layout.addWidget(task_list_label)
        
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(200)  # توازن أفضل بين القوائم
        self.task_list.itemSelectionChanged.connect(self.on_task_selected)
        self.task_list.itemDoubleClicked.connect(self.on_task_double_clicked)
        upload_layout.addWidget(self.task_list)
        
        # إضافة مسافة رأسية بين قائمة المهام وقائمة اللوج
        upload_layout.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Fixed))
        
        # Enhanced Progress Bars
        self.enhanced_progress_bars = EnhancedProgressBars()
        
        button_layout = QHBoxLayout()
        
        # Remove toggle progress mode button and permanently set to upload mode
        self.progress_mode = 'upload'  # Always show upload progress
        
        # Use Modify Task button in place of Add Upload Task
        self.modify_task_btn = QPushButton('Modify Task')
        self.modify_task_btn.clicked.connect(self.modify_selected_task)
        self.modify_task_btn.setEnabled(False)
        
        button_layout.addWidget(self.modify_task_btn)
        
        self.pause_btn = QPushButton('Pause')
        self.pause_btn.clicked.connect(self.pause_selected_task)
        self.pause_btn.setEnabled(False)
        button_layout.addWidget(self.pause_btn)
        
        self.resume_btn = QPushButton('Resume')
        self.resume_btn.clicked.connect(self.resume_selected_task)
        self.resume_btn.setEnabled(False)
        button_layout.addWidget(self.resume_btn)
        
        self.restart_btn = QPushButton('Restart')
        self.restart_btn.clicked.connect(self.restart_selected_task)
        self.restart_btn.setEnabled(False)
        button_layout.addWidget(self.restart_btn)
        
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.clicked.connect(self.cancel_selected_task)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)
        
        self.delete_btn = QPushButton('Delete')
        self.delete_btn.clicked.connect(self.delete_selected_task)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)
        
        upload_layout.addLayout(button_layout)
        upload_layout.addWidget(self.enhanced_progress_bars)
        
        # Log area with smaller height
        log_label = QLabel("Log:")
        log_label.setStyleSheet("font-weight: bold;")
        upload_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(140)
        self.log_text.setMaximumHeight(160)
        upload_layout.addWidget(self.log_text)
        
        upload_tab.setLayout(upload_layout)
        
        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout()
        
        # Add filter controls
        filter_frame = QFrame()
        filter_layout = QHBoxLayout()
        
        # Date range filter
        filter_layout.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.from_date)
        
        filter_layout.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.to_date)
        
        # Order number filter
        filter_layout.addWidget(QLabel("Order #:"))
        self.order_filter = QLineEdit()
        filter_layout.addWidget(self.order_filter)
        
        # Apply filter button
        apply_filter_btn = QPushButton('Apply Filter')
        apply_filter_btn.clicked.connect(self.apply_history_filter)
        filter_layout.addWidget(apply_filter_btn)
        
        # Reset filter button
        reset_filter_btn = QPushButton('Show Today')
        reset_filter_btn.clicked.connect(self.reset_history_filter)
        filter_layout.addWidget(reset_filter_btn)
        
        filter_frame.setLayout(filter_layout)
        history_layout.addWidget(filter_frame)
        
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.show_order_details)
        
        history_layout.addWidget(QLabel("Upload History:"))
        history_layout.addWidget(self.history_list)
        
        self.upload_details = QTextBrowser()
        self.upload_details.setReadOnly(True)
        history_layout.addWidget(QLabel("Upload Details:"))
        history_layout.addWidget(self.upload_details)
        
        history_tab.setLayout(history_layout)
        
        # Activity Log tab
        activity_tab = QWidget()
        activity_layout = QVBoxLayout()
        
        # Add filter controls for activity log
        activity_filter_frame = QFrame()
        activity_filter_layout = QHBoxLayout()
        
        # Date range filter
        activity_filter_layout.addWidget(QLabel("From:"))
        self.log_from_date = QDateEdit()
        self.log_from_date.setCalendarPopup(True)
        self.log_from_date.setDate(QDate.currentDate())
        activity_filter_layout.addWidget(self.log_from_date)
        
        activity_filter_layout.addWidget(QLabel("To:"))
        self.log_to_date = QDateEdit()
        self.log_to_date.setCalendarPopup(True)
        self.log_to_date.setDate(QDate.currentDate())
        activity_filter_layout.addWidget(self.log_to_date)
        
        # User filter
        activity_filter_layout.addWidget(QLabel("User:"))
        self.user_filter = QLineEdit()
        activity_filter_layout.addWidget(self.user_filter)
        
        # Activity type filter
        activity_filter_layout.addWidget(QLabel("Activity:"))
        self.activity_type_filter = QComboBox()
        self.activity_type_filter.addItems(["All", "Login/Logout", "Upload", "Task Management", "System"])
        activity_filter_layout.addWidget(self.activity_type_filter)
        
        # Apply filter button
        apply_log_filter_btn = QPushButton('Apply Filter')
        apply_log_filter_btn.clicked.connect(self.apply_activity_filter)
        activity_filter_layout.addWidget(apply_log_filter_btn)
        
        # Reset filter button
        reset_log_filter_btn = QPushButton('Show Today')
        reset_log_filter_btn.clicked.connect(self.reset_activity_filter)
        activity_filter_layout.addWidget(reset_log_filter_btn)
        
        activity_filter_frame.setLayout(activity_filter_layout)
        activity_layout.addWidget(activity_filter_frame)
        
        # Activity log table
        self.activity_table = QTableWidget()
        self.activity_table.setColumnCount(5)
        self.activity_table.setHorizontalHeaderLabels(["Timestamp", "User", "Activity", "Details", "IP/Device"])
        self.activity_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.activity_table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.activity_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        activity_layout.addWidget(self.activity_table)
        
        activity_tab.setLayout(activity_layout)
        
        # Storage tab
        storage_tab = QWidget()
        storage_layout = QVBoxLayout()
        
        # Storage settings section
        storage_settings_frame = QFrame()
        storage_settings_frame.setFrameShape(QFrame.StyledPanel)
        storage_settings_layout = QVBoxLayout()
        
        # Title
        storage_title = QLabel("Local Storage Settings")
        storage_title.setStyleSheet("font-weight: bold; font-size: 14pt; margin-bottom: 10px;")
        storage_settings_layout.addWidget(storage_title)
        
        # Current path display
        current_path_label = QLabel("Current Local Storage Path:")
        current_path_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        storage_settings_layout.addWidget(current_path_label)
        
        # Get current storage path from database
        current_storage_path = self.db_manager.get_device_storage_path(self.mac_address)
        if not current_storage_path:
            # Fallback to QSettings if not in database
            from PyQt5.QtCore import QSettings
            settings = QSettings('AWSUploader', 'Settings')
            current_storage_path = settings.value('local_storage_path', 'Not set')
        
        self.current_storage_label = QLabel(current_storage_path or "Not set")
        self.current_storage_label.setStyleSheet("color: #666; padding: 10px; background-color: #f0f0f0; border-radius: 5px; margin-bottom: 15px;")
        self.current_storage_label.setWordWrap(True)
        storage_settings_layout.addWidget(self.current_storage_label)
        
        # Change storage path button
        change_storage_btn = QPushButton("Change Storage Location")
        change_storage_btn.clicked.connect(self.open_settings)
        change_storage_btn.setStyleSheet("QPushButton { padding: 10px; font-size: 12pt; background-color: #4CAF50; color: white; font-weight: bold; }")
        storage_settings_layout.addWidget(change_storage_btn)
        
        # Add some spacing
        storage_settings_layout.addStretch()
        
        storage_settings_frame.setLayout(storage_settings_layout)
        storage_layout.addWidget(storage_settings_frame)
        
        # Add stretch to push everything to the top
        storage_layout.addStretch()
        
        storage_tab.setLayout(storage_layout)
        
        # Add tabs to tab widget
        self.tabs.addTab(upload_tab, "Upload Files")
        self.tabs.addTab(history_tab, "Upload History")
        self.tabs.addTab(activity_tab, "Activity Log")
        self.tabs.addTab(storage_tab, "Storage")
        
        layout.addWidget(self.tabs)
        
        main_widget.setLayout(layout)
        
        # Initialize history
        self.load_upload_history()
        
        # Initialize activity log
        self.load_activity_log()
        
        # Display any pending log messages that were stored before log_text was created
        if hasattr(self, '_pending_log_messages') and self._pending_log_messages:
            for message in self._pending_log_messages:
                self.log_text.append(message)
            self._pending_log_messages = []
    
    def toggle_login(self):
        """
        Handle login/logout button click
        """
        if self.user_info.get('is_logged_in', False):
            # User is logged in, handle logout
            reply = QMessageBox.question(
                self,
                "Confirm Logout",
                "Are you sure you want to logout?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Log the logout action
                self.log_message("Logged out")
                self.log_activity("auth", "logout", f"User {self.user_info['Emp_FullName']} logged out")
                
                # Update user info
                self.user_info['is_logged_in'] = False
                
                # Update UI
                self.login_button.setText("Login")
                self.user_label.setText("User: Guest")
                
                # Disable sensitive operations
                self.disable_authenticated_features()
        else:
            # User is not logged in, show login dialog
            from ui.login_dialog import LoginDialog
            login_dialog = LoginDialog(self.db_manager, parent=self)
            
            if login_dialog.exec_() == QDialog.Accepted:
                # Get user info from dialog
                user_credentials = login_dialog.get_user_credentials()
                
                # Authenticate user (this would normally check against a database)
                if self.authenticate_user(user_credentials['username'], user_credentials['password']):
                    # Update user info
                    self.user_info['is_logged_in'] = True
                    
                    # Update UI
                    self.login_button.setText("Logout")
                    self.user_label.setText(f"User: {self.user_info['Emp_FullName']}")
                    
                    # Log the login
                    self.log_message(f"Logged in as {self.user_info['Emp_FullName']}")
                    self.log_activity("auth", "login", f"User {self.user_info['Emp_FullName']} logged in")
                    
                    # Enable sensitive operations
                    self.enable_authenticated_features()
                else:
                    QMessageBox.warning(self, "Error", "Login failed. Please check username and password.")
                    self.log_activity("auth", "login_failed", f"Failed login attempt for user {user_credentials['username']}")
    
    def authenticate_user(self, username, password):
        """
        Authenticate user credentials
        
        Args:
            username (str): Username
            password (str): Password
            
        Returns:
            bool: True if authentication succeeded
        """
        try:
            # Print debug info
            self.log_message(f"Login attempt: username = {username}")
            
            # In a real application, you would check these credentials against your database
            # For this example, we'll just check against the current user_info or a simple check
            if hasattr(self.db_manager, 'authenticate'):
                # If the db_manager has an authenticate method, use it
                self.log_message("Using authentication method from database manager")
                result = self.db_manager.authenticate(username, password)
                if result and isinstance(result, dict):
                    # Update user_info with returned data
                    self.user_info.update(result)
                    self.log_message(f"Authentication successful for user: {result.get('Emp_FullName', 'unknown')}")
                    return True
                else:
                    self.log_message("Authentication failed: invalid credentials")
                    return False
            else:
                # Fallback simple authentication - for demo purposes
                # In a real app, NEVER do this - always check against secure database
                # This is ONLY for demonstration
                self.log_message("Fallback authentication method: demo only")
                if username == self.user_info.get('username', 'admin') and password == "password":
                    self.log_message("Authentication successful using alternative method")
                    return True
                self.log_message("Authentication failed: invalid credentials")
                return False
        except Exception as e:
            self.log_message(f"Error during authentication attempt: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return False
    
    def ensure_user_logged_in(self):
        """
        Ensure the user is logged in, either by checking current authentication state 
        or by prompting for login.
        
        Returns:
            bool: True if user is or becomes authenticated, False otherwise
        """
        # If already logged in, just return True
        if self.user_info.get('is_logged_in', False):
            return True
            
        # Show authentication dialog
        from PyQt5.QtWidgets import QMessageBox, QDialog
        
        # If auto-login is disabled, only show manual login dialog
        if self.no_auto_login:
            reply = QMessageBox.Yes
        else:
            # Ask if user wants to login
            reply = QMessageBox.question(
                self, 
                "Authentication Required", 
                "You need to be logged in to perform this action. Would you like to log in now?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.Yes
            )
        
        if reply == QMessageBox.Yes:
            # Show login dialog
            from ui.login_dialog import LoginDialog
            login_dialog = LoginDialog(self.db_manager, parent=self)
            
            if login_dialog.exec_() == QDialog.Accepted:
                # Get user info from dialog
                user_credentials = login_dialog.get_user_credentials()
                
                # Authenticate user
                if self.authenticate_user(user_credentials['username'], user_credentials['password']):
                    # Update user info
                    self.user_info['is_logged_in'] = True
                    
                    # Update UI
                    self.login_button.setText("Logout")
                    self.user_label.setText(f"User: {self.user_info['Emp_FullName']}")
                    
                    # Log the login
                    self.log_message(f"Logged in as {self.user_info['Emp_FullName']}")
                    self.log_activity("auth", "login", f"User {self.user_info['Emp_FullName']} logged in")
                    
                    # Enable sensitive operations
                    self.enable_authenticated_features()
                    
                    return True
                else:
                    QMessageBox.warning(self, "Error", "Login failed. Please check your username and password.")
                    self.log_activity("auth", "login_failed", f"Failed login attempt for user {user_credentials['username']}")
        
        return False
    
    def disable_authenticated_features(self):
        """Disable features that require authentication"""
        # Disable buttons that require authentication (check if they exist first)
        if hasattr(self, 'upload_photoshoot_btn'):
            self.upload_photoshoot_btn.setEnabled(False)
        
        # These still need authentication
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.setEnabled(False)
        if hasattr(self, 'delete_btn'):
            self.delete_btn.setEnabled(False)
        if hasattr(self, 'modify_task_btn'):
            self.modify_task_btn.setEnabled(False)
    
    def enable_authenticated_features(self):
        """Enable features that require authentication"""
        # Enable buttons that may be used after authentication (check if they exist first)
        if hasattr(self, 'upload_photoshoot_btn'):
            self.upload_photoshoot_btn.setEnabled(True)
        
        # The other buttons depend on task selection state,
        # so we'll update them based on the current selection
        if hasattr(self, 'on_task_selected'):
            self.on_task_selected()
    
    def log_activity(self, category, action, details, user=None):
        """
        Log an activity to the database
        
        Args:
            category (str): Activity category (auth, task, system, etc.)
            action (str): Specific action taken
            details (str): Additional details about the activity
            user (str, optional): Username. If None, current user is used.
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            # Get current user if not specified
            if user is None:
                user = self.user_info.get('Emp_FullName', 'Unknown')
                
            # Get device info
            import getmac
            import socket
            device_id = getmac.get_mac_address()
            try:
                ip_address = socket.gethostbyname(socket.gethostname())
            except:
                ip_address = "Unknown"
                
            # Check if activity_log table exists
            cursor = self.db_manager.connection.cursor()
            
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'activity_log'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] == 0:
                # Table doesn't exist, create it
                self.log_message("Activity log table doesn't exist, creating it...")
                
                create_table_query = """
                CREATE TABLE activity_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    username VARCHAR(100) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    details TEXT,
                    ip_address VARCHAR(50),
                    device_id VARCHAR(100),
                    emp_id INT NULL,
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_username (username),
                    INDEX idx_category (category),
                    INDEX idx_action (action),
                    INDEX idx_emp_id (emp_id)
                )
                """
                cursor.execute(create_table_query)
                self.db_manager.connection.commit()
                
            # Add employee ID column if needed
            cursor.execute("""
            SELECT COUNT(*) as column_exists
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = 'activity_log'
            AND column_name = 'emp_id'
            """, (self.db_manager.rds_config['database'],))
            
            has_emp_id = cursor.fetchone()[0] > 0
            
            if not has_emp_id:
                alter_query = """
                ALTER TABLE activity_log
                ADD COLUMN emp_id INT NULL,
                ADD INDEX idx_emp_id (emp_id)
                """
                cursor.execute(alter_query)
                self.db_manager.connection.commit()
                self.log_message("Added emp_id column to activity_log table")
            
            # Get employee ID from user info if available
            emp_id = self.user_info.get('Emp_ID') if hasattr(self, 'user_info') and self.user_info else None
            
            # Insert the activity log
            query = """
            INSERT INTO activity_log
            (username, category, action, details, ip_address, device_id, emp_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (user, category, action, details, ip_address, device_id, emp_id)
            cursor.execute(query, values)
            self.db_manager.connection.commit()
            
            # Print to console for debugging
            print(f"[ACTIVITY] {user} ({category}/{action}): {details}")
            
        except Exception as e:
            self.log_message(f"Error logging activity: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def load_activity_log(self, from_date=None, to_date=None, username=None, activity_type=None):
        """
        Load activity log data into the activity table
        
        Args:
            from_date (str, optional): Start date filter (YYYY-MM-DD)
            to_date (str, optional): End date filter (YYYY-MM-DD)
            username (str, optional): Filter by username
            activity_type (str, optional): Filter by activity category
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            # Check if activity_log table exists
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'activity_log'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result['table_exists'] == 0:
                # Table doesn't exist yet
                self.activity_table.setRowCount(0)
                return
            
            # Build query with filters
            query = """
            SELECT timestamp, username, category, action, details, ip_address, device_id
            FROM activity_log
            WHERE 1=1
            """
            
            params = []
            
            if from_date:
                query += " AND DATE(timestamp) >= %s"
                params.append(from_date)
                
            if to_date:
                query += " AND DATE(timestamp) <= %s"
                params.append(to_date)
                
            if username:
                query += " AND username LIKE %s"
                params.append(f"%{username}%")
                
            if activity_type and activity_type != "All":
                # Map selection to categories
                category_map = {
                    "Login/Logout": "auth",
                    "Upload": "upload",
                    "Task Management": "task",
                    "System": "system"
                }
                if activity_type in category_map:
                    query += " AND category = %s"
                    params.append(category_map[activity_type])
            
            # Add order by
            query += " ORDER BY timestamp DESC LIMIT 1000"
            
            # Execute query
            cursor.execute(query, params)
            logs = cursor.fetchall()
            
            # Clear the table
            self.activity_table.setRowCount(0)
            
            # Fill table with data
            self.activity_table.setRowCount(len(logs))
            
            for row, log in enumerate(logs):
                self.activity_table.setItem(row, 0, QTableWidgetItem(str(log['timestamp'])))
                self.activity_table.setItem(row, 1, QTableWidgetItem(log['username']))
                self.activity_table.setItem(row, 2, QTableWidgetItem(f"{log['category']} - {log['action']}"))
                self.activity_table.setItem(row, 3, QTableWidgetItem(log['details']))
                self.activity_table.setItem(row, 4, QTableWidgetItem(f"{log['ip_address']} / {log['device_id']}"))
            
            # Resize rows to content
            self.activity_table.resizeRowsToContents()
            
        except Exception as e:
            self.log_message(f"Error loading activity log: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            
    def apply_activity_filter(self):
        """Apply filters to the activity log"""
        from_date = self.log_from_date.date().toString("yyyy-MM-dd")
        to_date = self.log_to_date.date().toString("yyyy-MM-dd")
        username = self.user_filter.text()
        activity_type = self.activity_type_filter.currentText()
        
        self.load_activity_log(from_date, to_date, username, activity_type)
        
    def reset_activity_filter(self):
        """Reset activity log filters to show today's activities"""
        today = QDate.currentDate()
        self.log_from_date.setDate(today)
        self.log_to_date.setDate(today)
        self.user_filter.clear()
        self.activity_type_filter.setCurrentIndex(0)  # All
        
        self.load_activity_log(today.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd"))
    
    def setup_tray(self):
        """Setup system tray icon and menu"""
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'Uploadicon.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            # Try alternative path
            icon_path = 'Uploadicon.ico'
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                print(f"Warning: Icon file not found at {icon_path}")
        
        # Create tray menu
        tray_menu = QMenu()
        
        # Show/Hide action
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)
        
        # Add separator
        tray_menu.addSeparator()
        
        # Upload status action (informational)
        running_tasks = len([t for t in self.upload_tasks if t.get('status') == 'running'])
        if running_tasks > 0:
            status_action = QAction(f"🔄 {running_tasks} uploads running", self)
            status_action.setEnabled(False)  # Make it non-clickable
        else:
            status_action = QAction("✅ No active uploads", self)
            status_action.setEnabled(False)  # Make it non-clickable
        
        # Add separator
        tray_menu.addSeparator()
        
        # Exit action
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # Connect double-click to show window
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # Show the tray icon
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip("AWS File Uploader")
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation (clicks)"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single click on some systems
            self.show_from_tray()
    
    def log_message(self, message):
        """Show only file upload/skipped and error messages in the log area, newest on top"""
        # فلترة الرسائل
        msg_lower = message.lower()
        show = (
            'uploaded' in msg_lower or
            'uploading' in msg_lower or
            'skipped' in msg_lower or
            'error' in msg_lower
        )
        if not show:
            return
        print(message)
        if hasattr(self, 'log_text'):
            current = self.log_text.toPlainText()
            if current:
                self.log_text.setPlainText(f"{message}\n" + current)
            else:
                self.log_text.setPlainText(message)
        else:
            if not hasattr(self, '_pending_log_messages'):
                self._pending_log_messages = []
            self._pending_log_messages.insert(0, message)
    
    def browse_local_storage(self):
        """Browse for local storage location and save to database"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Local Storage Location')
        if folder:
            # Update local variable
            self.local_storage_path = folder
            # Save to database
            if self.db_manager.update_device_storage_path(self.mac_address, folder):
                self.log_message(f"Local storage path updated to: {folder}")
            else:
                self.log_message("Warning: Failed to save storage path to database")
    
    def open_settings(self):
        """Open settings dialog"""
        try:
            # Get current storage path from database
            current_path = self.db_manager.get_device_storage_path(self.mac_address)
            if not current_path:
                # Fallback to QSettings if not in database
                from PyQt5.QtCore import QSettings
                settings = QSettings('AWSUploader', 'Settings')
                current_path = settings.value('local_storage_path', None)
            
            from ui.settings_dialog import SettingsDialog
            dialog = SettingsDialog(self.db_manager, self.mac_address, current_path, self)
            
            if dialog.exec_() == dialog.Accepted:
                new_path = dialog.get_new_path()
                if new_path:
                    # Update the display in Storage tab
                    if hasattr(self, 'current_storage_label'):
                        self.current_storage_label.setText(new_path)
                    self.log_message(f"Storage path updated to: {new_path}")
                    
        except Exception as e:
            self.log_message(f"Error opening settings: {str(e)}")
            print(f"Settings error: {e}")
    
    def add_photoshoot_task(self):
        """Open dialog for adding a new photoshoot upload task"""
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        # Get current storage path from database
        current_storage_path = self.db_manager.get_device_storage_path(self.mac_address)
        if not current_storage_path:
            # Fallback to QSettings if not in database
            from PyQt5.QtCore import QSettings
            settings = QSettings('AWSUploader', 'Settings')
            current_storage_path = settings.value('local_storage_path', None)
        
        if not current_storage_path:
            QMessageBox.warning(self, "Warning", "Please configure local storage location first in the Storage tab")
            return
        
        # Update local variable
        self.local_storage_path = current_storage_path
        
        dialog = TaskEditorDialog(self.db_manager, self.local_storage_path, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            # Get task data from dialog
            task_data = dialog.get_task_data()
            
            # Create a unique task ID
            task_id = len(self.upload_tasks) + 1
            
            # Create a task item for the list
            task_item = QListWidgetItem()
            task_item.setText(f"Task {task_id}: Order {task_data['order_number']} - Pending")
            
            # Store only the task ID directly
            task_item.setData(Qt.ItemDataRole.UserRole, task_id)
            
            # Add to the list widget
            self.task_list.addItem(task_item)
            
            # Create task dictionary
            task = {
                'id': task_id,
                'item': task_item,
                'order_number': task_data['order_number'],
                'order_date': task_data['order_date'],
                'folder_path': task_data['folder_path'],
                'photographers': task_data['photographers'],
                'uploader': None,
                'status': 'pending',
                'progress': 0,
                'local_path': task_data['local_path'],
                'device_id': self.device_id,
            }
            
            # Save task to database
            db_id = self.save_task_to_database(task)
            if db_id:
                task['db_id'] = db_id
            
            # Store the task data
            self.upload_tasks.append(task)
            
            # Enable the start all button if we have tasks
            # self.start_all_btn.setEnabled(len(self.upload_tasks) > 0)
            
            self.log_message(f"Added new photoshoot task {task_id} for order {task_data['order_number']}")
            self.log_message(f"Local path: {task_data['local_path']}")
            
            # Add task to queue for sequential execution instead of starting immediately
            self.add_task_to_queue(task)
            self.log_message(f"Task {task_id} added to queue")
            
            # Show tray notification for new task
            self.tray_icon.showMessage(
                "📤 New Upload Started",
                f"Started uploading Order {task_data['order_number']}",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
    
    def modify_selected_task(self):
        """Open dialog for modifying the selected task"""
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Information", "No task selected")
            return
        
        task_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        # Check if task_data is a dictionary or a direct task_id
        if isinstance(task_data, dict):
            task_id = task_data['id']
        else:
            # If task_data is the task_id directly
            task_id = task_data
        
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            self.log_message(f"Error: Could not find task with ID {task_id}")
            return
        
        # Check if task is running or paused
        if task['status'] in ['running', 'paused']:
            reply = QMessageBox.question(
                self, 
                "Modify Running Task", 
                "This task is currently active. Do you want to stop it before modifying?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                # Stop the task first
                if task.get('uploader'):
                    task['uploader'].stop()
                task['status'] = 'pending'
                task['progress'] = 0
                
                # Update the list item if it exists
                if 'item' in task and task['item']:
                    task['item'].setText(f"Task {task_id}: Order {task['order_number']} - Pending")
        
        # Open the task editor dialog
        dialog = TaskEditorDialog(self.db_manager, self.local_storage_path, task_data=task, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            # Get updated task data
            updated_data = dialog.get_task_data()
            
            # Update the task
            task['order_number'] = updated_data['order_number']
            task['order_date'] = updated_data['order_date']
            task['folder_path'] = updated_data['folder_path']
            task['photographers'] = updated_data['photographers']
            task['local_path'] = updated_data['local_path']
            
            # Update the list item if it exists
            if 'item' in task and task['item']:
                task['item'].setText(f"Task {task['id']}: Order {updated_data['order_number']} - {task['status'].capitalize()}")
                
                # Store only the task ID directly
                task['item'].setData(Qt.ItemDataRole.UserRole, task['id'])
            
            self.log_message(f"Modified task {task_id} for order {updated_data['order_number']}")
    
    def on_task_selected(self):
        """Handle task selection to enable/disable appropriate buttons"""
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            # Disable all task-related buttons if no task is selected
            self.cancel_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.modify_task_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        
        # Get the selected task
        task_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Check if task_data is a dictionary or a direct task_id
        if isinstance(task_data, dict):
            task_id = task_data['id']
        else:
            # If task_data is the task_id directly
            task_id = task_data
        
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            self.log_message(f"Error: Could not find task with ID {task_id}")
            return
        
        # Enable modify and delete buttons only when logged in
        if self.user_info.get('is_logged_in', False):
            self.modify_task_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
        else:
            self.modify_task_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
        
        # Enable/disable buttons based on task status
        if task['status'] == 'running':
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
        elif task['status'] == 'paused':
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.restart_btn.setEnabled(True)
        elif task['status'] in ['completed', 'failed', 'cancelled']:
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
        else:  # pending
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
    
    def on_task_double_clicked(self, item):
        """Handle double-click on task item to open folder"""
        try:
            # Get the selected task
            task_data = item.data(Qt.ItemDataRole.UserRole)
            
            # Check if task_data is a dictionary or a direct task_id
            if isinstance(task_data, dict):
                task_id = task_data['id']
            else:
                # If task_data is the task_id directly
                task_id = task_data
            
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            
            if not task:
                self.log_message(f"Error: Could not find task with ID {task_id}")
                return
            
            # Get the folder path
            folder_path = task.get('folder_path', '')
            if not folder_path:
                QMessageBox.warning(self, "Warning", "No folder path found for this task")
                return
            
            # Check if folder exists
            if not os.path.exists(folder_path):
                QMessageBox.warning(self, "Warning", f"Folder does not exist:\n{folder_path}")
                return
            
            # Open folder based on operating system
            self.open_folder_in_explorer(folder_path)
            self.log_message(f"Opened folder for task {task_id}: {folder_path}")
            
        except Exception as e:
            self.log_message(f"Error opening folder: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to open folder: {str(e)}")
    
    def open_folder_in_explorer(self, folder_path):
        """
        Open folder in the default file explorer based on operating system
        
        Args:
            folder_path (str): Path to the folder to open
        """
        try:
            import sys
            import subprocess
            
            if sys.platform == 'win32':
                # Windows
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                # macOS
                subprocess.Popen(['open', folder_path])
            else:
                # Linux and other Unix-like systems
                subprocess.Popen(['xdg-open', folder_path])
                
        except Exception as e:
            raise Exception(f"Failed to open folder: {str(e)}")
    
    def start_all_tasks(self):
        """Start all pending upload tasks sequentially"""
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        pending_tasks = [task for task in self.upload_tasks if task['status'] == 'pending']
        
        if not pending_tasks:
            QMessageBox.information(self, "Information", "No pending tasks to start")
            return
        
        # Start only the first pending task
        if pending_tasks:
            self.start_task(pending_tasks[0])
        
        self.cancel_btn.setEnabled(True)
    
    def start_task(self, task):
        """
        Start a specific upload task (adds to queue for sequential execution)
        """
        try:
            if not task:
                return
            
            # Check if user is logged in first
            if not self.ensure_user_logged_in():
                return
            
            # Check if task is already running or in queue
            if task.get('status') == 'running':
                self.log_message(f"Task {task['id']} is already running")
                return
            
            if task in self.task_queue:
                self.log_message(f"Task {task['id']} is already in queue")
                return
            
            # Set task status to pending (queued)
            task['status'] = 'pending'
            self.update_task_list(task)
            
            # Add task to queue for sequential execution
            self.add_task_to_queue(task)
            
        except Exception as e:
            self.log_message(f"Error queuing task: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def update_task_progress(self, task_id, current, total):
        """Add task to pending updates instead of immediate update"""
        try:
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                return
            
            # Update progress
            if total > 0:
                task['progress'] = int((current / total) * 100)
            
            # Add to pending updates
            self.pending_ui_updates.add(task_id)
            
        except Exception as e:
            self.log_message(f"Error updating task progress: {str(e)}")

    def update_task_list(self, task):
        """Add task to pending updates instead of immediate update"""
        self.pending_ui_updates.add(task['id'])

    def update_task_list_internal(self, task):
        """Internal method to update task list item"""
        try:
            if 'item' not in task or not task['item']:
                return
                
            # Update task item text
            status_text = {
                'pending': '⏳',
                'running': '▶️',
                'paused': '⏸️',
                'completed': '✅',
                'cancelled': '❌'
            }.get(task['status'], '❓')
            
            progress = task.get('progress', 0)
            task['item'].setText(
                f"{status_text} Task {task['id']}: Order {task['order_number']} - {progress}%"
            )
            
        except Exception as e:
            self.log_message(f"Error updating task list item: {str(e)}")

    def update_all_progress_bars(self):
        """Update all progress bars with current task information"""
        # Count tasks by status
        completed_tasks = len([t for t in self.upload_tasks if t['status'] == 'completed'])
        total_tasks = len(self.upload_tasks)
        running_tasks = [t for t in self.upload_tasks if t['status'] == 'running']
        
        # Update all tasks progress bar
        self.enhanced_progress_bars.update_all_tasks_progress(completed_tasks, total_tasks)
        
        # Update current task progress bar
        if running_tasks:
            current_task = running_tasks[0]  # Show first running task
            self.enhanced_progress_bars.update_task_progress(
                current_task['id'], 
                current_task['order_number'], 
                current_task.get('progress', 0)
            )
        else:
            # No running tasks, clear current task progress
            self.enhanced_progress_bars.task_progress_bar.setValue(0)
            self.enhanced_progress_bars.task_progress_bar.setFormat("📋 Current Task: No task running")
        
        # Show or hide progress bars based on activity
        if total_tasks > 0 and (running_tasks or completed_tasks > 0):
            self.enhanced_progress_bars.show_progress_bars()
        else:
            self.enhanced_progress_bars.hide_progress_bars()
    
    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.1f} GB"
    
    def log_task_message(self, task_id, message):
        """
        Log a message for a specific task
        
        Args:
            task_id (int): Task ID
            message (str): Message to log
        """
        self.log_message(f"Task {task_id}: {message}")
    
    def task_finished(self, task_id):
        """Called when a task finishes execution"""
        try:
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                return
            
            # Update task status
            task['status'] = 'completed'
            task['progress'] = 100
            
            # Update UI
            self.update_task_list(task)
            self.update_buttons_state()
            
            # Clean up completed tasks periodically
            self.cleanup_completed_tasks()
            
            # Process next task
            self.task_execution_finished(task)
            
        except Exception as e:
            self.log_message(f"Error in task_finished: {str(e)}")
    
    def cleanup_completed_tasks(self):
        """Clean up old completed tasks to free memory"""
        try:
            from datetime import datetime, timedelta
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            # احتفظ بالمهام الحديثة فقط
            active_tasks = []
            for task in self.upload_tasks:
                if (task['status'] in ['running', 'paused', 'pending'] or 
                    task.get('created_at', datetime.now()) > cutoff_time):
                    active_tasks.append(task)
                else:
                    # تنظيف الخيط إن وجد
                    self.cleanup_task_thread(task)
            
            removed_count = len(self.upload_tasks) - len(active_tasks)
            if removed_count > 0:
                self.upload_tasks = active_tasks
                self.log_message(f"Cleaned up {removed_count} old completed tasks")
                
        except Exception as e:
            self.log_message(f"Error cleaning up tasks: {str(e)}")
    
    def all_tasks_finished(self):
        """Handle completion of all tasks"""
        self.enhanced_progress_bars.clear_all_progress()
        self.cancel_btn.setEnabled(False)
        self.log_message("All upload tasks completed")
        
        # Show enhanced tray notification
        completed_count = len([t for t in self.upload_tasks if t['status'] == 'completed'])
        self.tray_icon.showMessage(
            "🎉 All Uploads Complete!",
            f"Successfully completed {completed_count} upload tasks",
            QSystemTrayIcon.MessageIcon.Information,
            5000
        )
        
        # Update tray menu
        self.update_tray_menu()
    
    def pause_selected_task(self):
        """
        Pause the selected upload task
        """
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            self.log_message("No task selected")
            return
        
        if task['status'] != 'running':
            self.log_message(f"Task {task_id} is not running, cannot pause")
            return
        
        if not task.get('uploader') or not task['uploader'].isRunning():
            self.log_message(f"Task {task_id} has no active uploader")
            return
        
        # Pause the uploader
        self.log_message(f"Pausing task for Order {task['order_number']}")
        task['uploader'].pause()
        
        # Update task status
        task['status'] = 'paused'
        task['last_action_by'] = self.user_info.get('Emp_FullName', 'Unknown')
        self.update_task_list(task)
        
        # Log the action
        self.log_activity("task", "pause", 
                         f"Paused upload task for order {task['order_number']}", 
                         self.user_info.get('Emp_FullName'))
        
        # Update buttons
        self.update_buttons_state()
        
        # Update system tray menu
        self.update_tray_menu()

    def resume_selected_task(self):
        """
        Resume the selected upload task
        """
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            self.log_message("No task selected")
            return
        
        if task['status'] != 'paused':
            self.log_message(f"Task {task_id} is not paused, cannot resume")
            return
        
        # If task has a paused uploader, resume it
        if task.get('uploader') and task['uploader'].isRunning():
            self.log_message(f"Resuming paused uploader for Order {task['order_number']}")
            task['uploader'].resume()
            task['status'] = 'running'
            task['last_action_by'] = self.user_info.get('Emp_FullName', 'Unknown')
            self.update_task_list(task)
        else:
            # Otherwise start a new uploader
            self.log_message(f"Starting new uploader for Order {task['order_number']}")
            self.start_task(task)
        
        # Log the action
        self.log_activity("task", "resume", 
                         f"Resumed upload task for order {task['order_number']}", 
                         self.user_info.get('Emp_FullName'))
        
        # Update buttons
        self.update_buttons_state()
        
        # Update system tray menu
        self.update_tray_menu()

    def restart_selected_task(self):
        """
        Restart the selected upload task from the beginning
        """
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            self.log_message("No task selected")
            return
        
        # Confirm restart
        reply = QMessageBox.question(
            self, 
            'Confirm Restart', 
            f'Are you sure you want to restart the upload for Order {task["order_number"]}? This will start the upload from the beginning.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Stop existing uploader if running
        if task.get('uploader') and task['uploader'].isRunning():
            self.cleanup_task_thread(task)
        
        # Delete the state file if it exists
        state_file = Path.home() / '.aws_uploader' / f"task_state_{task['order_number']}.json"
        if state_file.exists():
            try:
                state_file.unlink()
                self.log_message(f"Deleted saved state for Order {task['order_number']}")
            except Exception as e:
                self.log_message(f"Error deleting state file: {str(e)}")
        
        # Reset task progress
        task['uploader'] = None
        task['status'] = 'pending'
        task['progress'] = 0
        task['last_action_by'] = self.user_info.get('Emp_FullName', 'Unknown')
        self.update_task_list(task)
        
        # Log the action
        self.log_activity("task", "restart", 
                        f"Restarted upload task for order {task['order_number']}", 
                        self.user_info.get('Emp_FullName'))
        
        # Start the task with a clean slate
        self.start_task(task)

    def cancel_selected_task(self):
        """Cancel the selected upload task"""
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        # Check if task_data is a dictionary or a direct task_id
        if isinstance(task_data, dict):
            task_id = task_data['id']
        else:
            # If task_data is the task_id directly
            task_id = task_data
            
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            self.log_message(f"Error: Could not find task with ID {task_id}")
            return
            
        # Cancel only if task is running or paused
        if task['status'] in ['running', 'paused'] and task.get('uploader'):
            # Stop the uploader
            self.cleanup_task_thread(task)
            
            # Update task status
            task['status'] = 'cancelled'
            task['last_action_by'] = self.user_info.get('Emp_FullName', 'Unknown')
            
            # Update the list item if it exists
            if 'item' in task and task['item']:
                task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Cancelled")
            
            # Log the action
            self.log_activity("task", "cancel", 
                            f"Cancelled upload task for order {task['order_number']}", 
                            self.user_info.get('Emp_FullName'))
            
            # Save cancelled status to database
            self.save_task_to_database(task)
            
            # Update buttons
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
            
            self.log_message(f"Cancelled upload task {task['id']} for order {task['order_number']}")
            
        if all(t['status'] in ['completed', 'cancelled'] for t in self.upload_tasks):
            self.cancel_btn.setEnabled(False)
            
        # Update system tray menu
        self.update_tray_menu()
    
    def delete_selected_task(self):
        """
        Delete the selected upload task from the list and optionally from the database
        """
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
            
        task_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        # Check if task_data is a dictionary or a direct task_id
        if isinstance(task_data, dict):
            task_id = task_data['id']
        else:
            # If task_data is the task_id directly
            task_id = task_data
            
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            self.log_message(f"Error: Could not find task with ID {task_id}")
            return
            
        # Confirm deletion
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            'Confirm Deletion', 
            f'Are you sure you want to delete the task for Order {task["order_number"]}?\n\n'
            f'Status: {task["status"].capitalize()}\n'
            f'Progress: {task.get("progress", 0)}%',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        # Stop task if running
        if task['status'] in ['running', 'paused'] and task.get('uploader'):
            # Stop the uploader
            self.cleanup_task_thread(task)
            self.log_message(f"Stopped running task for order {task['order_number']}")
            
        # Ask if the task should also be deleted from the database
        delete_from_db = False
        if hasattr(task, 'db_id') and task.get('db_id'):
            db_reply = QMessageBox.question(
                self, 
                'Delete from Database', 
                'Do you also want to delete this task from the database?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            delete_from_db = (db_reply == QMessageBox.Yes)
            
        # Remove from list widget
        row = self.task_list.row(selected_items[0])
        self.task_list.takeItem(row)
        
        # Remove task data
        if 'item' in task:
            task['item'] = None
            
        # Delete from database if requested
        if delete_from_db and hasattr(task, 'db_id') and task.get('db_id'):
            try:
                if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                    self.db_manager.connect()
                    
                cursor = self.db_manager.connection.cursor()
                
                # Determine ID column
                cursor.execute("""
                SELECT COLUMN_NAME 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'upload_tasks' 
                AND COLUMN_NAME IN ('task_id', 'id')
                """, (self.db_manager.rds_config['database'],))
                
                columns = cursor.fetchall()
                id_column = 'task_id' if ('task_id',) in columns else 'id'
                
                # Delete the record
                query = f"DELETE FROM upload_tasks WHERE {id_column} = %s"
                cursor.execute(query, (task['db_id'],))
                self.db_manager.connection.commit()
            except Exception as e:
                self.log_message(f"Error deleting task from database: {str(e)}")
                import traceback
                self.log_message(traceback.format_exc())
                
        # Remove from tasks list
        self.upload_tasks = [t for t in self.upload_tasks if t['id'] != task_id]
        
        # Log the action
        self.log_message(f"Deleted task for order {task['order_number']} from task list")
        self.log_activity("task", "delete", 
                        f"Deleted task for order {task['order_number']}", 
                        self.user_info.get('Emp_FullName'))
        
        # Update button states
        self.on_task_selected()
        
        # Enable/disable start all button based on pending tasks
        # self.start_all_btn.setEnabled(any(t['status'] == 'pending' for t in self.upload_tasks))
    
    def save_task_to_database(self, task):
        """
        Save a task to the database for persistence
        
        Args:
            task (dict): Task to save
            
        Returns:
            int: Database ID of the saved task
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
            
            # Calculate state file path - convert Path objects to strings
            state_path = str(Path.home() / '.aws_uploader' / f"task_state_{task['order_number']}.json")
            
            # Ensure folder_path and local_path are strings (not PosixPath)
            folder_path = str(task['folder_path']) if task['folder_path'] else ''
            local_path = str(task.get('local_path', folder_path)) if task.get('local_path') else folder_path
            
            # Convert QDate to string format that MySQL can handle
            order_date = task['order_date']
            if isinstance(order_date, QDate):
                try:
                    # تحقق من أن التاريخ صالح
                    if order_date.isValid() and order_date.year() > 0:
                        order_date = order_date.toString('yyyy-MM-dd')
                    else:
                        # استخدام التاريخ الحالي إذا كان التاريخ غير صالح
                        current_date = QDate.currentDate()
                        order_date = current_date.toString('yyyy-MM-dd')
                        self.log_message(f"Warning: Invalid QDate found, using current date instead")
                except Exception as date_error:
                    # في حالة حدوث أي خطأ، استخدم التاريخ الحالي
                    from datetime import datetime
                    order_date = datetime.now().strftime('%Y-%m-%d')
                    self.log_message(f"Error processing QDate: {str(date_error)}. Using current date.")
            elif hasattr(order_date, 'strftime'):
                # إذا كان datetime، قم بتحويله إلى سلسلة نصية
                order_date = order_date.strftime('%Y-%m-%d')
            elif isinstance(order_date, str):
                # إذا كان بالفعل سلسلة نصية، تأكد من أنه بالتنسيق الصحيح
                try:
                    from datetime import datetime
                    # حاول تحليل التاريخ للتأكد من صحته
                    parsed_date = datetime.strptime(order_date, '%Y-%m-%d')
                    order_date = parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    # إذا كان التنسيق غير صحيح، استخدم التاريخ الحالي
                    order_date = datetime.now().strftime('%Y-%m-%d')
                    self.log_message(f"Warning: Invalid date string format. Using current date.")
            else:
                # إذا كان التاريخ None أو نوع غير معروف، استخدم التاريخ الحالي
                from datetime import datetime
                order_date = datetime.now().strftime('%Y-%m-%d')
                self.log_message(f"Warning: Unknown date type. Using current date.")
            
            cursor = self.db_manager.connection.cursor()
            
            # First, check if the task_state_path column exists
            cursor.execute("""
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME = 'task_state_path'
            """, (self.db_manager.rds_config['database'],))
            
            task_state_path_exists = cursor.fetchone()[0] > 0
            
            # Next, check if the employee tracking columns exist
            cursor.execute("""
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME = 'created_by'
            """, (self.db_manager.rds_config['database'],))
            
            created_by_exists = cursor.fetchone()[0] > 0
            
            # Check if the task_id column exists
            cursor.execute("""
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME = 'task_id'
            """, (self.db_manager.rds_config['database'],))
            
            has_task_id = cursor.fetchone()[0] > 0
            
            # Determine the ID column name to use in the WHERE clause
            id_column = 'task_id' if has_task_id else 'id'
            
            self.log_message(f"Using database column '{id_column}' for task identification")
            
            # Get current user info for tracking
            current_user = self.user_info.get('Emp_FullName', 'Unknown')
            current_emp_id = self.user_info.get('Emp_ID')
            
            # Set created_by if not already set in task
            if 'created_by' not in task and self.user_info.get('is_logged_in', False):
                task['created_by'] = current_user
                task['created_by_emp_id'] = current_emp_id
            
            # Always update last_action_by when saving
            if self.user_info.get('is_logged_in', False):
                task['last_action_by'] = current_user
                task['last_action_by_emp_id'] = current_emp_id
            
            # Check if task already has a database ID
            if task.get('db_id'):
                # Build the update query based on which columns exist
                update_fields = [
                    "order_number = %s",
                    "order_date = %s",
                    "folder_path = %s",
                    "local_path = %s",
                    "status = %s",
                    "progress = %s",
                    "main_photographer_id = %s",
                    "assistant_photographer_id = %s",
                    "video_photographer_id = %s",
                    "DeviceID = %s"
                ]
                # إذا كانت المهمة مكتملة، حدث completed_timestamp
                if task.get('status') == 'completed':
                    update_fields.append("completed_timestamp = NOW()")
                
                # Add task_state_path and last_state_update if they exist
                if task_state_path_exists:
                    update_fields.append("task_state_path = %s")
                    update_fields.append("last_state_update = NOW()")
                
                # Add employee tracking fields if they exist
                if created_by_exists:
                    update_fields.append("last_action_by = %s")
                    update_fields.append("last_action_time = NOW()")
                    update_fields.append("last_action_by_emp_id = %s")
                    
                    # Set created_by if null
                    update_fields.append("created_by = COALESCE(created_by, %s)")
                    update_fields.append("created_by_emp_id = COALESCE(created_by_emp_id, %s)")
                
                # Create the update query
                query = f"""
                UPDATE upload_tasks SET
                    {", ".join(update_fields)}
                WHERE {id_column} = %s
                """
                
                # Create values tuple based on which columns are included
                values = [
                    task['order_number'],
                    order_date,  # Use the converted date
                    folder_path,
                    local_path,
                    task['status'],
                    task.get('progress', 0),
                    task.get('photographers', {}).get('main'),
                    task.get('photographers', {}).get('assistant'),
                    task.get('photographers', {}).get('video'),
                    task.get('device_id', self.device_id)
                ]
                
                # Add task_state_path if included in the query
                if task_state_path_exists:
                    values.append(state_path)
                
                # Add employee tracking values if included
                if created_by_exists:
                    values.append(task.get('last_action_by', current_user))
                    values.append(task.get('last_action_by_emp_id', current_emp_id))
                    values.append(task.get('created_by', current_user))
                    values.append(task.get('created_by_emp_id', current_emp_id))
                
                # Add the ID as the last parameter
                values.append(task['db_id'])
                
                cursor.execute(query, tuple(values))
                self.db_manager.connection.commit()
                
                return task['db_id']
            
            else:
                # For inserting, build the appropriate column list and values
                insert_columns = [
                    "order_number", "order_date", "folder_path", "local_path",
                    "status", "progress",
                    "main_photographer_id", "assistant_photographer_id", "video_photographer_id",
                    "DeviceID"
                ]
                
                values = [
                    task['order_number'],
                    order_date,  # Use the converted date
                    folder_path,
                    local_path,
                    task['status'],
                    task.get('progress', 0),
                    task.get('photographers', {}).get('main'),
                    task.get('photographers', {}).get('assistant'),
                    task.get('photographers', {}).get('video'),
                    task.get('device_id', self.device_id)
                ]
                
                # Add task_state_path if it exists
                if task_state_path_exists:
                    insert_columns.append("task_state_path")
                    insert_columns.append("last_state_update")
                    values.append(state_path)
                    placeholders = ["%s"] * (len(insert_columns) - 1) + ["NOW()"]
                else:
                    placeholders = ["%s"] * len(insert_columns)
                
                # Add employee tracking columns if they exist
                if created_by_exists:
                    insert_columns.append("created_by")
                    insert_columns.append("last_action_by")
                    insert_columns.append("last_action_time")
                    insert_columns.append("created_by_emp_id")
                    insert_columns.append("last_action_by_emp_id")
                    
                    values.append(task.get('created_by', current_user))
                    values.append(task.get('last_action_by', current_user))
                    values.append(task.get('created_by_emp_id', current_emp_id))
                    values.append(task.get('last_action_by_emp_id', current_emp_id))
                    
                    # Adjust placeholders for the timestamp
                    placeholders.append("%s")  # created_by
                    placeholders.append("%s")  # last_action_by
                    placeholders.append("NOW()")  # last_action_time
                    placeholders.append("%s")  # created_by_emp_id
                    placeholders.append("%s")  # last_action_by_emp_id
                
                # Create the insert query
                query = f"""
                INSERT INTO upload_tasks
                ({", ".join(insert_columns)})
                VALUES ({", ".join(placeholders)})
                """
                
                cursor.execute(query, tuple(values))
                db_id = cursor.lastrowid
                self.db_manager.connection.commit()
                
                # Store database ID in task
                task['db_id'] = db_id
                
                self.log_message(f"Created new task record in database (ID: {db_id})")
                return db_id
            
        except Exception as e:
            self.log_message(f"Error saving task to database: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return None

    def validate_state_file(self, state_file):
        """
        Validate and potentially repair a state file
        
        Args:
            state_file (Path): Path to the state file
            
        Returns:
            dict or None: The loaded state if valid, None if invalid and cannot be repaired
        """
        try:
            # Check if file exists and is not empty
            if not state_file.exists() or state_file.stat().st_size == 0:
                self.log_message(f"State file is empty or does not exist: {state_file}")
                return None

            # Try to read and parse the file
            with open(state_file, 'r') as f:
                content = f.read().strip()
                
            # Attempt basic JSON repairs if needed
            try:
                # First try parsing as is
                state = json.loads(content)
                
                # Check if the state has the minimum required fields
                required_fields = ['order_number', 'folder_path']
                missing_fields = [field for field in required_fields if field not in state]
                
                if missing_fields:
                    self.log_message(f"State file is missing required fields: {', '.join(missing_fields)}")
                    # Create backup before returning None
                    backup_file = state_file.with_suffix('.json.incomplete')
                    shutil.copy(state_file, backup_file)
                    self.log_message(f"Backup created: {backup_file}")
                    return None
                    
                # Validate numbers in state to prevent division by zero
                if 'total_files' in state and (not isinstance(state['total_files'], int) or state['total_files'] <= 0):
                    self.log_message(f"Fix: invalid total_files value ({state.get('total_files')})")
                    state['total_files'] = max(1, int(state.get('total_files', 1)))
                    
                if 'current_file_index' in state:
                    if not isinstance(state['current_file_index'], int) or state['current_file_index'] < 0:
                        self.log_message(f"Fix: invalid current_file_index value ({state.get('current_file_index')})")
                        state['current_file_index'] = max(0, int(state.get('current_file_index', 0)))
                    
                    # Ensure current_file_index doesn't exceed total_files
                    if state['current_file_index'] > state.get('total_files', 1):
                        self.log_message(f"Fix: current_file_index is greater than total_files")
                        state['current_file_index'] = state.get('total_files', 1)
                
                # Add a timestamp for tracking
                state['validation_timestamp'] = datetime.now().isoformat()
                
                # Save the validated and potentially repaired state
                with open(state_file, 'w') as f:
                    json.dump(state, f, indent=2)
                    
                return state
            except json.JSONDecodeError as e:
                self.log_message(f"JSON format error in file {state_file}, Attempting to fix: {str(e)}")
                    
                # Attempt basic repairs
                # Fix 1: Try adding missing closing brace
                if content.count('{') > content.count('}'):
                    fixed_content = content + '}'
                    try:
                        state = json.loads(fixed_content)
                        self.log_message(f"Fixed state file by adding missing bracket")
                            
                        # Save the repaired file
                        with open(state_file, 'w') as f:
                            f.write(json.dumps(state, indent=2))
                                
                        return state
                    except json.JSONDecodeError:
                        pass
                    
                # Fix 2: Try removing trailing comma
                if "},}" in content or "}, }" in content:
                    fixed_content = content.replace("},}", "}}")
                    fixed_content = fixed_content.replace("}, }", "}}")
                    try:
                        state = json.loads(fixed_content)
                        self.log_message(f"Fixed state file by removing extra comma")
                            
                        # Save the repaired file
                        with open(state_file, 'w') as f:
                            f.write(json.dumps(state, indent=2))
                                
                        return state
                    except json.JSONDecodeError:
                        pass
                    
                # If repair attempts failed, create backup and return None
                backup_file = state_file.with_suffix('.json.bak')
                shutil.copy(state_file, backup_file)
                self.log_message(f"Failed to fix state file. Backup created: {backup_file}")
                    
                # Delete or rename the corrupted file
                state_file.rename(state_file.with_suffix('.json.corrupted'))
                return None
                    
        except Exception as e:
            self.log_message(f"Unexpected error while checking state file {state_file}: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            
            # In case of an unexpected error, rename the file to avoid reusing it
            try:
                error_file = state_file.with_suffix('.json.error')
                shutil.copy(state_file, error_file)
                state_file.rename(state_file.with_suffix('.json.invalid'))
                self.log_message(f"Moved suspicious state file: {error_file}")
            except:
                pass
                
            return None
    
    def load_tasks_from_database(self):
        """Load tasks from database - only this device's incomplete tasks and today's completed tasks"""
        if not self.db_manager:
                return
                
        if not self.db_manager.connection:
            return
            
        if not self.db_manager.connection.is_connected():
            try:
                self.db_manager.connect()
            except Exception as e:
                print(f"Failed to reconnect to database: {str(e)}")
                return
            
        try:
            with self.db_manager.connection.cursor(dictionary=True) as cursor:
                # Get today's date for filtering completed tasks
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                
                # Query for:
                # 1. Incomplete tasks (pending, running, paused) for this device
                # 2. Tasks completed today for this device
                query = """
                SELECT t.task_id, t.order_number, t.status, t.progress, 
                       t.created_at, t.completed_timestamp, t.folder_path, t.local_path,
                       t.main_photographer_id, t.assistant_photographer_id, t.video_photographer_id,
                       t.order_date, t.DeviceID, d.DeviceName
                FROM upload_tasks t
                LEFT JOIN devices d ON t.DeviceID = d.DeviceID
                WHERE t.DeviceID = %s 
                AND (
                    t.status IN ('pending', 'running', 'paused') 
                    OR 
                    (t.status = 'completed' AND DATE(t.completed_timestamp) = %s)
                )
                ORDER BY 
                    CASE 
                        WHEN t.status = 'running' THEN 1
                        WHEN t.status = 'paused' THEN 2
                        WHEN t.status = 'pending' THEN 3
                        WHEN t.status = 'completed' THEN 4
                        ELSE 5
                    END,
                    t.created_at DESC
                """
                
                # Execute query with device ID and today's date
                cursor.execute(query, (self.device_id, today))
                results = cursor.fetchall()
                
                if not results:
                    print(f"No tasks found for device {self.device_name} (ID: {self.device_id})")
                    return
                
                print(f"Found {len(results)} tasks for device {self.device_name}")
                
                for db_task in results:
                    # Skip tasks that are already in the list
                    if any(t['order_number'] == db_task['order_number'] for t in self.upload_tasks):
                        continue
                            
                    # Create task object
                    task_id = len(self.upload_tasks) + 1
                    task = {
                        'id': task_id,
                        'order_number': db_task['order_number'],
                        'folder_path': db_task.get('folder_path', ''),
                        'local_path': db_task.get('local_path', db_task.get('folder_path', '')),
                        'status': db_task.get('status', 'pending'),
                        'progress': db_task.get('progress', 0),
                        'uploader': None,
                        'photographers': {
                            'main': db_task.get('main_photographer_id'),
                            'assistant': db_task.get('assistant_photographer_id'),
                            'video': db_task.get('video_photographer_id')
                        },
                        'order_date': self._parse_safe_date(db_task.get('order_date')),
                        'db_id': db_task['task_id'],
                        'device_id': db_task['DeviceID'],
                        'device_name': db_task['DeviceName'],
                    }
                    
                    # Build full path for the task
                    base_storage_path = self.db_manager.get_device_storage_path(self.mac_address)
                    
                    # Use the local_path directly if it's already a full path
                    if task['local_path'] and os.path.isabs(task['local_path']):
                        full_local_path = task['local_path']
                    elif base_storage_path and task['local_path']:
                        # Only combine if local_path is relative
                        if task['local_path'].startswith('/'):
                            # Remove leading slash from relative path
                            relative_path = task['local_path'][1:]
                        else:
                            relative_path = task['local_path']
                        
                        # Create full path by combining base storage path with relative path
                        full_local_path = os.path.join(base_storage_path, relative_path)
                    else:
                        # Fallback to using folder_path if local_path is not available
                        if task.get('folder_path'):
                            full_local_path = task['folder_path']
                        else:
                            full_local_path = task['local_path'] or ''
                    
                    task['full_local_path'] = full_local_path
                    
                    # Create QListWidgetItem for the task
                    from PyQt5.QtWidgets import QListWidgetItem
                    from PyQt5.QtCore import Qt
                    
                    task_item = QListWidgetItem()
                    
                    # Show status with date for completed tasks
                    if task['status'] == 'completed':
                        completed_date = db_task.get('completed_timestamp')
                        if completed_date:
                            date_str = completed_date.strftime("%H:%M") if hasattr(completed_date, 'strftime') else str(completed_date)
                            task_item.setText(f"Task {task_id}: Order {task['order_number']} - Completed ({date_str})")
                        else:
                            task_item.setText(f"Task {task_id}: Order {task['order_number']} - Completed (Today)")
                    else:
                        task_item.setText(f"Task {task_id}: Order {task['order_number']} - {task['status'].capitalize()}")
                    
                    task_item.setData(Qt.ItemDataRole.UserRole, task_id)
                    
                    # Add item to task
                    task['item'] = task_item
                    
                    # Add to the list widget
                    self.task_list.addItem(task_item)
                    
                    # Add task to list
                    self.upload_tasks.append(task)
                
                if self.upload_tasks:
                    incomplete_count = len([t for t in self.upload_tasks if t['status'] in ['pending', 'running', 'paused']])
                    completed_today_count = len([t for t in self.upload_tasks if t['status'] == 'completed'])
                    
                    print(f"Loaded {len(self.upload_tasks)} tasks from database:")
                    print(f"  - {incomplete_count} incomplete tasks")
                    print(f"  - {completed_today_count} completed today")
                    
                    # Add a small delay to ensure all components are ready
                    if incomplete_count > 0:
                        print("Waiting for components to initialize before starting tasks...")
                        import time
                        time.sleep(1)  # 1 second delay before starting any tasks
                    
                    # Add all incomplete tasks to queue for sequential execution
                    incomplete_tasks = [task for task in self.upload_tasks if task['status'] in ['pending', 'running', 'paused']]
                    if incomplete_tasks:
                        print(f"Adding {len(incomplete_tasks)} incomplete tasks to queue...")
                        self.log_message(f"🔄 Found {len(incomplete_tasks)} incomplete tasks, adding to queue...")
                        
                        for task in incomplete_tasks:
                            try:
                                # Reset status to pending for queue processing
                                task['status'] = 'pending'
                                self.update_task_list(task)
                                
                                # Add to queue
                                self.add_task_to_queue(task)
                                print(f"Added task {task['id']}: Order {task['order_number']} to queue")
                            except Exception as e:
                                print(f"Failed to add task {task['id']} to queue: {str(e)}")
                
        except Exception as e:
            print(f"Error loading tasks from database: {str(e)}")
            import traceback
            traceback.print_exc()

    def auto_start_task(self, task):
        """
        Automatically start a task without user interaction (adds to queue)
        """
        try:
            if not task:
                return
            
            # Determine the action type for better logging
            action_type = "Starting"
            if task.get('status') == 'paused':
                action_type = "Resuming"
            elif task.get('status') == 'running':
                action_type = "Restarting"
            
            print(f"{action_type} task {task['id']}: Order {task['order_number']}")
            self.log_message(f"{action_type} upload for Order {task['order_number']}")
            
            # Check if we have the required data
            if not task.get('local_path'):
                print(f"Error: Local storage path missing for task {task.get('order_number')}")
                return
            
            # Check if path exists, if not, try to use folder_path
            if not os.path.exists(task['local_path']):
                if task.get('folder_path') and os.path.exists(task['folder_path']):
                    task['local_path'] = task['folder_path']
                    print(f"Using folder_path as local_path for task {task['order_number']}")
                else:
                    print(f"Warning: Local storage path does not exist: {task['local_path']}")
                    return
            
            # Set task status to pending (queued)
            task['status'] = 'pending'
            self.update_task_list(task)
            
            # Add task to queue for sequential execution
            self.add_task_to_queue(task)
            
        except Exception as e:
            print(f"Error auto-starting task: {str(e)}")
            import traceback
            traceback.print_exc()

    def check_db_schema(self):
        """Verify database schema for user authentication"""
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            cursor = self.db_manager.connection.cursor()
            
            # Check for employees table
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'employees'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] == 0:
                self.log_message("Warning: Employees table doesn't exist!")
                return
                
            # Check for username/password columns
            cursor.execute("""
            SELECT COUNT(*) as columns_exist
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'employees' 
            AND COLUMN_NAME IN ('Emp_UserName', 'Emp_Password')
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] < 2:
                self.log_message("Warning: Username/password columns not fully present in employees table!")
                return
                
            # Check if any user exists
            cursor.execute("SELECT COUNT(*) FROM employees")
            result = cursor.fetchone()
            self.log_message(f"Number of users in database: {result[0]}")
            
        except Exception as e:
            self.log_message(f"Error checking database structure: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def toggle_progress_mode(self):
        """
        Toggle between showing file scanning progress and actual upload progress
        This function is kept for compatibility but is no longer used in the UI
        """
        # Always use upload mode regardless of toggle
        self.progress_mode = 'upload'
        
        # Update progress display for all tasks
        for task in self.upload_tasks:
            if task.get('uploader') and task['uploader'].isRunning():
                if hasattr(task['uploader'], 'uploaded_file_count') and hasattr(task['uploader'], 'total_files'):
                    # Always show actual uploads
                    progress = (task['uploader'].uploaded_file_count / max(task['uploader'].total_files, 1)) * 100
                    
                    task['progress'] = progress
                    self.update_task_list(task)

    def auto_resume_all_tasks(self):
        """
        Automatically resume all paused tasks
        """
        try:
            paused_tasks = [task for task in self.upload_tasks if task['status'] == 'paused']
            if paused_tasks:
                self.log_message(f"Auto-resuming {len(paused_tasks)} paused tasks")
                
                # تم إزالة التحقق من تسجيل الدخول هنا - نسمح باستئناف المهام بدون تسجيل الدخول
                
                # Start tasks one by one with longer delay between them
                import time
                tasks_started = 0
                
                for i, task in enumerate(paused_tasks):
                    try:
                        # Check database connection before each operation
                        if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                            self.log_message("Reconnecting to database...")
                            self.db_manager.connect()
                        
                        self.log_message(f"Resuming task {i+1}/{len(paused_tasks)}: Order {task['order_number']}")
                        
                        # Use longer delay between tasks
                        if tasks_started > 0:
                            self.log_message(f"Waiting before resuming next task...")
                            time.sleep(3)  # Wait 3 seconds between tasks
                        
                        # Execute task in a separate try/except block
                        try:
                            self.start_task(task)
                            tasks_started += 1
                            
                            # Additional delay before starting thread
                            time.sleep(0.5)
                        except Exception as task_error:
                            self.log_message(f"Error resuming task {task['order_number']}: {str(task_error)}")
                            import traceback
                            self.log_message(traceback.format_exc())
                            continue
                            
                    except Exception as db_error:
                        self.log_message(f"Database connection error: {str(db_error)}")
                        # Temporary pause before next attempt
                        time.sleep(5)
                
                if tasks_started > 0:
                    self.log_message(f"Successfully resumed {tasks_started} out of {len(paused_tasks)} tasks")
                else:
                    self.log_message("No tasks were successfully resumed, please try again")
            else:
                self.log_message("No paused tasks found to resume")
        except Exception as e:
            self.log_message(f"Error during auto-resume of tasks: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def auto_resume_task(self, task_id):
        """
        Automatically resume a task by ID
        This method is used for single-task resumption from the auto-resume system
        
        Args:
            task_id (int): ID of the task to resume
        """
        try:
            # Find the task with the given ID
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            
            if not task:
                self.log_message(f"Error: Could not find task with ID {task_id}")
                return False
                
            if task['status'] != 'paused':
                self.log_message(f"Task {task_id} is not in paused state, cannot resume")
                return False
                
            # تم إزالة التحقق من تسجيل الدخول هنا
                
            self.log_message(f"Auto-resuming task {task_id} for order {task.get('order_number', 'unknown')}")
            
            # Use start_task to resume with proper state handling
            self.start_task(task)
            
            return True
            
        except Exception as e:
            self.log_message(f"Error auto-resuming task {task_id}: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return False

    def refresh_todays_uploads(self):
        """
        Refresh today's uploads list by querying the database
        """
        try:
            self.log_message("Refreshing today's uploads list...")
            
            # Clear the list
            self.today_uploads_list.clear()
            
            # Check database connection
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("Error: No database connection available")
                return
            
            # Get today's date in the format used by the database
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Query the database for today's uploads
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            # First, check which ID column to use
            cursor.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME IN ('task_id', 'id')
            """, (self.db_manager.rds_config['database'],))
            
            columns = cursor.fetchall()
            if not columns:
                self.log_message("Error: Could not find ID column in upload_tasks table")
                return
                
            # Use the first ID column found (prioritize task_id if available)
            id_columns = [col['COLUMN_NAME'] for col in columns]
            id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
            
            # Query for today's uploads
            query = f"""
            SELECT {id_column} as task_id, order_number, status, progress, 
                   created_at, folder_path, created_by
            FROM upload_tasks 
            WHERE DATE(created_at) = %s
            ORDER BY created_at DESC
            """
            
            # Execute query
            cursor.execute(query, (today,))
            results = cursor.fetchall()
            
            self.log_message(f"Found {len(results)} uploads today")
            
            # Add items to the list
            for upload in results:
                item_text = f"Order {upload['order_number']} - {upload['status'].capitalize()} ({int(upload['progress'])}%)"
                if 'created_by' in upload and upload['created_by']:
                    item_text += f" - by {upload['created_by']}"
                
                # Add the item to the list
                from PyQt5.QtWidgets import QListWidgetItem
                from PyQt5.QtCore import Qt
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, upload['task_id'])
                self.today_uploads_list.addItem(item)
                
        except Exception as e:
            self.log_message(f"Error refreshing today's uploads: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def apply_history_filter(self):
        """
        Apply date and order filters to the upload history
        """
        try:
            self.log_message("Applying history filter...")
            
            # Get filter values
            from_date = self.from_date.date().toString("yyyy-MM-dd")
            to_date = self.to_date.date().toString("yyyy-MM-dd")
            order_number = self.order_filter.text().strip()
            
            self.log_message(f"Filter: From {from_date} to {to_date}, Order: {order_number or 'All'}")
            
            # Clear the history list
            self.history_list.clear()
            
            # Clear the details
            self.upload_details.clear()
            
            # Check database connection
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("Error: No database connection available")
                return
            
            # Query the database for upload history
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            # First, check which ID column to use
            cursor.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME IN ('task_id', 'id')
            """, (self.db_manager.rds_config['database'],))
            
            columns = cursor.fetchall()
            if not columns:
                self.log_message("Error: Could not find ID column in upload_tasks table")
                return
                
            # Use the first ID column found (prioritize task_id if available)
            id_columns = [col['COLUMN_NAME'] for col in columns]
            id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
            
            # Build the query with filters
            query = f"""
            SELECT t.task_id, t.order_number, t.status, t.progress, 
                   t.created_at, t.updated_at, t.folder_path, t.created_by, 
                   t.order_date, t.main_photographer_id, t.assistant_photographer_id, 
                   t.video_photographer_id, t.local_path, t.DeviceID, d.DeviceName
            FROM upload_tasks t
            LEFT JOIN devices d ON t.DeviceID = d.DeviceID
            WHERE 1=1
            """
            
            params = []
            
            if from_date:
                query += " AND DATE(created_at) >= %s"
                params.append(from_date)
                
            if to_date:
                query += " AND DATE(created_at) <= %s"
                params.append(to_date)
                
            if order_number:
                query += " AND order_number LIKE %s"
                params.append(f"%{order_number}%")
            
            # Add order by
            query += " ORDER BY created_at DESC"
            
            # Execute query
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            self.log_message(f"Found {len(results)} uploads matching filter criteria")
            
            # Add items to the history list
            from PyQt5.QtWidgets import QListWidgetItem
            from PyQt5.QtCore import Qt
            
            for upload in results:
                # Format the date
                created_date = upload.get('created_at')
                if created_date:
                    if hasattr(created_date, 'strftime'):
                        date_str = created_date.strftime("%Y-%m-%d %H:%M")
                    else:
                        date_str = str(created_date)
                else:
                    date_str = "Unknown"
                
                # Create display text
                item_text = f"Order {upload['order_number']} - {upload['status'].capitalize()}"
                item_text += f" ({date_str})"
                
                # Add the item to the list
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, upload)
                self.history_list.addItem(item)
            
            # Log activity
            self.log_activity("history", "filter", 
                         f"Applied filter to upload history: From {from_date} to {to_date}, Order: {order_number or 'All'}", 
                         self.user_info.get('Emp_FullName'))
                
        except Exception as e:
            self.log_message(f"Error applying history filter: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def load_upload_history(self):
        """
        Load upload history for the History tab
        This is called during initialization to populate the history list
        """
        try:
            self.log_message("Loading upload history...")
            
            # Reset date filters to today by default
            today = QDate.currentDate()
            self.from_date.setDate(today)
            self.to_date.setDate(today)
            
            # Apply the filter to load today's uploads
            self.apply_history_filter()
            
        except Exception as e:
            self.log_message(f"Error loading upload history: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def init_database_schema(self):
        """
        Initialize database schema for task storage
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("No database connection available, skipping schema initialization")
                return
                
            self.log_message("Checking database schema...")
            
            cursor = self.db_manager.connection.cursor()
            
            # Check if upload_tasks table exists
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'upload_tasks'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] == 0:
                # Table doesn't exist, create it
                self.log_message("Creating upload_tasks table...")
                
                # Create the table with appropriate structure
                create_table_query = """
                CREATE TABLE upload_tasks (
                    task_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_number VARCHAR(50) NOT NULL,
                    order_date DATE,
                    folder_path VARCHAR(1024) NOT NULL,
                    main_photographer_id INT,
                    assistant_photographer_id INT,
                    video_photographer_id INT,
                    status VARCHAR(20) DEFAULT 'pending',
                    progress INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    s3_destination VARCHAR(1024),
                    total_files INT DEFAULT 0,
                    uploaded_files INT DEFAULT 0,
                    failed_files INT DEFAULT 0,
                    local_path VARCHAR(1024),
                    completed_at TIMESTAMP NULL,
                    INDEX idx_order_number (order_number),
                    INDEX idx_status (status),
                    INDEX idx_created_at (created_at),
                    INDEX idx_order_date (order_date)
                )
                """
                cursor.execute(create_table_query)
                self.db_manager.connection.commit()
                self.log_message("Created upload_tasks table")
            
            # Check if task_state_path column exists
            cursor.execute("""
            SELECT COUNT(*) as column_exists
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = 'upload_tasks'
            AND column_name = 'task_state_path'
            """, (self.db_manager.rds_config['database'],))
            
            has_state_path = cursor.fetchone()[0] > 0
            
            if not has_state_path:
                # Add the task_state_path column
                self.log_message("Adding task_state_path column to upload_tasks table")
                alter_query = """
                ALTER TABLE upload_tasks
                ADD COLUMN task_state_path VARCHAR(1024) NULL,
                ADD COLUMN last_state_update TIMESTAMP NULL
                """
                cursor.execute(alter_query)
                self.db_manager.connection.commit()
            
            # Check if user tracking columns exist
            cursor.execute("""
            SELECT COUNT(*) as column_exists
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = 'upload_tasks'
            AND column_name = 'created_by'
            """, (self.db_manager.rds_config['database'],))
            
            has_user_tracking = cursor.fetchone()[0] > 0
            
            if not has_user_tracking:
                # Add user tracking columns
                self.log_message("Adding user tracking columns to upload_tasks table")
                alter_query = """
                ALTER TABLE upload_tasks
                ADD COLUMN created_by VARCHAR(100) NULL,
                ADD COLUMN last_action_by VARCHAR(100) NULL,
                ADD COLUMN last_action_time TIMESTAMP NULL,
                ADD COLUMN created_by_emp_id INT NULL,
                ADD COLUMN last_action_by_emp_id INT NULL,
                ADD INDEX idx_created_by (created_by),
                ADD INDEX idx_last_action_by (last_action_by)
                """
                cursor.execute(alter_query)
                self.db_manager.connection.commit()
            
            # Check if photographers table exists
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'photographers'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] == 0:
                # Table doesn't exist, create it
                self.log_message("Creating photographers table...")
                
                create_table_query = """
                CREATE TABLE photographers (
                    photographer_id INT AUTO_INCREMENT PRIMARY KEY,
                    photographer_name VARCHAR(100) NOT NULL,
                    employee_id INT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_photographer_name (photographer_name),
                    INDEX idx_employee_id (employee_id)
                )
                """
                cursor.execute(create_table_query)
                self.db_manager.connection.commit()
                self.log_message("Created photographers table")
            
            # Check if activity_log table exists
            cursor.execute("""
            SELECT COUNT(*) as table_exists
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = 'activity_log'
            """, (self.db_manager.rds_config['database'],))
            
            result = cursor.fetchone()
            if result[0] == 0:
                # Table doesn't exist, create it
                self.log_message("Creating activity_log table...")
                
                create_table_query = """
                CREATE TABLE activity_log (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    username VARCHAR(100) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    details TEXT,
                    ip_address VARCHAR(50),
                    device_id VARCHAR(100),
                    emp_id INT NULL,
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_username (username),
                    INDEX idx_category (category),
                    INDEX idx_action (action),
                    INDEX idx_emp_id (emp_id)
                )
                """
                cursor.execute(create_table_query)
                self.db_manager.connection.commit()
                self.log_message("Created activity_log table")
            
            self.log_message("Database schema check completed")
        except Exception as e:
            self.log_message(f"Error initializing database schema: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def reset_history_filter(self):
        """
        Reset history filter to show today's uploads
        """
        try:
            # Set date filters to today
            today = QDate.currentDate()
            self.from_date.setDate(today)
            self.to_date.setDate(today)
            
            # Clear order filter
            self.order_filter.clear()
            
            # Apply the filter
            self.apply_history_filter()
            
            self.log_message("Reset history filter to today's date")
            
        except Exception as e:
            self.log_message(f"Error resetting history filter: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

    def show_order_details(self, item):
        """
        Show details for the selected order in the history list
        
        Args:
            item (QListWidgetItem): The selected item in the history list
        """
        try:
            # Get the upload data from the item
            from PyQt5.QtCore import Qt
            upload_data = item.data(Qt.ItemDataRole.UserRole)
            
            if not upload_data:
                self.log_message("No upload data found for selected item")
                return
                
            # Clear the details view
            self.upload_details.clear()
            
            # Format the details HTML
            html = "<html><body style='font-family: Arial; font-size: 10pt;'>"
            html += f"<h2>Order {upload_data['order_number']}</h2>"
            
            # Basic details
            html += "<table style='width: 100%; border-spacing: 5px;'>"
            
            # Status with color
            status = upload_data.get('status', 'unknown')
            status_color = {
                'completed': 'green',
                'running': 'blue',
                'paused': 'orange',
                'pending': 'gray',
                'cancelled': 'red',
                'error': 'darkred'
            }.get(status.lower(), 'black')
            
            html += f"<tr><td><b>Status:</b></td><td style='color: {status_color};'>{status.capitalize()}</td></tr>"
            
            # Progress
            progress = int(upload_data.get('progress', 0))
            html += f"<tr><td><b>Progress:</b></td><td>{progress}%</td></tr>"
            
            # Dates
            created_date = upload_data.get('created_at')
            if created_date:
                if hasattr(created_date, 'strftime'):
                    created_str = created_date.strftime("%Y-%m-%d %H:%M")
                else:
                    created_str = str(created_date)
                html += f"<tr><td><b>Created:</b></td><td>{created_str}</td></tr>"
                
            updated_date = upload_data.get('updated_at')
            if updated_date:
                if hasattr(updated_date, 'strftime'):
                    updated_str = updated_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    updated_str = str(updated_date)
                html += f"<tr><td><b>Last Updated:</b></td><td>{updated_str}</td></tr>"
                
            # Order date
            order_date = upload_data.get('order_date')
            if order_date:
                if hasattr(order_date, 'strftime'):
                    order_date_str = order_date.strftime("%Y-%m-%d")
                else:
                    order_date_str = str(order_date)
                html += f"<tr><td><b>Order Date:</b></td><td>{order_date_str}</td></tr>"
                
            # Creator
            created_by = upload_data.get('created_by')
            if created_by:
                html += f"<tr><td><b>Created By:</b></td><td>{created_by}</td></tr>"
                
            # Folder path
            folder_path = upload_data.get('folder_path')
            if folder_path:
                html += f"<tr><td><b>Folder Path:</b></td><td>{folder_path}</td></tr>"
                
            # Local path
            local_path = upload_data.get('local_path')
            if local_path and local_path != folder_path:
                html += f"<tr><td><b>Local Path:</b></td><td>{local_path}</td></tr>"
                
            # Photographers and Device section combined
            html += self.format_photographers_and_device_section(upload_data)
                
            html += "</table>"
            
            # Add image preview section
            html += self.add_image_preview_section(upload_data)
            
            html += "</body></html>"
            
            # Set the HTML content
            self.upload_details.setHtml(html)
            
            # Disconnect any existing handlers first
            try:
                self.upload_details.anchorClicked.disconnect()
            except Exception:
                pass
            
            # Connect the link click handler for image preview only
            self.upload_details.anchorClicked.connect(self.handle_preview_action)
            
        except Exception as e:
            self.log_message(f"Error showing order details: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def get_photographer_name(self, photographer_id):
        """
        Get photographer name from ID
        
        Args:
            photographer_id (int): Photographer ID
            
        Returns:
            str: Photographer name or ID if not found
        """
        try:
            if not photographer_id:
                return None
                
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                return f"ID: {photographer_id}"
                
            # Query the database for photographer name from employees table
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            query = """
            SELECT Emp_FullName
            FROM employees
            WHERE Emp_ID = %s
            """
            
            cursor.execute(query, (photographer_id,))
            result = cursor.fetchone()
            
            if result and 'Emp_FullName' in result:
                return result['Emp_FullName']
            else:
                return f"ID: {photographer_id}"
                
        except Exception as e:
            self.log_message(f"Error getting photographer name: {str(e)}")
            return f"ID: {photographer_id}"

    def format_photographers_and_device_section(self, upload_data):
        """
        Format photographers and device section together
        
        Args:
            upload_data (dict): Upload data dictionary
            
        Returns:
            str: HTML formatted photographers and device section
        """
        html = ""
        photographers = {}
        
        # Get photographer IDs
        photographer_ids = {
            'main': upload_data.get('main_photographer_id'),
            'assistant': upload_data.get('assistant_photographer_id'), 
            'video': upload_data.get('video_photographer_id')
        }
        
        # Debug: Log photographer IDs
        self.log_message(f"Photographer IDs from upload data: {photographer_ids}")
        
        # Get names for each photographer
        for role, photographer_id in photographer_ids.items():
            if photographer_id:
                name = self.get_photographer_name(photographer_id)
                if name and not name.startswith("ID:"):
                    photographers[role] = name
                else:
                    # Debug: Log the photographer ID that couldn't be found
                    self.log_message(f"Could not find name for photographer ID {photographer_id} (role: {role})")
        
        # Start photographers section
        html += "<tr><td colspan='2'><hr/><b>📸 Team & Equipment:</b></td></tr>"
        
        # Add photographers if any exist
        if photographers:
            role_names = {
                'main': '👨‍📷 Main Photographer',
                'assistant': '🤝 Assistant Photographer', 
                'video': '🎬 Video Photographer'
            }
            
            for role, name in photographers.items():
                display_name = role_names.get(role, role.title())
                html += f"<tr><td><b>{display_name}:</b></td><td>{name}</td></tr>"
        else:
            html += f"<tr><td><b>📷 Photographers:</b></td><td style='color: #888;'>Not specified</td></tr>"
        
        # Add device information
        device_name = upload_data.get('DeviceName', 'Unknown Device')
        html += f"<tr><td><b>💻 Device:</b></td><td>{device_name}</td></tr>"
        
        return html

    def add_image_preview_section(self, upload_data):
        """
        Add image preview section to order details
        
        Args:
            upload_data (dict): Upload data dictionary
            
        Returns:
            str: HTML for image preview section
        """
        html = "<hr/><h3>📸 Images</h3>"
        order_number = upload_data.get('order_number', '')
        if order_number:
            html += f"<p><a href='preview:{order_number}' style='color: #007acc; text-decoration: none; font-weight: bold;'>🔍 Preview Images from S3</a></p>"
        else:
            html += "<p style='color: gray;'>Image preview not available</p>"
        return html

    def handle_preview_action(self, url):
        """
        Handle clicks on preview links in order details
        
        Args:
            url (QUrl): The clicked URL
        """
        try:
            url_str = url.toString()
            
            if url_str.startswith('preview:'):
                order_number = url_str.split(':')[1]
                self.show_image_preview(order_number)
            else:
                self.log_message(f"Unknown preview action: {url_str}")
                
        except Exception as e:
            self.log_message(f"Error handling preview action: {str(e)}")

    def show_image_preview(self, order_number):
        """
        Show image preview dialog for the specified order
        
        Args:
            order_number (str): Order number to preview
        """
        try:
            if not self.aws_session:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", "AWS session not available for image preview")
                return
            
            # Import and show the preview dialog
            from ui.s3_image_preview_dialog import S3ImagePreviewDialog
            preview_dialog = S3ImagePreviewDialog(
                order_number, 
                self.aws_session, 
                self
            )
            preview_dialog.exec_()
            
        except ImportError:
            self.log_message("Image preview feature not available. Missing S3ImagePreviewDialog module.")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Feature Not Available", 
                                   "Image preview feature is not yet implemented.\n\n"
                                   "This feature will allow you to preview uploaded images from S3.")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to open image preview: {str(e)}")
            self.log_message(f"Error opening image preview: {str(e)}")
    
# Removed old order action functions: handle_order_action, resume_order_from_history, view_order_files, delete_order_from_history
    # These have been replaced with the new image preview functionality
    
# Removed view_order_files and delete_order_from_history functions

    def quit_app(self):
        """
        Safely quit the application, saving task states and closing connections
        """
        try:
            # Save task states before quitting
            self.log_message("Application is closing, saving task states...")
            
            # Update application status to clean shutdown
            self.update_app_status("clean_shutdown")
            
            # Stop any running upload tasks
            for task in self.upload_tasks:
                if task.get('status') == 'running' and task.get('uploader') and task['uploader'].isRunning():
                    self.log_message(f"Stopping task for order {task.get('order_number', 'unknown')}")
                    self.cleanup_task_thread(task)
            
            # Close database connection
            if hasattr(self, 'db_manager') and self.db_manager:
                self.log_message("Closing database connection")
                try:
                    self.db_manager.close()
                except Exception as e:
                    self.log_message(f"Error closing database: {str(e)}")
            
            self.log_message("Application closed successfully")
        except Exception as e:
            import traceback
            self.log_message(f"Error during shutdown: {str(e)}")
            self.log_message(traceback.format_exc())
        
        # Exit the application
        from PyQt5.QtWidgets import QApplication
        QApplication.quit()

    def _parse_safe_date(self, date_value):
        """
        Parse a date string safely
        
        Args:
            date_value (str): Date string in the format 'YYYY-MM-DD'
            
        Returns:
            QDate: Parsed date, or current date if parsing fails
        """
        try:
            return QDate.fromString(date_value, "yyyy-MM-dd")
        except:
            return QDate.currentDate()

    def update_buttons_state(self):
        """Update the states of the task control buttons"""
        selected_items = self.task_list.selectedItems()
        
        # If no task is selected, disable all task-specific buttons
        if not selected_items:
            self.modify_task_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
            
        # Get the selected task
        task_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Check if task_data is a dictionary or a direct task_id
        if isinstance(task_data, dict):
            task_id = task_data['id']
        else:
            # If task_data is the task_id directly
            task_id = task_data
        
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            self.log_message(f"Error: Could not find task with ID {task_id}")
            return
            
        # Enable modify button for all tasks
        self.modify_task_btn.setEnabled(True)
        
        # Enable/disable buttons based on task status
        if task['status'] == 'running':
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.delete_btn.setEnabled(False)
        elif task['status'] == 'paused':
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.restart_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.delete_btn.setEnabled(False)
        elif task['status'] in ['completed', 'failed', 'cancelled']:
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.delete_btn.setEnabled(True)
        else:  # pending
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
    
    def init_aws_session(self):
        """Initialize AWS session with credentials from config"""
        try:
            # Use boto3 to create a session
            import boto3
            import os
            
            # Try to extract credentials from secure config
            aws_access_key = self.aws_config.get('AWS_ACCESS_KEY_ID')
            aws_secret_key = self.aws_config.get('AWS_SECRET_ACCESS_KEY')
            region = self.aws_config.get('AWS_REGION', 'us-east-1')
            bucket_name = self.aws_config.get('AWS_S3_BUCKET', 'balistudiostorage')
            
            # If credentials not in config, try environment variables
            if not aws_access_key:
                aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
                self.log_message("Using AWS access key from environment variable")
                
            if not aws_secret_key:
                aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
                self.log_message("Using AWS secret key from environment variable")
                
            if not region:
                region = os.environ.get('AWS_REGION', 'us-east-1')
                self.log_message(f"Using AWS region from environment: {region}")
                
            # Create session if we have credentials
            if aws_access_key and aws_secret_key:
                self.aws_session = boto3.Session(
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=region
                )
                
                # Test the connection to S3
                try:
                    s3 = self.aws_session.client('s3')
                    s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    self.log_message(f"Connected to bucket: {bucket_name}")
                except Exception as bucket_error:
                    self.log_message(f"Error connecting to S3 bucket: {str(bucket_error)}")
                    # Still keep the session, as it might be a permissions issue
            else:
                # Try creating a session with default credentials
                self.log_message("No explicit AWS credentials provided, trying default credentials")
                try:
                    self.aws_session = boto3.Session()
                    s3 = self.aws_session.client('s3')
                    s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    self.log_message(f"Connected to bucket using default credentials: {bucket_name}")
                except Exception as default_error:
                    self.log_message(f"Error using default credentials: {str(default_error)}")
                    self.aws_session = None
        except Exception as e:
            self.log_message(f"Error initializing AWS session: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            self.aws_session = None
            
            # In safe mode, create a mock session
            if self.safe_mode:
                self.log_message("Creating mock AWS session for safe mode")
                self.aws_session = type('MockSession', (), {'client': lambda *args, **kwargs: None})
    
    def closeEvent(self, event):
        """
        Handle window close event - minimize to tray instead of closing
        """
        if self.tray_icon.isVisible():
            # Show notification about minimizing to tray
            self.tray_icon.showMessage(
                "AWS File Uploader",
                "Application was minimized to tray. Click the tray icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
            
            # Hide the window instead of closing
            self.hide()
            event.ignore()
        else:
            # If tray is not available, close normally
            event.accept()
    
    def show_from_tray(self):
        """Show the application window from system tray"""
        self.show()
        self.raise_()
        self.activateWindow()

    def update_tray_menu(self):
        """Update tray menu based on current state"""
        if not hasattr(self, 'tray_icon') or not self.tray_icon:
            return
            
        menu = QMenu()
        
        # Show/Hide action
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_from_tray)
        menu.addAction(show_action)
        
        # Separator
        menu.addSeparator()
        
        # Task status actions
        if hasattr(self, 'upload_tasks') and self.upload_tasks:
            running_tasks = [t for t in self.upload_tasks if t.get('status') == 'running']
            if running_tasks:
                for task in running_tasks[:3]:  # Show max 3 running tasks
                    task_action = QAction(f"Order {task['order_number']} - Running", self)
                    task_action.setEnabled(False)  # Just for display
                    menu.addAction(task_action)
                
                if len(running_tasks) > 3:
                    more_action = QAction(f"... and {len(running_tasks) - 3} more", self)
                    more_action.setEnabled(False)
                    menu.addAction(more_action)
                
                menu.addSeparator()
        
        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)

    def get_mac_address(self):
        """Get MAC address using getmac library"""
        import getmac
        return getmac.get_mac_address()
    
    def try_auto_login(self):
        """Try to auto-login if credentials are available"""
        try:
            # This is a placeholder - implement based on your authentication logic
            pass
        except Exception as e:
            print(f"Auto-login failed: {str(e)}")
    
    def add_task_to_queue(self, task):
        """Add a task to the execution queue"""
        if task not in self.task_queue:
            self.task_queue.append(task)
            self.log_message(f"Added task {task['id']} (Order {task['order_number']}) to queue")
        
        # Try to start the next task if none is running
        self.process_task_queue()
    
    def process_task_queue(self):
        """Process the task queue - start the next task if none is running"""
        # Check if there's already a running task
        if self.current_running_task is not None:
            # Check if the current task is still actually running
            if (self.current_running_task.get('status') == 'running' and 
                self.current_running_task.get('uploader') and 
                self.current_running_task['uploader'].isRunning()):
                # Task is still running, don't start a new one
                return
            else:
                # Current task is no longer running, clear it
                self.current_running_task = None
        
        # If no task is running and there are tasks in queue, start the next one
        if not self.current_running_task and self.task_queue:
            next_task = self.task_queue.pop(0)  # Get first task from queue
            self.current_running_task = next_task
            self.log_message(f"🚀 Starting queued task {next_task['id']} (Order {next_task['order_number']})")
            self.start_task_execution(next_task)
    
    def start_task_execution(self, task):
        """Actually start executing a task (internal method)"""
        try:
            # This is the actual task execution logic from the original start_task method
            if not task:
                return
            
            # Check if we have the required data
            if not task.get('local_path'):
                self.log_message(f"Error: Local storage path missing for task {task.get('order_number')}")
                self.task_execution_finished(task)
                return
            
            # Check if path exists, if not, try to use folder_path
            if not os.path.exists(task['local_path']):
                if task.get('folder_path') and os.path.exists(task['folder_path']):
                    task['local_path'] = task['folder_path']
                    self.log_message(f"Using folder_path as local_path for task {task['order_number']}")
                else:
                    self.log_message(f"Error: Local storage path does not exist: {task['local_path']}")
                    self.task_execution_finished(task)
                    return
            
            # Update task status to running
            task['status'] = 'running'
            self.update_task_list(task)
            
            # Clean up previous thread if it exists
            if task.get('uploader') is not None:
                self.cleanup_task_thread(task)
            
            # Create a new uploader
            from utils.background_uploader import BackgroundUploader
            
            uploader = BackgroundUploader(
                task['folder_path'],
                task['order_number'],
                task['order_date'],
                self.aws_session,
                task['photographers'],
                task.get('full_local_path', task['local_path']),
                self,
                task_id=task['id']  # Pass task ID for better tracking
            )
            
            # Connect signals
            try:
                uploader.progress.connect(lambda current, total, task_id=task['id']: 
                        self.update_task_progress(task_id, current, total))
                uploader.log.connect(lambda message, task_id=task['id']: 
                        self.log_task_message(task_id, message))
                uploader.finished.connect(lambda task_id=task['id']: 
                        self.task_finished(task_id))
                uploader.current_file_progress.connect(
                        lambda file_name, progress, uploaded, total: 
                        self.enhanced_progress_bars.update_file_progress(file_name, progress, uploaded, total))
                  
            except Exception as signal_error:
                self.log_message(f"Error connecting signals: {str(signal_error)}")
            
            # Set the uploader in the task
            task['uploader'] = uploader
            
            # Start the upload
            uploader.start()
            
        except Exception as e:
            self.log_message(f"Error starting task execution: {str(e)}")
            self.task_execution_finished(task)
    
    def task_execution_finished(self, task):
        """Called when a task finishes execution (success or failure)"""
        # Clear the current running task
        if self.current_running_task and self.current_running_task['id'] == task['id']:
            self.current_running_task = None
        
        # Process the next task in queue
        self.process_task_queue()
    
    def handle_file_progress(self, task_id, file_name, progress_percent, uploaded_bytes, total_bytes, formatted_size):
        """
        Handle detailed file progress updates with task ID
        
        Args:
            task_id (int): Task ID
            file_name (str): Current file name
            progress_percent (int): File progress percentage
            uploaded_bytes (int): Bytes uploaded for current file
            total_bytes (int): Total bytes for current file
            formatted_size (str): Human-readable size format
        """
        try:
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                return
            
            # Update enhanced progress bars with formatted information
            self.enhanced_progress_bars.update_file_progress(
                file_name, progress_percent, uploaded_bytes, total_bytes
            )
            
            # Update task item with current file info if running
            if task['status'] == 'running' and 'item' in task and task['item']:
                task_progress = task.get('progress', 0)
                task['item'].setText(
                    f"Task {task_id}: Order {task['order_number']} - Uploading {file_name} "
                    f"({task_progress}% | File: {progress_percent}%)"
                )
            
            # Log detailed progress every 25%
            if progress_percent % 25 == 0 and progress_percent > 0:
                self.log_message(f"Task {task_id}: {file_name} - {progress_percent}% ({formatted_size})")
                
        except Exception as e:
            self.log_message(f"Error handling file progress: {str(e)}")
    
    def handle_task_status_change(self, task_id, status, details):
        """
        Handle task status changes with enhanced logging
        
        Args:
            task_id (int): Task ID
            status (str): New status
            details (str): Status details
        """
        try:
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                return
            
            # Update task status
            task['status'] = status
            
            # Log status change with enhanced information
            self.log_message(f"📊 Task {task_id} (Order {task['order_number']}): {status.upper()} - {details}")
            
            # Update UI based on status
            if status == "completed":
                task['progress'] = 100
                self.enhanced_progress_bars.clear_file_progress()
                
                # Show system notification
                if hasattr(self, 'tray_icon') and self.tray_icon:
                    self.tray_icon.showMessage(
                        "Upload Complete",
                        f"Order {task['order_number']} uploaded successfully",
                        self.tray_icon.MessageIcon.Information,
                        3000
                    )
            elif status == "paused":
                # Update tray icon to show paused state
                if hasattr(self, 'tray_icon') and self.tray_icon:
                    self.update_tray_menu()
            elif status == "stopped":
                task['status'] = 'cancelled'
                task['progress'] = 0
                self.enhanced_progress_bars.clear_file_progress()
            
            # Update task list display
            self.update_task_list(task)
            
            # Update all progress bars
            self.update_all_progress_bars()
            
        except Exception as e:
            self.log_message(f"Error handling task status change: {str(e)}")

    def cleanup_task_thread(self, task):
        """Safely cleanup task thread"""
        if not task.get('uploader'):
            return
        uploader = task['uploader']
        try:
            if uploader.isRunning():
                uploader.stop()
                if not uploader.wait(5000):  # 5 seconds
                    self.log_message(f"Warning: Force terminating thread for task {task['id']}")
                    uploader.terminate()
                    uploader.wait(2000)
            uploader.disconnect()
            task['uploader'] = None
        except Exception as e:
            self.log_message(f"Error cleaning up thread: {str(e)}")
            task['uploader'] = None

    @circuit_breaker_decorator(failure_threshold=3, recovery_timeout=30)
    def handle_database_operation(self, operation_func, *args, **kwargs):
        """Handle database operations with specific error handling"""
        connection = None
        try:
            connection = self.get_db_connection()
            return operation_func(connection, *args, **kwargs)
        except mysql.connector.Error as db_error:
            if db_error.errno == errorcode.CR_SERVER_LOST:
                self.log_message("Database connection lost, attempting reconnect...")
                self.db_manager.reconnect()
                return operation_func(connection, *args, **kwargs)
            else:
                self.log_message(f"Database error: {db_error}")
                raise
        except Exception as e:
            self.log_message(f"Unexpected error in database operation: {str(e)}")
            raise
        finally:
            if connection and connection != self.db_manager.connection:
                connection.close()

    @circuit_breaker_decorator(failure_threshold=5, recovery_timeout=60)
    def handle_aws_operation(self, operation_func, *args, **kwargs):
        """Handle AWS operations with specific error handling"""
        try:
            return operation_func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoCredentialsError':
                self.log_message("AWS credentials not found")
            elif error_code == 'AccessDenied':
                self.log_message("AWS access denied")
            else:
                self.log_message(f"AWS error: {error_code}")
            raise
        except BotoCoreError as e:
            self.log_message(f"AWS connection error: {str(e)}")
            raise

    def init_connection_pool(self):
        """Initialize database connection pool"""
        try:
            self.db_pool = pooling.MySQLConnectionPool(
                pool_name="uploader_pool",
                pool_size=5,
                pool_reset_session=True,
                **self.db_manager.rds_config
            )
            self.log_message("Database connection pool initialized successfully")
        except Exception as e:
            self.log_message(f"Failed to create connection pool: {str(e)}")
            self.db_pool = None

    def get_db_connection(self):
        """Get connection from pool"""
        try:
            if self.db_pool:
                return self.db_pool.get_connection()
            else:
                return self.db_manager.connection
        except Exception as e:
            self.log_message(f"Error getting database connection: {str(e)}")
            return self.db_manager.connection

    def batch_update_ui(self):
        """Update UI in batches for better performance"""
        if not self.pending_ui_updates:
            return
        
        try:
            # تحديث جميع المهام المعلقة
            for task_id in self.pending_ui_updates:
                task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
                if task:
                    self.update_task_list_internal(task)
            
            self.pending_ui_updates.clear()
            self.update_all_progress_bars()
            
        except Exception as e:
            self.log_message(f"Error in batch UI update: {str(e)}")