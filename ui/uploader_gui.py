#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import shutil
from datetime import datetime
from pathlib import Path
import boto3
from boto3.session import Session
from PyQt5.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, 
                            QHBoxLayout, QWidget, QLabel, QLineEdit, QProgressBar, 
                            QTextEdit, QFileDialog, QFrame, QMessageBox, QSystemTrayIcon,
                            QMenu, QDialog, QDateEdit, QComboBox, QListWidget, QListWidgetItem,
                            QTabWidget, QScrollArea, QGridLayout, QTextBrowser, QApplication,
                            QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog)
from PyQt5.QtCore import Qt, QThread, QSettings, QDate, QTimer
from PyQt5.QtGui import QIcon

from ui.photographers_dialog import PhotographersDialog
from ui.order_selector_dialog import OrderSelectorDialog
from ui.image_preview_dialog import ImagePreviewDialog
from ui.task_editor_dialog import TaskEditorDialog
from utils.background_uploader import BackgroundUploader

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
        self.aws_config = aws_config
        self.db_manager = db_manager
        self.user_info = user_info
        self.skip_state_load = skip_state_load
        self.auto_resume = auto_resume
        self.safe_mode = safe_mode
        self.load_all_tasks = load_all_tasks
        self.no_auto_login = no_auto_login
        
        # Set default application state
        self.upload_tasks = []
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
        self.local_storage_path = self.settings.value("local_storage_path", str(Path.home() / "Documents"))
        
        # Initialize AWS session
        self.init_aws_session()
        
        # Run initialization
        self.setWindowTitle("Secure File Uploader")
        self.setup_tray()
        self.init_ui()
        
        # Initialize database schema
        self.init_database_schema()
        
        # Check user authentication state
        if not user_info.get('is_logged_in', False):
            # Disable authenticated features on startup
            self.disable_authenticated_features()
        else:
            self.enable_authenticated_features()
        
        # Check previous shutdown status
        if not skip_state_load:
            self.check_previous_shutdown()
            
        # Save shutdown status
        self.update_app_status("running")
        
        # Load tasks from database if enabled
        self.load_tasks_from_database()
        
        # Auto-resume tasks if enabled
        if auto_resume and not safe_mode and not skip_state_load:
            self.log_message("Auto-resume is enabled, checking for paused tasks...")
            self.auto_resume_all_tasks()
            
        # Log application start
        if safe_mode:
            self.log_message("Running in safe mode with limited functionality")
        if skip_state_load:
            self.log_message("Skipping loading previous tasks and saved states")
        if no_auto_login:
            self.log_message("Automatic login is disabled")
    
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
        self.setWindowTitle('Secure File Uploader')
        self.setGeometry(100, 100, 900, 700)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # User info panel
        user_frame = QFrame()
        user_frame.setFrameShape(QFrame.StyledPanel)
        user_layout = QVBoxLayout()  # تغيير من QHBoxLayout إلى QVBoxLayout
        
        # قسم علوي يحتوي على ترحيب + زر تسجيل الدخول
        top_layout = QHBoxLayout()
        
        # Welcome label on the left
        self.user_info_label = QLabel(f"Welcome {self.user_info['Emp_FullName']}")
        top_layout.addWidget(self.user_info_label)
        
        # Spacer to push login button to the right
        top_layout.addStretch()
        
        # Login button on the right
        self.login_button = QPushButton("Logout" if self.user_info.get('is_logged_in', False) else "Login")
        self.login_button.clicked.connect(self.toggle_login)
        self.login_button.setMaximumWidth(80)  # جعل الزر أصغر
        top_layout.addWidget(self.login_button)
        
        # إضافة القسم العلوي إلى التصميم الرئيسي
        user_layout.addLayout(top_layout)
        
        # قسم سفلي يحتوي على Device ID تحت Welcome
        bottom_layout = QHBoxLayout()
        import getmac
        device_id_label = QLabel(f"Device ID: {getmac.get_mac_address()}")
        bottom_layout.addWidget(device_id_label)
        bottom_layout.addStretch()  # إضافة مسافة فارغة على اليمين
        
        # إضافة القسم السفلي إلى التصميم الرئيسي
        user_layout.addLayout(bottom_layout)
        
        user_frame.setLayout(user_layout)
        layout.addWidget(user_frame)
        
        # Tab widget for different functions
        self.tabs = QTabWidget()
        
        # Upload tab
        upload_tab = QWidget()
        upload_layout = QVBoxLayout()
        
        # Local storage path (only field kept from original UI)
        storage_frame = QFrame()
        storage_layout = QHBoxLayout()
        
        self.local_storage = QLineEdit()
        self.local_storage.setPlaceholderText("Select local storage path...")
        self.local_storage.setText(self.local_storage_path)
        self.local_storage.setReadOnly(True)
        storage_browse_btn = QPushButton('Browse')
        storage_browse_btn.clicked.connect(self.browse_local_storage)
        
        storage_layout.addWidget(QLabel('Local Storage Path:'))
        storage_layout.addWidget(self.local_storage)
        storage_layout.addWidget(storage_browse_btn)
        storage_frame.setLayout(storage_layout)
        upload_layout.addWidget(storage_frame)
        
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
        
        # Add today's uploads section
        today_uploads_frame = QFrame()
        today_uploads_layout = QVBoxLayout()
        
        today_uploads_label = QLabel("Today's Uploads:")
        today_uploads_label.setStyleSheet("font-weight: bold;")
        today_uploads_layout.addWidget(today_uploads_label)
        
        self.today_uploads_list = QListWidget()
        self.today_uploads_list.setMaximumHeight(120)  # Limit height
        today_uploads_layout.addWidget(self.today_uploads_list)
        
        refresh_today_btn = QPushButton('Refresh Today\'s Uploads')
        refresh_today_btn.clicked.connect(self.refresh_todays_uploads)
        today_uploads_layout.addWidget(refresh_today_btn)
        
        today_uploads_frame.setLayout(today_uploads_layout)
        upload_layout.addWidget(today_uploads_frame)
        
        # Task list for multiple uploads
        task_list_label = QLabel("Upload Tasks:")
        upload_layout.addWidget(task_list_label)
        
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(150)
        self.task_list.itemSelectionChanged.connect(self.on_task_selected)
        upload_layout.addWidget(self.task_list)
        
        # Progress bar and buttons
        self.progress_bar = QProgressBar()
        
        button_layout = QHBoxLayout()
        
        # Remove toggle progress mode button and permanently set to upload mode
        self.progress_mode = 'upload'  # Always show upload progress
        
        # Use Modify Task button in place of Add Upload Task
        self.modify_task_btn = QPushButton('Modify Task')
        self.modify_task_btn.clicked.connect(self.modify_selected_task)
        self.modify_task_btn.setEnabled(False)
        
        self.start_all_btn = QPushButton('Start All Tasks')
        self.start_all_btn.clicked.connect(self.start_all_tasks)
        self.start_all_btn.setEnabled(False)
        
        # Buttons for pause, resume, restart
        self.pause_btn = QPushButton('Pause Task')
        self.pause_btn.clicked.connect(self.pause_selected_task)
        self.pause_btn.setEnabled(False)
        
        self.resume_btn = QPushButton('Resume Task')
        self.resume_btn.clicked.connect(self.resume_selected_task)
        self.resume_btn.setEnabled(False)
        
        self.restart_btn = QPushButton('Restart Task')
        self.restart_btn.clicked.connect(self.restart_selected_task)
        self.restart_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton('Cancel Selected')
        self.cancel_btn.clicked.connect(self.cancel_selected_task)
        self.cancel_btn.setEnabled(False)
        
        # Add delete button
        self.delete_btn = QPushButton('Delete Task')
        self.delete_btn.clicked.connect(self.delete_selected_task)
        self.delete_btn.setEnabled(False)
        
        # Add buttons in logical order
        button_layout.addWidget(self.modify_task_btn)
        button_layout.addWidget(self.start_all_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.resume_btn)
        button_layout.addWidget(self.restart_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.delete_btn)
        
        upload_layout.addWidget(self.progress_bar)
        upload_layout.addLayout(button_layout)
        
        # Log area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
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
        self.activity_table.horizontalHeader().setStretchLastSection(True)
        self.activity_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        
        activity_layout.addWidget(self.activity_table)
        
        activity_tab.setLayout(activity_layout)
        
        # Add tabs to widget
        self.tabs.addTab(upload_tab, "Upload Files")
        self.tabs.addTab(history_tab, "Upload History")
        self.tabs.addTab(activity_tab, "Activity Log")
        
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
                self.user_info_label.setText("Not logged in")
                
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
                    self.user_info_label.setText(f"Welcome {self.user_info['Emp_FullName']}")
                    
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
                    self.user_info_label.setText(f"Welcome {self.user_info['Emp_FullName']}")
                    
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
        # Disable buttons that require authentication
        self.upload_photoshoot_btn.setEnabled(False)
        
        # Start Task and Resume Task buttons don't need authentication anymore
        # self.start_all_btn.setEnabled(False)
        # self.pause_btn.setEnabled(False)
        # self.resume_btn.setEnabled(False)
        # self.restart_btn.setEnabled(False)
        
        # These still need authentication
        self.cancel_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.modify_task_btn.setEnabled(False)
    
    def enable_authenticated_features(self):
        """Enable features that require authentication"""
        # Enable buttons that may be used after authentication
        self.upload_photoshoot_btn.setEnabled(True)
        
        # The other buttons depend on task selection state,
        # so we'll update them based on the current selection
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
            cursor.close()
            
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
                cursor.close()
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
            cursor.close()
            
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
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'icon.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.log_message(f"Warning: Icon file not found at {icon_path}")
        
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show)
        quit_action = tray_menu.addAction("Exit")
        quit_action.triggered.connect(self.quit_app)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    def log_message(self, message):
        """Add a timestamped message to the log area"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store the message in a console log for debugging
        print(f"[{timestamp}] {message}")
        
        # Safely append to log_text if it exists
        if hasattr(self, 'log_text') and self.log_text is not None:
            self.log_text.append(f"[{timestamp}] {message}")
        else:
            # If log_text doesn't exist yet, store message in a queue to be displayed later
            if not hasattr(self, '_pending_log_messages'):
                self._pending_log_messages = []
            self._pending_log_messages.append(f"[{timestamp}] {message}")
    
    def browse_local_storage(self):
        """Browse for local storage location"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Local Storage Location')
        if folder:
            self.local_storage.setText(folder)
            self.local_storage_path = folder
            self.settings.setValue("local_storage_path", folder)
            self.log_message(f"Local storage location set to: {folder}")
    
    def handle_completed_task_resubmission(self, task_data, existing_task):
        """
        Handle the scenario where a user is trying to resubmit a task that was previously completed
        
        Args:
            task_data (dict): New task data the user is trying to add
            existing_task (dict): Existing completed task from the database
            
        Returns:
            bool: True if the task should be resubmitted, False if it should be skipped
        """
        # If the task is not completed, always allow resubmission
        if existing_task.get('status', '').lower() != 'completed':
            return True
            
        # Create a message about the existing completed task
        folder_path = existing_task.get('folder_path', '')
        completion_date = existing_task.get('completed_at', '')
        completion_date_str = f" on {completion_date}" if completion_date else ""
        
        message = (f"Order {task_data['order_number']} was already successfully uploaded{completion_date_str}.\n\n"
                  f"Original folder: {folder_path}\n"
                  f"Completed by: {existing_task.get('last_action_by', 'Unknown')}\n\n"
                  f"What would you like to do?")
        
        # Create a message box with options
        from PyQt5.QtWidgets import QMessageBox
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Task Already Completed")
        msgBox.setText(message)
        
        # Add buttons for different actions
        resumeButton = msgBox.addButton("Resume as New Task", QMessageBox.ActionRole)
        scanButton = msgBox.addButton("Scan for Missing Files", QMessageBox.ActionRole)
        cancelButton = msgBox.addButton("Cancel", QMessageBox.RejectRole)
        
        # Set the default button
        msgBox.setDefaultButton(cancelButton)
        
        # Execute the dialog
        msgBox.exec_()
        
        # Handle the user's choice
        clickedButton = msgBox.clickedButton()
        
        if clickedButton == resumeButton:
            # Create a fresh task, ignoring the completed status
            self.log_message(f"User chose to add order {task_data['order_number']} as a new task despite previous completion")
            return True
            
        elif clickedButton == scanButton:
            # Create a temporary task object for scanning
            temp_task = {
                'order_number': task_data['order_number'],
                'folder_path': task_data['folder_path'],
                'local_path': task_data['local_path'],
                'order_date': task_data['order_date']
            }
            
            # Show a scanning dialog
            from PyQt5.QtWidgets import QProgressDialog
            progress = QProgressDialog("Scanning for missing files...", "Cancel", 0, 0, self)
            progress.setWindowTitle("File Scan")
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(0)
            progress.show()
            
            # Process events to make sure the dialog appears
            QApplication.processEvents()
            
            # Scan for missing files
            self.log_message(f"Scanning for missing files in order {task_data['order_number']}")
            scan_results = self.scan_for_missing_files(temp_task)
            
            # Close the progress dialog
            progress.close()
            
            if not scan_results:
                QMessageBox.warning(
                    self,
                    "Scan Failed",
                    "The scan for missing files failed. Please check the logs for details."
                )
                return False
                
            if scan_results['missing_files'] == 0:
                # No missing files found
                QMessageBox.information(
                    self,
                    "No Missing Files",
                    f"All {scan_results['total_files']} files appear to be already uploaded to AWS S3.\n\n"
                    f"If you still want to create a new task, click 'Resume as New Task' instead."
                )
                return False
            else:
                # Missing files found - ask user if they want to create a task for just these files
                reply = QMessageBox.question(
                    self,
                    "Missing Files Found",
                    f"Found {scan_results['missing_files']} files out of {scan_results['total_files']} "
                    f"that have not been uploaded to AWS S3.\n\n"
                    f"Would you like to create a task to upload only these missing files?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Add the missing files list to the task data so it can be used by the uploader
                    task_data['missing_files'] = scan_results['missing_file_list']
                    task_data['upload_missing_only'] = True
                    
                    # Show some example missing files
                    examples = scan_results['missing_file_list'][:5]
                    example_str = "\n".join([f"- {ex}" for ex in examples])
                    
                    if len(scan_results['missing_file_list']) > 5:
                        example_str += f"\n- And {len(scan_results['missing_file_list']) - 5} more..."
                    
                    QMessageBox.information(
                        self,
                        "Task Created for Missing Files",
                        f"A task will be created to upload only the {scan_results['missing_files']} missing files.\n\n"
                        f"Examples of missing files:\n{example_str}"
                    )
                    return True
                else:
                    return False
            
        else:  # Cancel button or dialog closed
            self.log_message(f"User cancelled adding duplicate task for order {task_data['order_number']}")
            return False
    
    def add_photoshoot_task(self):
        """Open dialog for adding a new photoshoot upload task"""
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        if not self.local_storage_path:
            QMessageBox.warning(self, "Warning", "Please select a local storage location first")
            self.browse_local_storage()
            if not self.local_storage_path:
                return
        
        dialog = TaskEditorDialog(self.db_manager, self.local_storage_path, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            # Get task data from dialog
            task_data = dialog.get_task_data()
            
            # Check if the task with this order number already exists in the database
            try:
                if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                    self.db_manager.connect()
                
                # Find the correct primary key for the upload_tasks table
                cursor = self.db_manager.connection.cursor(dictionary=True)
                
                # Check for task_id or id column
                cursor.execute("""
                SELECT COLUMN_NAME 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'upload_tasks' 
                AND COLUMN_NAME IN ('task_id', 'id')
                """, (self.db_manager.rds_config['database'],))
                
                id_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
                id_column = 'task_id' if 'task_id' in id_columns else id_columns[0] if id_columns else 'id'
                
                # Check if this order exists in the database
                query = f"""
                SELECT {id_column} as task_id, order_number, folder_path, status, completed_at, last_action_by
                FROM upload_tasks 
                WHERE order_number = %s
                """
                cursor.execute(query, (task_data['order_number'],))
                existing_task = cursor.fetchone()
                cursor.close()
                
                if existing_task:
                    # We found this task already exists in the database
                    # Check if it's completed and handle accordingly
                    if not self.handle_completed_task_resubmission(task_data, existing_task):
                        return  # User chose not to proceed with task creation
                    
                    # If we get here, user wants to proceed with the task
                    # The existing task details will be retrieved from the database
                    # in the task creation code below
            except Exception as e:
                self.log_message(f"Error checking for existing task: {str(e)}")
                import traceback
                self.log_message(traceback.format_exc())
            
            # Also check if the task is already in our current list
            for task in self.upload_tasks:
                if task['order_number'] == task_data['order_number']:
                    # Ask user if they want to modify the existing task or create a new one
                    from PyQt5.QtWidgets import QMessageBox
                    reply = QMessageBox.question(
                        self, 
                        'Task Already Exists', 
                        f'A task for Order {task_data["order_number"]} already exists in the current session.\n\n'
                        f'Status: {task["status"].capitalize()}\n'
                        f'Progress: {task.get("progress", 0)}%\n\n'
                        f'Do you want to modify the existing task instead?',
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        QMessageBox.Yes
                    )
                    
                    if reply == QMessageBox.Yes:
                        # Find the task item and select it
                        for i in range(self.task_list.count()):
                            item = self.task_list.item(i)
                            task_id = item.data(Qt.UserRole)
                            if isinstance(task_id, int) and task_id == task['id']:
                                self.task_list.setCurrentItem(item)
                                self.modify_selected_task()
                                return
                                
                    elif reply == QMessageBox.Cancel:
                        return
                        
                    # If No, we'll continue creating a new task
                    break
            
            # Create a unique task ID
            task_id = len(self.upload_tasks) + 1
            
            # Create a task item for the list
            task_item = QListWidgetItem()
            task_item.setText(f"Task {task_id}: Order {task_data['order_number']} - Pending")
            
            # Store only the task ID directly
            task_item.setData(Qt.UserRole, task_id)
            
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
                'local_path': task_data['local_path']
            }
            
            # Save task to database
            db_id = self.save_task_to_database(task)
            if db_id:
                task['db_id'] = db_id
            
            # Store the task data
            self.upload_tasks.append(task)
            
            # Enable the start all button if we have tasks
            self.start_all_btn.setEnabled(len(self.upload_tasks) > 0)
            
            self.log_message(f"Added new photoshoot task {task_id} for order {task_data['order_number']}")
    
    def modify_selected_task(self):
        """Open dialog for modifying the selected task"""
        # Check if user is logged in first
        if not self.ensure_user_logged_in():
            return
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Information", "No task selected")
            return
        
        task_data = selected_items[0].data(Qt.UserRole)
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
                task['item'].setData(Qt.UserRole, task['id'])
            
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
        task_data = selected_items[0].data(Qt.UserRole)
        
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
        
        self.log_message(f"Selected task {task_id} in state: {task['status']}")
        
        # Start, Resume, Restart buttons are always enabled regardless of login status
        # Enable/disable buttons based on task status
        if task['status'] == 'running':
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
        elif task['status'] == 'paused':
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.restart_btn.setEnabled(False)
        elif task['status'] in ['completed', 'cancelled']:
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
        elif task['status'] == 'pending':
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)  # Enable restart for pending tasks
    
    def start_all_tasks(self):
        """Start all pending upload tasks"""
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        pending_tasks = [task for task in self.upload_tasks if task['status'] == 'pending']
        
        if not pending_tasks:
            QMessageBox.information(self, "Information", "No pending tasks to start")
            return
        
        for task in pending_tasks:
            self.start_task(task)
        
        self.cancel_btn.setEnabled(True)
    
    def start_task(self, task):
        """
        Start a specific upload task
        """
        try:
            if not task:
                return
            
            # Check if we have the required data
            if not task.get('local_path'):
                self.log_message(f"Error: Local storage path missing for task {task.get('order_number')}")
                return
            
            # Validate paths before starting
            if not os.path.exists(task['local_path']):
                self.log_message(f"Warning: Local storage path does not exist: {task['local_path']}")
                reply = QMessageBox.question(
                    self, 
                    "Path Not Found", 
                    f"Local storage path for task {task['order_number']} does not exist:\n{task['local_path']}\n\nDo you want to update it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Open folder selection dialog
                    new_folder = QFileDialog.getExistingDirectory(
                        self, 
                        f'Select local storage folder for task {task["order_number"]}'
                    )
                    if new_folder:
                        task['local_path'] = new_folder
                        self.log_message(f"Updated local storage path to: {new_folder}")
                        
                        # Update database
                        self.save_task_to_database(task)
                    else:
                        self.log_message("No folder selected, cannot start task")
                        return
                else:
                    return
            
            # Check AWS session before starting
            if self.aws_session is None:
                self.log_message("Error: No AWS session available, cannot upload")
                
                # Si estamos en modo seguro, crear sesión simulada sin preguntar
                if self.safe_mode:
                    self.log_message("Running in safe mode - creating mock AWS session")
                    self.aws_session = type('MockSession', (), {
                        'client': lambda *args, **kwargs: None,
                        'bucket_name': 'mock-bucket'
                    })
                else:
                    # Solo mostrar diálogo si no estamos en modo seguro
                    # Ask if the user wants to configure AWS credentials
                    reply = QMessageBox.question(
                        self,
                        "AWS Configuration Required",
                        "AWS credentials are missing or invalid. Would you like to configure them now?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    
                    if reply == QMessageBox.Yes:
                        # Show a dialog to configure AWS credentials
                        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout
                        
                        aws_dialog = QDialog(self)
                        aws_dialog.setWindowTitle("Configure AWS Credentials")
                        layout = QVBoxLayout()
                        
                        form_layout = QFormLayout()
                        
                        # AWS access key input
                        aws_access_key_input = QLineEdit()
                        aws_access_key_input.setText(os.environ.get("AWS_ACCESS_KEY_ID", ""))
                        form_layout.addRow("AWS Access Key ID:", aws_access_key_input)
                        
                        # AWS secret key input
                        aws_secret_key_input = QLineEdit()
                        aws_secret_key_input.setText(os.environ.get("AWS_SECRET_ACCESS_KEY", ""))
                        form_layout.addRow("AWS Secret Access Key:", aws_secret_key_input)
                        
                        # AWS region input
                        aws_region_input = QLineEdit()
                        aws_region_input.setText(os.environ.get("AWS_REGION", "us-east-1"))
                        form_layout.addRow("AWS Region:", aws_region_input)
                        
                        # AWS bucket input
                        aws_bucket_input = QLineEdit()
                        aws_bucket_input.setText(os.environ.get("AWS_S3_BUCKET", "balistudiostorage"))
                        form_layout.addRow("S3 Bucket:", aws_bucket_input)
                        
                        layout.addLayout(form_layout)
                        
                        # Buttons
                        button_layout = QHBoxLayout()
                        save_btn = QPushButton("Save")
                        cancel_btn = QPushButton("Cancel")
                        
                        button_layout.addWidget(save_btn)
                        button_layout.addWidget(cancel_btn)
                        layout.addLayout(button_layout)
                        
                        aws_dialog.setLayout(layout)
                        
                        # Connect buttons
                        save_btn.clicked.connect(aws_dialog.accept)
                        cancel_btn.clicked.connect(aws_dialog.reject)
                        
                        # Show dialog
                        if aws_dialog.exec_() == QDialog.Accepted:
                            # Save AWS credentials to environment variables
                            os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key_input.text()
                            os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_key_input.text()
                            os.environ["AWS_REGION"] = aws_region_input.text()
                            os.environ["AWS_S3_BUCKET"] = aws_bucket_input.text()
                            
                            # Update aws_config
                            self.aws_config["AWS_ACCESS_KEY_ID"] = aws_access_key_input.text()
                            self.aws_config["AWS_SECRET_ACCESS_KEY"] = aws_secret_key_input.text()
                            self.aws_config["AWS_REGION"] = aws_region_input.text()
                            self.aws_config["AWS_S3_BUCKET"] = aws_bucket_input.text()
                            
                            # Reinitialize AWS session
                            self.init_aws_session()
                            
                            if self.aws_session is None:
                                self.log_message("Failed to initialize AWS session with provided credentials")
                                QMessageBox.warning(self, "AWS Error", "Failed to initialize AWS session with provided credentials. Please check your credentials and try again.")
                                return
                        else:
                            self.log_message("AWS configuration cancelled")
                            return
                    else:
                        self.log_message("AWS configuration skipped, cannot upload")
                        return
            
            # Update task status to running
            task['status'] = 'running'
            self.update_task_list(task)
            
            # Check if there's an existing BackgroundUploader instance
            if task.get('uploader') and task['uploader'].isRunning():
                # Resume existing uploader
                self.log_message(f"Resuming existing task for order {task['order_number']}")
                try:
                    task['uploader'].resume()
                except Exception as e:
                    self.log_message(f"Error resuming existing task: {str(e)}")
                    # Clean up task and recreate it
                    task['uploader'] = None
                    # We'll create a new task in the steps below
                return
            
            # Clean up previous thread if it exists
            if task.get('uploader') is not None:
                self.log_message(f"Cleaning up old thread for order {task['order_number']}")
                try:
                    # Make sure old thread is stopped
                    if task['uploader'].isRunning():
                        task['uploader'].stop()
                        task['uploader'].wait(1000)  # Wait one second for termination
                    task['uploader'] = None
                except Exception as e:
                    self.log_message(f"Warning: Error cleaning up old thread: {str(e)}")
                    task['uploader'] = None
            
            # Short delay to ensure cleanup is complete
            import time
            time.sleep(0.1)
            
            # Check if we have a list of missing files to upload
            missing_files_list = None
            if 'missing_files' in task and task.get('upload_missing_only', False):
                missing_files_list = task['missing_files']
                self.log_message(f"Uploading {len(missing_files_list)} missing files for order {task['order_number']}")
            
            # Create a new uploader or recreate one from saved state
            state_file = Path.home() / '.aws_uploader' / f"task_state_{task['order_number']}.json"
            if state_file.exists():
                self.log_message(f"Found state file for order {task['order_number']}")
                
                try:
                    # Create the BackgroundUploader with basic parameters
                    uploader = BackgroundUploader(
                        task['folder_path'],
                        task['order_number'],
                        task['order_date'],
                        self.aws_session,
                        task['photographers'],
                        task['local_path'],
                        self,
                        missing_files_list=missing_files_list
                    )
                    
                    # Connect signals with task_id in a safer way - use weaker connections to prevent memory issues
                    try:
                        uploader.progress.connect(lambda current, total, task_id=task['id']: 
                                self.update_task_progress(task_id, current, total))
                        uploader.log.connect(lambda message, task_id=task['id']: 
                                self.log_task_message(task_id, message))
                        uploader.finished.connect(lambda task_id=task['id']: 
                                self.task_finished(task_id))
                    except Exception as signal_error:
                        self.log_message(f"Error connecting signals: {str(signal_error)}")
                    
                    # Set the uploader in the task
                    task['uploader'] = uploader
                    
                    # Try to load state in UI before starting
                    try:
                        with open(state_file, 'r') as f:
                            state = json.load(f)
                            
                        # Update progress in UI
                        if 'current_file_index' in state and 'total_files' in state:
                            progress = (state['current_file_index'] / max(state['total_files'], 1)) * 100
                            task['progress'] = progress
                            self.log_message(f"Resuming upload at {progress:.1f}% ({state['current_file_index']}/{state['total_files']})")
                    except Exception as state_error:
                        self.log_message(f"Error loading state file: {str(state_error)}")
                        
                    # Update task in UI
                    self.update_task_list(task)
                    
                    # Additional delay before starting thread
                    time.sleep(0.5)
                    
                    # Start the thread
                    self.log_message(f"Starting upload for order {task['order_number']} (resuming from saved state)")
                    task['uploader'].start()
                    
                except Exception as e:
                    self.log_message(f"Error resuming task from state file: {str(e)}")
                    import traceback
                    self.log_message(traceback.format_exc())
                    
                    # Set task to error state
                    task['status'] = 'error'
                    self.update_task_list(task)
                
            else:
                # No saved state, create a new uploader
                self.log_message(f"Starting new upload for order {task['order_number']}")
                
                try:
                    # Create the BackgroundUploader
                    uploader = BackgroundUploader(
                        task['folder_path'],
                        task['order_number'],
                        task['order_date'],
                        self.aws_session,
                        task['photographers'],
                        task['local_path'],
                        self,
                        missing_files_list=missing_files_list
                    )
                    
                    # Connect signals with task_id
                    uploader.progress.connect(lambda current, total, task_id=task['id']: 
                            self.update_task_progress(task_id, current, total))
                    uploader.log.connect(lambda message, task_id=task['id']: 
                            self.log_task_message(task_id, message))
                    uploader.finished.connect(lambda task_id=task['id']: 
                            self.task_finished(task_id))
                    
                    # Set the uploader in the task
                    task['uploader'] = uploader
                    
                    # Save state before starting
                    try:
                        self.save_task_to_database(task)
                    except Exception as db_error:
                        self.log_message(f"Warning: Error saving task to database: {str(db_error)}")
                    
                    # Additional delay before starting thread
                    time.sleep(0.5)
                    
                    # Start the thread
                    task['uploader'].start()
                except Exception as e:
                    self.log_message(f"Error starting new task: {str(e)}")
                    import traceback
                    self.log_message(traceback.format_exc())
                    task['status'] = 'error'
                    self.update_task_list(task)
            
            # Update buttons
            self.update_buttons_state()
            
        except Exception as e:
            self.log_message(f"Error starting task: {str(e)}")
            task['status'] = 'error'
            self.update_task_list(task)
            import traceback
            self.log_message(traceback.format_exc())
    
    def update_task_progress(self, task_id, current, total):
        """
        Update progress for a specific task
        
        Args:
            task_id (int): Task ID
            current (int): Current progress
            total (int): Total items
        """
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            return
        
        # Safety check for invalid values
        if total <= 0:
            self.log_message(f"Warning: Total value for task {task_id} is zero or negative: {total}")
            # Set percentage to 0 or current value depending on current
            if current <= 0:
                percentage = 0
            else:
                # Keep previous percentage or set to some nominal value
                percentage = task.get('progress', 0)
        else:
            # Calculate percentage based on progress mode
            if hasattr(task, 'uploader') and task.get('uploader'):
                uploader = task.get('uploader')
                if self.progress_mode == 'upload' and hasattr(uploader, 'uploaded_file_count'):
                    # Use actual uploaded files count for progress
                    percentage = round((uploader.uploaded_file_count / total) * 100)
                else:
                    # Use current file index (scanning progress)
                    percentage = round((current / total) * 100)
            else:
                # Fallback to standard calculation
                percentage = round((current / total) * 100)
        
        # Clamp percentage to valid range
        percentage = max(0, min(100, percentage))
        task['progress'] = percentage
        
        # Update the list item if it exists
        if 'item' in task and task['item']:
            # Display mode in the task text
            mode_text = "uploading" if self.progress_mode == 'upload' else "scanning"
            task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Running ({percentage}% {mode_text})")
        
        # Update the main progress bar with average progress of all running tasks
        running_tasks = [t for t in self.upload_tasks if t['status'] == 'running']
        if running_tasks:
            avg_progress = sum(t['progress'] for t in running_tasks) / len(running_tasks)
            self.progress_bar.setValue(round(avg_progress))
    
    def log_task_message(self, task_id, message):
        """
        Log a message for a specific task
        
        Args:
            task_id (int): Task ID
            message (str): Message to log
        """
        self.log_message(f"Task {task_id}: {message}")
    
    def task_finished(self, task_id):
        """
        Handle completion of a specific task
        
        Args:
            task_id (int): Finished task ID
        """
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            return
        
        # Update task status
        task['status'] = 'completed'
        task['progress'] = 100
        
        # Update the list item if it exists
        if 'item' in task and task['item']:
            task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Completed")
        
        # Save completed status to database
        self.save_task_to_database(task)
        
        # Enable restart button for completed tasks
        self.restart_btn.setEnabled(True)
        
        # Check if all tasks are completed
        if all(t['status'] in ['completed', 'cancelled'] for t in self.upload_tasks):
            self.all_tasks_finished()
        
        # Refresh the upload history
        self.load_upload_history()
    
    def all_tasks_finished(self):
        """Handle completion of all tasks"""
        self.progress_bar.setValue(100)
        self.cancel_btn.setEnabled(False)
        self.log_message("All upload tasks completed")
        
        self.tray_icon.showMessage(
            "All Uploads Complete",
            "All file upload tasks completed successfully",
            QSystemTrayIcon.Information,
            2000
        )
    
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
        
        task_id = selected_items[0].data(Qt.UserRole)
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

    def resume_selected_task(self):
        """
        Resume the selected upload task
        """
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_id = selected_items[0].data(Qt.UserRole)
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

    def restart_selected_task(self):
        """
        Restart the selected upload task from the beginning
        """
        # لا نحتاج للتحقق من تسجيل الدخول
        # تم إزالة الشرط الذي يتحقق من تسجيل الدخول
            
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            return
        
        task_id = selected_items[0].data(Qt.UserRole)
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
            task['uploader'].stop()
            # Wait for thread to finish
            if not task['uploader'].wait(1000):
                self.log_message("Warning: Uploader thread did not stop properly")
        
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
        
        task_data = selected_items[0].data(Qt.UserRole)
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
            task['uploader'].stop()
            
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
            
        task_data = selected_items[0].data(Qt.UserRole)
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
            task['uploader'].stop()
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
                cursor.close()
                
                self.log_message(f"Deleted task for order {task['order_number']} from database")
                self.log_activity("task", "delete_db", 
                                f"Deleted task for order {task['order_number']} from database", 
                                self.user_info.get('Emp_FullName'))
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
        self.start_all_btn.setEnabled(any(t['status'] == 'pending' for t in self.upload_tasks))
    
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
            local_path = str(task.get('local_path', folder_path)) or folder_path
            
            # Check if task already exists in the database by order number
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            # Find the correct primary key for the upload_tasks table
            cursor.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME IN ('task_id', 'id')
            """, (self.db_manager.rds_config['database'],))
            
            id_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
            id_column = 'task_id' if 'task_id' in id_columns else id_columns[0] if id_columns else 'id'
            
            # Check if task already exists
            cursor.execute(f"""
            SELECT {id_column} as task_id 
            FROM upload_tasks 
            WHERE order_number = %s
            """, (task['order_number'],))
            
            existing_task = cursor.fetchone()
            
            # Initialize params
            params = [
                task.get('status', 'pending'),
                task.get('progress', 0),
                folder_path,
                local_path,
                task['order_number'],
                state_path,
                self.user_info.get('Emp_FullName'),
                task.get('order_date', None)
            ]
            
            # Include photographer IDs if available
            if 'photographers' in task:
                params.extend([
                    task['photographers'].get('main'),
                    task['photographers'].get('assistant'),
                    task['photographers'].get('video')
                ])
            else:
                params.extend([None, None, None])
                
            # Add completion timestamp if task is completed
            completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if task.get('status') == 'completed' else None
            params.append(completed_at)
            
            # Add the last person who took action on this task, if available
            last_action_by = task.get('last_action_by', self.user_info.get('Emp_FullName'))
            params.append(last_action_by)
            
            if existing_task:
                # Update the existing task
                self.log_message(f"Updating existing database entry for order {task['order_number']}")
                
                # Calculate which fields to update
                update_query = f"""
                UPDATE upload_tasks SET 
                status = %s, 
                progress = %s,
                folder_path = %s,
                local_path = %s,
                state_file_path = %s,
                updated_by = %s,
                order_date = %s,
                main_photographer_id = %s,
                assistant_photographer_id = %s,
                video_photographer_id = %s,
                completed_at = %s,
                last_action_by = %s,
                updated_at = NOW()
                WHERE {id_column} = %s
                """
                
                # Add task ID to params
                params.append(existing_task['task_id'])
                
                # Execute the update
                cursor.execute(update_query, params)
                self.db_manager.connection.commit()
                
                # Store the database ID in the task
                db_id = existing_task['task_id']
                task['db_id'] = db_id
                
            else:
                # Insert as a new task
                self.log_message(f"Inserting new database entry for order {task['order_number']}")
                
                # Create the insert query
                fields = [
                    "status", "progress", "folder_path", "local_path", "order_number", 
                    "state_file_path", "created_by", "order_date", 
                    "main_photographer_id", "assistant_photographer_id", "video_photographer_id",
                    "completed_at", "last_action_by"
                ]
                
                placeholders = ", ".join(["%s"] * len(fields))
                fields_str = ", ".join(fields)
                
                insert_query = f"INSERT INTO upload_tasks ({fields_str}, created_at) VALUES ({placeholders}, NOW())"
                
                # Execute the insert
                cursor.execute(insert_query, params)
                self.db_manager.connection.commit()
                
                # Get the new task ID
                db_id = cursor.lastrowid
                task['db_id'] = db_id
                
            cursor.close()
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
        """
        Load saved tasks from database and state files
        """
        try:
            # If skip_state_load is enabled, don't load saved tasks
            if self.skip_state_load:
                self.log_message("Skipping loading previous tasks and saved states")
                return
                
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
            
            self.log_message("Searching for saved tasks...")

            # Create a tracking set of all order numbers already loaded
            # to avoid duplicates from different sources
            loaded_order_numbers = set()
            
            # Get all order numbers already in memory
            for task in self.upload_tasks:
                loaded_order_numbers.add(task['order_number'])
            
            # Load tasks from database if load_all_tasks is enabled
            if hasattr(self, 'load_all_tasks') and self.load_all_tasks:
                self.log_message("Loading ALL incomplete tasks from database...")
                try:
                    # Find the correct primary key for the upload_tasks table
                    cursor = self.db_manager.connection.cursor(dictionary=True)
                    
                    # Check for task_id or id column
                    cursor.execute("""
                    SELECT COLUMN_NAME 
                    FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = %s 
                    AND TABLE_NAME = 'upload_tasks' 
                    AND COLUMN_NAME IN ('task_id', 'id')
                    """, (self.db_manager.rds_config['database'],))
                    
                    id_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
                    
                    if not id_columns:
                        self.log_message("Error: Could not find ID column in upload_tasks table")
                        cursor.close()
                    else:
                        # Use the first ID column found (prioritize task_id if both exist)
                        id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
                        self.log_message(f"Using database column '{id_column}' for task identification")
                        
                        # Get environment variables to control task loading behavior
                        load_completed = os.environ.get('LOAD_COMPLETED_TASKS', '0') == '1'
                        ignore_completed = os.environ.get('IGNORE_COMPLETED_TASKS', '1') == '1'
                        
                        # Log loading criteria
                        if load_completed:
                            self.log_message("Including completed tasks in loading")
                        elif ignore_completed:
                            self.log_message("Ignoring completed tasks as configured")
                        
                        # Query the database for incomplete tasks
                        query = f"""
                        SELECT {id_column} as task_id, order_number, folder_path, local_path, 
                               status, progress, created_at, order_date, 
                               main_photographer_id, assistant_photographer_id, video_photographer_id
                        FROM upload_tasks 
                        WHERE 1=1
                        """
                        
                        # Add status filter if not loading all tasks
                        if not load_completed and ignore_completed:
                            query += " AND status != 'completed' AND status != 'cancelled'"
                        
                        # Execute the query
                        cursor.execute(query)
                        
                        # Process the results
                        results = cursor.fetchall()
                        self.log_message(f"Found {len(results)} tasks in database matching criteria")
                        
                        loaded_count = 0
                        skipped_count = 0
                        
                        for db_task in results:
                            # Access data using dictionary keys
                            order_number = db_task['order_number']
                            
                            # Skip tasks that are already in the list
                            if order_number in loaded_order_numbers:
                                skipped_count += 1
                                self.log_message(f"Task for order {order_number} already exists, skipping")
                                continue
                            
                            # Add this order to our tracking set
                            loaded_order_numbers.add(order_number)
                            
                            folder_path = db_task.get('folder_path', '')
                            local_path = db_task.get('local_path', folder_path) or folder_path
                            task_status = db_task.get('status', 'paused')
                            progress = db_task.get('progress', 0)
                            
                            # Check if the folder path exists
                            path_exists = os.path.exists(folder_path) if folder_path else False
                            if not path_exists and os.path.exists(local_path):
                                path_exists = True
                                folder_path = local_path
                            
                            if not path_exists:
                                self.log_message(f"Warning: Path does not exist for order {order_number}: {folder_path}")
                            
                            # Create a task object
                            task_id = len(self.upload_tasks) + 1
                            task = {
                                'id': task_id,
                                'order_number': order_number,
                                'folder_path': folder_path,
                                'local_path': local_path or folder_path,
                                'status': task_status,
                                'progress': progress,
                                'uploader': None,
                                'photographers': {
                                    'main': db_task.get('main_photographer_id'),
                                    'assistant': db_task.get('assistant_photographer_id'),
                                    'video': db_task.get('video_photographer_id')
                                },
                                'order_date': self._parse_safe_date(db_task.get('order_date')),
                                'path_exists': path_exists,
                                'db_task_id': db_task['task_id']
                            }
                            
                            # Add task to list and update UI
                            self.upload_tasks.append(task)
                            self.update_task_list(task)
                            loaded_count += 1
                            self.log_message(f"Added task for order {order_number} from database (status: {task_status})")
                        
                        self.log_message(f"Database load summary: Added {loaded_count} tasks, skipped {skipped_count} duplicates")
                        cursor.close()
                except Exception as e:
                    self.log_message(f"Error loading tasks from database: {str(e)}")
                    import traceback
                    self.log_message(traceback.format_exc())
            
            # First, scan for any state files that might indicate interrupted uploads
            state_dir = Path.home() / '.aws_uploader'
            if state_dir.exists():
                self.log_message(f"Searching for state files in: {state_dir}")
                state_files = list(state_dir.glob("task_state_*.json"))
                if state_files:
                    self.log_message(f"Found {len(state_files)} saved state files")
                    
                    for state_file in state_files:
                        try:
                            # Check if file has one of our error extensions
                            if any(state_file.name.endswith(ext) for ext in ['.corrupted', '.error', '.invalid', '.bak']):
                                self.log_message(f"Ignoring suspicious state file: {state_file.name}")
                                continue
                            
                            # Validate the state file
                            state = self.validate_state_file(state_file)
                            if not state:
                                self.log_message(f"Ignoring corrupted state file: {state_file.name}")
                                continue
                                
                            # Parse order number from filename (task_state_135547.json -> 135547)
                            try:
                                order_number = state_file.stem.split('_')[-1]
                                
                                # Additional validation on order_number
                                if not order_number or not order_number.isdigit():
                                    self.log_message(f"Invalid order number in filename: {state_file.name}")
                                    continue
                                
                                # Skip if we already have this order in our tasks
                                if order_number in loaded_order_numbers:
                                    self.log_message(f"Task for order {order_number} already loaded, skipping state file")
                                    continue
                                
                                # Add to tracking set
                                loaded_order_numbers.add(order_number)
                                
                                self.log_message(f"Loading state for order number: {order_number}")
                            except (IndexError, ValueError) as e:
                                self.log_message(f"Error parsing order number from filename {state_file.name}: {str(e)}")
                                continue
                            
                            # Rest of the code remains the same
                            # Check for required fields in state file
                            required_fields = ['order_number', 'folder_path']
                            missing_fields = [field for field in required_fields if field not in state]
                            
                            if missing_fields:
                                self.log_message(f"State file missing essential fields: {', '.join(missing_fields)}")
                                continue
                            
                            # Make sure values are the correct type to prevent crashes
                            if not isinstance(state.get('order_number'), str):
                                self.log_message(f"Order number type incorrect (required: text): {type(state.get('order_number'))}")
                                state['order_number'] = str(state.get('order_number', order_number))
                                
                            # Get last saved timestamp for debugging
                            last_saved = state.get('last_saved', 'Unknown')
                            self.log_message(f"Last state update: {last_saved}")
                            
                            # Set safe default values for progress tracking
                            total_files = max(1, state.get('total_files', 1))
                            current_file_index = min(max(0, state.get('current_file_index', 0)), total_files)
                            
                            # Calculate safe progress percentage
                            if total_files <= 0:
                                progress = 0
                            else:
                                progress = (current_file_index / total_files) * 100
                                
                            # Convert folder paths to strings if they're Path objects
                            folder_path = str(state.get('folder_path', '')) if state.get('folder_path') else ''
                            local_path = str(state.get('local_path', folder_path)) if state.get('local_path') else folder_path
                            
                            # Create a task from the saved state
                            task_id = len(self.upload_tasks) + 1
                            task = {
                                'id': task_id,
                                'order_number': state.get('order_number', order_number),
                                'folder_path': folder_path,
                                'local_path': local_path,
                                'status': 'paused',  # Always start as paused for safety
                                'progress': progress,
                                'uploader': None,  # Will be initialized when resumed
                                'photographers': state.get('photographers', {}),
                                # Handle date conversion safely
                                'order_date': self._parse_safe_date(state.get('order_date')) 
                            }
                            
                            # Check if files are valid
                            file_path = task.get('folder_path', '')
                            if file_path and not os.path.exists(file_path):
                                self.log_message(f"Warning: files path does not exist: {file_path}")
                                # Don't auto-prompt for all files, just log the warning for now
                                task['path_exists'] = False
                            else:
                                task['path_exists'] = True
                        
                            # Add task to list and update UI
                            self.upload_tasks.append(task)
                            self.update_task_list(task)
                            self.log_message(f"Restored paused task for order {order_number} from state file")
                            
                            # Auto-resume task if the application was not properly closed last time
                            # Use safer timer approach to avoid UI freezes
                            if hasattr(self, '_auto_resume') and self._auto_resume and task['status'] == 'paused':
                                self.log_message(f"Auto-resuming task {order_number} after abnormal shutdown")
                                # Use a timer to start the task after UI is fully loaded
                                # Add random delay to avoid starting all tasks simultaneously
                                import random
                                delay = 5000 + (random.randint(0, 10) * 1000)  # 5-15 seconds
                                QTimer.singleShot(delay, lambda task_id=task['id']: self.auto_resume_task(task_id))
                                    
                        except Exception as e:
                            self.log_message(f"Error loading state file {state_file.name}: {str(e)}")
                            import traceback
                            self.log_message(traceback.format_exc())
            else:
                self.log_message("No saved state files found")
                if not state_dir.exists():
                    self.log_message(f"State save directory doesn't exist, creating: {state_dir}")
                    state_dir.mkdir(exist_ok=True)
                
            # If auto_resume flag is enabled, start all paused tasks automatically
            if self.auto_resume:
                self.log_message("AUTO_RESUME is enabled, resuming all paused tasks automatically...")
                # Use a timer to avoid UI freezing
                QTimer.singleShot(3000, self.auto_resume_all_tasks)
            
        except Exception as e:
            self.log_message(f"Error loading tasks: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

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
            
            cursor.close()
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
                cursor.close()
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
            cursor.close()
            
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
                item.setData(Qt.UserRole, upload['task_id'])
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
                cursor.close()
                return
                
            # Use the first ID column found (prioritize task_id if available)
            id_columns = [col['COLUMN_NAME'] for col in columns]
            id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
            
            # Build the query with filters
            query = f"""
            SELECT {id_column} as task_id, order_number, status, progress, 
                   created_at, updated_at, folder_path, created_by, 
                   order_date, main_photographer_id, assistant_photographer_id, 
                   video_photographer_id, local_path
            FROM upload_tasks 
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
            cursor.close()
            
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
                item.setData(Qt.UserRole, upload)
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
            cursor.close()
            
            # Run a separate check for user authentication schema
            self.check_db_schema()
            
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
            upload_data = item.data(Qt.UserRole)
            
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
                    created_str = created_date.strftime("%Y-%m-%d %H:%M:%S")
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
                
            # Photographers
            main_photographer_id = upload_data.get('main_photographer_id')
            if main_photographer_id:
                photographer_name = self.get_photographer_name(main_photographer_id)
                html += f"<tr><td><b>Main Photographer:</b></td><td>{photographer_name}</td></tr>"
                
            assistant_photographer_id = upload_data.get('assistant_photographer_id')
            if assistant_photographer_id:
                photographer_name = self.get_photographer_name(assistant_photographer_id)
                html += f"<tr><td><b>Assistant Photographer:</b></td><td>{photographer_name}</td></tr>"
                
            video_photographer_id = upload_data.get('video_photographer_id')
            if video_photographer_id:
                photographer_name = self.get_photographer_name(video_photographer_id)
                html += f"<tr><td><b>Video Photographer:</b></td><td>{photographer_name}</td></tr>"
                
            html += "</table>"
            
            # Add actions section
            html += "<hr/><h3>Actions</h3>"
            html += "<ul>"
            html += f"<li><a href='resume:{upload_data['task_id']}'>Resume Upload</a></li>"
            html += f"<li><a href='view:{upload_data['task_id']}'>View Files</a></li>"
            html += f"<li><a href='delete:{upload_data['task_id']}'>Delete Task</a></li>"
            html += "</ul>"
            
            html += "</body></html>"
            
            # Set the HTML content
            self.upload_details.setHtml(html)
            
            # Connect the link click handler
            self.upload_details.anchorClicked.connect(self.handle_order_action)
            
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
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                return f"ID: {photographer_id}"
                
            # Query the database for photographer name
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            query = """
            SELECT photographer_name
            FROM photographers
            WHERE photographer_id = %s
            """
            
            cursor.execute(query, (photographer_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if result and 'photographer_name' in result:
                return result['photographer_name']
            else:
                return f"ID: {photographer_id}"
                
        except Exception as e:
            self.log_message(f"Error getting photographer name: {str(e)}")
            return f"ID: {photographer_id}"
    
    def handle_order_action(self, url):
        """
        Handle clicks on action links in order details
        
        Args:
            url (QUrl): The clicked URL
        """
        try:
            # Parse the URL
            url_str = url.toString()
            
            # Extract action and task ID
            parts = url_str.split(':')
            if len(parts) != 2:
                self.log_message(f"Invalid action URL: {url_str}")
                return
                
            action = parts[0]
            task_id = int(parts[1])
            
            self.log_message(f"Order action: {action} for task {task_id}")
            
            # Handle different actions
            if action == 'resume':
                self.resume_order_from_history(task_id)
            elif action == 'view':
                self.view_order_files(task_id)
            elif action == 'delete':
                self.delete_order_from_history(task_id)
            else:
                self.log_message(f"Unknown action: {action}")
                
        except Exception as e:
            self.log_message(f"Error handling order action: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def resume_order_from_history(self, task_id):
        """
        Resume upload for a task from history
        
        Args:
            task_id (int): Task ID to resume
        """
        try:
            self.log_message(f"Resuming upload for task {task_id} from history")
            
            # Check if user is logged in
            if not self.ensure_user_logged_in():
                self.log_message("User not logged in, cannot resume task")
                return
                
            # Get task data from database
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("Error: No database connection available")
                return
                
            # Query for task details
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
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
            
            # Get task details
            query = f"""
            SELECT order_number, folder_path, local_path, order_date, 
                   main_photographer_id, assistant_photographer_id, video_photographer_id
            FROM upload_tasks
            WHERE {id_column} = %s
            """
            
            cursor.execute(query, (task_id,))
            task_data = cursor.fetchone()
            cursor.close()
            
            if not task_data:
                self.log_message(f"Error: Task with ID {task_id} not found in database")
                return
                
            # Create a new task for the upload
            new_task_id = len(self.upload_tasks) + 1
            
            # Create photographers dict
            photographers = {
                'main': task_data.get('main_photographer_id'),
                'assistant': task_data.get('assistant_photographer_id'),
                'video': task_data.get('video_photographer_id')
            }
            
            task = {
                'id': new_task_id,
                'order_number': task_data['order_number'],
                'folder_path': task_data.get('folder_path', ''),
                'local_path': task_data.get('local_path', task_data.get('folder_path', '')),
                'status': 'pending',
                'progress': 0,
                'uploader': None,
                'photographers': photographers,
                'order_date': task_data.get('order_date'),
                'db_id': task_id  # Keep original task ID for database updates
            }
            
            # Create a task item for the list
            from PyQt5.QtWidgets import QListWidgetItem
            from PyQt5.QtCore import Qt
            
            task_item = QListWidgetItem()
            task_item.setText(f"Task {new_task_id}: Order {task['order_number']} - Pending")
            task_item.setData(Qt.UserRole, task['id'])
            
            # Add item to task
            task['item'] = task_item
            
            # Add to the list widget
            self.task_list.addItem(task_item)
            
            # Add to tasks list
            self.upload_tasks.append(task)
            
            # Enable the Start All button
            self.start_all_btn.setEnabled(True)
            
            # Switch to Upload tab
            self.tabs.setCurrentIndex(0)
            
            # Select the new task
            self.task_list.setCurrentItem(task_item)
            
            # Log the action
            self.log_message(f"Created new task for order {task['order_number']} from history")
            self.log_activity("task", "resume_from_history", 
                            f"Created task for order {task['order_number']} from history", 
                            self.user_info.get('Emp_FullName'))
            
            # Ask if user wants to start the task immediately
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 
                'Start Upload', 
                f'Do you want to start the upload for Order {task["order_number"]} now?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # Start the task
                self.start_task(task)
                
        except Exception as e:
            self.log_message(f"Error resuming order from history: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def view_order_files(self, task_id):
        """
        View files for a task
        
        Args:
            task_id (int): Task ID to view
        """
        try:
            self.log_message(f"Viewing files for task {task_id}")
            
            # Get task data from database
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("Error: No database connection available")
                return
                
            # Query for task details
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
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
            
            # Get task details
            query = f"""
            SELECT order_number, folder_path, local_path
            FROM upload_tasks
            WHERE {id_column} = %s
            """
            
            cursor.execute(query, (task_id,))
            task_data = cursor.fetchone()
            cursor.close()
            
            if not task_data:
                self.log_message(f"Error: Task with ID {task_id} not found in database")
                return
                
            # Determine the path to open
            folder_path = task_data.get('folder_path', '')
            local_path = task_data.get('local_path', folder_path)
            
            path_to_open = local_path if local_path and os.path.exists(local_path) else folder_path
            
            if not path_to_open or not os.path.exists(path_to_open):
                self.log_message(f"Error: Path does not exist: {path_to_open}")
                
                # Ask user to browse for folder
                from PyQt5.QtWidgets import QMessageBox, QFileDialog
                reply = QMessageBox.question(
                    self, 
                    'Path Not Found', 
                    f'The folder for Order {task_data["order_number"]} was not found at:\n{path_to_open}\n\nDo you want to browse for it?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    # Browse for folder
                    folder = QFileDialog.getExistingDirectory(
                        self, 
                        f'Select folder for Order {task_data["order_number"]}'
                    )
                    
                    if folder:
                        path_to_open = folder
                        
                        # Update database with new path
                        if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                            self.db_manager.connect()
                            
                        if self.db_manager.connection:
                            cursor = self.db_manager.connection.cursor()
                            
                            query = f"""
                            UPDATE upload_tasks
                            SET local_path = %s
                            WHERE {id_column} = %s
                            """
                            
                            cursor.execute(query, (folder, task_id))
                            self.db_manager.connection.commit()
                            cursor.close()
                            
                            self.log_message(f"Updated local path for Order {task_data['order_number']}: {folder}")
                    else:
                        return
                else:
                    return
                
            # Open folder in file explorer
            import subprocess
            import platform
            
            try:
                if platform.system() == 'Windows':
                    os.startfile(path_to_open)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.call(['open', path_to_open])
                else:  # Linux
                    subprocess.call(['xdg-open', path_to_open])
                    
                self.log_message(f"Opened folder for Order {task_data['order_number']}: {path_to_open}")
                self.log_activity("task", "view_files", 
                                f"Viewed files for order {task_data['order_number']}", 
                                self.user_info.get('Emp_FullName'))
            except Exception as e:
                self.log_message(f"Error opening folder: {str(e)}")
                
        except Exception as e:
            self.log_message(f"Error viewing order files: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def delete_order_from_history(self, task_id):
        """
        Delete a task from history
        
        Args:
            task_id (int): Task ID to delete
        """
        try:
            self.log_message(f"Deleting task {task_id} from history")
            
            # Check if user is logged in
            if not self.ensure_user_logged_in():
                self.log_message("User not logged in, cannot delete task")
                return
                
            # Get task data from database
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
                
            if not self.db_manager.connection:
                self.log_message("Error: No database connection available")
                return
                
            # Query for task details
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
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
            
            # Get task details
            query = f"""
            SELECT order_number
            FROM upload_tasks
            WHERE {id_column} = %s
            """
            
            cursor.execute(query, (task_id,))
            task_data = cursor.fetchone()
            
            if not task_data:
                self.log_message(f"Error: Task with ID {task_id} not found in database")
                cursor.close()
                return
                
            # Confirm deletion
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 
                'Confirm Deletion', 
                f'Are you sure you want to delete Order {task_data["order_number"]} from the database?\n\nThis action cannot be undone.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                cursor.close()
                return
                
            # Delete from database
            delete_query = f"""
            DELETE FROM upload_tasks
            WHERE {id_column} = %s
            """
            
            cursor.execute(delete_query, (task_id,))
            self.db_manager.connection.commit()
            cursor.close()
            
            self.log_message(f"Deleted task for Order {task_data['order_number']} from database")
            self.log_activity("task", "delete_from_history", 
                            f"Deleted task for order {task_data['order_number']} from database", 
                            self.user_info.get('Emp_FullName'))
            
            # Refresh the history list
            self.apply_history_filter()
            
            # Clear the details
            self.upload_details.clear()
            
        except Exception as e:
            self.log_message(f"Error deleting order from history: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())

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
                    task['uploader'].stop()
            
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

    def update_task_list(self, task):
        """
        Update the UI display for a task
        
        Args:
            task (dict): Task to update
        """
        try:
            # Find the list item for this task
            if 'item' in task and task['item'] is not None:
                # Update the list item text
                status_text = task['status'].capitalize()
                progress = int(task.get('progress', 0))
                
                task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - {status_text} ({progress}%)")
            else:
                # If item doesn't exist, create a new one
                from PyQt5.QtWidgets import QListWidgetItem
                from PyQt5.QtCore import Qt
                
                item = QListWidgetItem()
                status_text = task['status'].capitalize()
                progress = int(task.get('progress', 0))
                
                item.setText(f"Task {task['id']}: Order {task['order_number']} - {status_text} ({progress}%)")
                item.setData(Qt.UserRole, task['id'])
                
                # Store the item in the task
                task['item'] = item
                
                # Add to the list widget
                self.task_list.addItem(item)
                
            # Update progress bar if this is a running task
            if task['status'] == 'running':
                # Update progress bar based on all running tasks
                running_tasks = [t for t in self.upload_tasks if t['status'] == 'running']
                if running_tasks:
                    avg_progress = sum(t.get('progress', 0) for t in running_tasks) / len(running_tasks)
                    self.progress_bar.setValue(round(avg_progress))
                    
            # Update the database if task has a database ID
            if hasattr(task, 'db_id') and task.get('db_id') and self.db_manager.connection:
                try:
                    # Save task to database
                    self.save_task_to_database(task)
                except Exception as db_error:
                    self.log_message(f"Warning: Could not update task in database: {str(db_error)}")
        
        except Exception as e:
            self.log_message(f"Error updating task list: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
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
        task_data = selected_items[0].data(Qt.UserRole)
        
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
            self.restart_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.delete_btn.setEnabled(False)
        elif task['status'] in ['completed', 'cancelled', 'error']:
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.delete_btn.setEnabled(True)
        elif task['status'] == 'pending':
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
    
    def init_aws_session(self):
        """Initialize AWS session with credentials from config"""
        try:
            # Si estamos en modo seguro, crear automáticamente una sesión simulada
            if self.safe_mode:
                self.log_message("Running in safe mode - creating mock AWS session without attempting AWS connection")
                self.aws_session = type('MockSession', (), {
                    'client': lambda *args, **kwargs: None,
                    'bucket_name': self.aws_config.get('AWS_S3_BUCKET', 'mock-bucket')
                })
                return
                
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
                self.aws_session = boto3.session.Session(
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
                    self.aws_session = boto3.session.Session()
                    s3 = self.aws_session.client('s3')
                    s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    self.log_message(f"Connected to bucket using default credentials: {bucket_name}")
                except Exception as default_error:
                    self.log_message(f"Error using default credentials: {str(default_error)}")
                    self.aws_session = None
                    # Create an empty mock session for testing purposes
                    if self.safe_mode:
                        self.log_message("Creating mock AWS session for safe mode")
                        self.aws_session = type('MockSession', (), {'client': lambda *args, **kwargs: None})
        except Exception as e:
            self.log_message(f"Error initializing AWS session: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            self.aws_session = None
            
            # In safe mode, create a mock session
            if self.safe_mode:
                self.log_message("Creating mock AWS session for safe mode")
                self.aws_session = type('MockSession', (), {'client': lambda *args, **kwargs: None})

    def scan_for_missing_files(self, task):
        """
        Scan a task's local directory and compare with files already uploaded to S3
        to find any files that haven't been uploaded yet.
        
        Args:
            task (dict): Task to scan for missing files
            
        Returns:
            dict: Information about the scan results including:
                  - total_files: Total number of local files
                  - uploaded_files: Number of files already uploaded
                  - missing_files: Number of files not yet uploaded
                  - missing_file_list: List of file paths that need to be uploaded
        """
        self.log_message(f"Scanning for missing files in order {task['order_number']}...")
        
        try:
            from pathlib import Path
            import os
            import boto3
            
            # Make sure we have an AWS session
            if not hasattr(self, 'aws_session') or not self.aws_session:
                self.init_aws_session()
            
            if not self.aws_session:
                self.log_message("Error: No AWS session available for scanning S3")
                return None
            
            # Get the folder path
            folder_path = task.get('local_path') or task.get('folder_path')
            if not folder_path or not os.path.exists(folder_path):
                self.log_message(f"Error: Path not found: {folder_path}")
                return None
                
            # Create S3 client using session
            s3_client = self.aws_session.client('s3')
            
            # Get bucket name from config
            bucket_name = self.aws_config.get('AWS_S3_BUCKET', 'balistudiostorage')
            
            # Build the S3 prefix based on order number and date
            order_num = task['order_number']
            order_date = task.get('order_date')
            
            # Format date as YYYY-MM-DD if it's a QDate
            if isinstance(order_date, QDate) and order_date.isValid():
                date_str = order_date.toString('yyyy-MM-dd')
            elif hasattr(order_date, 'strftime'):
                date_str = order_date.strftime('%Y-%m-%d')
            elif isinstance(order_date, str):
                date_str = order_date
            else:
                # If no valid date, use current date
                from datetime import datetime
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            # Construct the S3 prefix (directory path in S3)
            s3_prefix = f"orders/{date_str}/{order_num}/"
            
            # Scan local files
            local_files = []
            local_file_sizes = {}
            
            try:
                # Walk through the directory and collect all files
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, folder_path)
                        
                        # Skip temporary files and hidden files
                        if file.startswith('.') or file.endswith('.tmp') or file.endswith('.crdownload'):
                            continue
                            
                        # Get file size for comparison
                        try:
                            file_size = os.path.getsize(file_path)
                            local_files.append(rel_path)
                            local_file_sizes[rel_path] = file_size
                        except OSError:
                            self.log_message(f"Warning: Could not access file: {file_path}")
                
                self.log_message(f"Found {len(local_files)} local files in {folder_path}")
            except Exception as e:
                self.log_message(f"Error scanning local directory: {str(e)}")
                return None
            
            # List files in S3
            s3_files = []
            s3_file_sizes = {}
            
            try:
                # Use pagination to handle large directories
                paginator = s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)
                
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Get the key (path) and remove the prefix to get the relative path
                            key = obj['Key']
                            if key.startswith(s3_prefix):
                                rel_key = key[len(s3_prefix):]
                                s3_files.append(rel_key)
                                s3_file_sizes[rel_key] = obj['Size']
                
                self.log_message(f"Found {len(s3_files)} files already uploaded to S3 in {s3_prefix}")
            except Exception as e:
                self.log_message(f"Error listing S3 objects: {str(e)}")
                return None
            
            # Find missing files (files in local directory but not in S3)
            missing_files = []
            size_mismatch_files = []
            
            for file in local_files:
                if file not in s3_files:
                    missing_files.append(file)
                elif local_file_sizes.get(file, 0) != s3_file_sizes.get(file, -1):
                    # Size mismatch means the file might be partially uploaded
                    size_mismatch_files.append(file)
            
            # Combine missing and size mismatched files as both need to be uploaded
            all_missing_files = missing_files + size_mismatch_files
            
            # Log the results
            self.log_message(f"Scan results for order {order_num}:")
            self.log_message(f" - Total local files: {len(local_files)}")
            self.log_message(f" - Files already in S3: {len(s3_files)}")
            self.log_message(f" - Files missing from S3: {len(missing_files)}")
            self.log_message(f" - Files with size mismatch: {len(size_mismatch_files)}")
            
            # If there are missing files, log some examples
            if all_missing_files:
                examples = all_missing_files[:5]
                self.log_message("Examples of missing files:")
                for example in examples:
                    self.log_message(f" - {example}")
                
                if len(all_missing_files) > 5:
                    self.log_message(f" - And {len(all_missing_files) - 5} more...")
            
            # Create a result summary
            result = {
                'total_files': len(local_files),
                'uploaded_files': len(s3_files),
                'missing_files': len(all_missing_files),
                'missing_file_list': all_missing_files,
                'has_partial_uploads': len(size_mismatch_files) > 0
            }
            
            return result
            
        except Exception as e:
            self.log_message(f"Error scanning for missing files: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return None