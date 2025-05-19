#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
import boto3
from boto3.session import Session
from PyQt5.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, 
                            QHBoxLayout, QWidget, QLabel, QLineEdit, QProgressBar, 
                            QTextEdit, QFileDialog, QFrame, QMessageBox, QSystemTrayIcon,
                            QMenu, QDialog, QDateEdit, QComboBox, QListWidget, QListWidgetItem,
                            QTabWidget, QScrollArea, QGridLayout, QTextBrowser, QApplication)
from PyQt5.QtCore import Qt, QThread, QSettings, QDate
from PyQt5.QtGui import QIcon

from ui.photographers_dialog import PhotographersDialog
from ui.order_selector_dialog import OrderSelectorDialog
from ui.image_preview_dialog import ImagePreviewDialog
from utils.background_uploader import BackgroundUploader

class S3UploaderGUI(QMainWindow):
    """
    Main application window for S3 file uploader
    """
    def __init__(self, aws_config, db_manager, user_info):
        super().__init__()
        self.aws_config = aws_config
        self.db_manager = db_manager
        self.user_info = user_info
        self.aws_session = Session(
            aws_access_key_id=aws_config['aws_access_key_id'],
            aws_secret_access_key=aws_config['aws_secret_key'],
            region_name=aws_config['region']
        )
        self.aws_session.bucket_name = aws_config['bucket']
        
        # Storage location settings
        self.settings = QSettings("BaliStudio", "SecureUploader")
        self.local_storage_path = self.settings.value("local_storage_path", "")
        
        # Order-related variables
        self.current_order_path = None
        
        # Photographer selection
        self.photographers = {
            'main': None,
            'assistant': None, 
            'video': None
        }
        
        # List to track multiple upload tasks
        self.upload_tasks = []
        
        self.init_ui()
        self.uploader = None
        self.setup_tray()
        
        # Load pending tasks from database
        self.load_pending_tasks()
    
    def init_ui(self):  # تغيير لاستخدام snake_case
        """Initialize the user interface"""
        self.setWindowTitle('Secure File Uploader')
        self.setGeometry(100, 100, 900, 700)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # User info panel
        user_frame = QFrame()
        user_frame.setFrameShape(QFrame.StyledPanel)
        user_layout = QHBoxLayout()
        
        user_layout.addWidget(QLabel(f"Welcome {self.user_info['Emp_FullName']}"))
        import getmac
        user_layout.addWidget(QLabel(f"Device ID: {getmac.get_mac_address()}"))
        
        user_frame.setLayout(user_layout)
        layout.addWidget(user_frame)
        
        # Tab widget for different functions
        self.tabs = QTabWidget()
        
        # Upload tab
        upload_tab = QWidget()
        upload_layout = QVBoxLayout()
        
        # Source folder selection
        folder_frame = QFrame()
        folder_layout = QHBoxLayout()
        
        self.folder_path = QLineEdit()
        self.folder_path.setPlaceholderText("Select folder...")
        self.folder_path.setReadOnly(True)
        browse_btn = QPushButton('Browse')
        browse_btn.clicked.connect(self.browse_folder)
        
        folder_layout.addWidget(QLabel('Source Folder:'))
        folder_layout.addWidget(self.folder_path)
        folder_layout.addWidget(browse_btn)
        folder_frame.setLayout(folder_layout)
        upload_layout.addWidget(folder_frame)
        
        # Local storage path
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
        
        # Order selection
        order_frame = QFrame()
        order_layout = QHBoxLayout()
        
        self.order_number = QLineEdit()
        self.order_number.setPlaceholderText("Enter or select order number")
        # Allow manual entry of order numbers
        self.order_number.setReadOnly(False)
        # Connect textChanged signal to validate manual entry
        self.order_number.textChanged.connect(self.validate_order_number_entry)
        
        self.order_date = QDateEdit()
        self.order_date.setCalendarPopup(True)
        self.order_date.setDate(QDate.currentDate())
        self.order_date.dateChanged.connect(self.date_changed)
        
        select_order_btn = QPushButton('Select Order')
        select_order_btn.clicked.connect(self.select_order)
        
        order_layout.addWidget(QLabel('Order Date:'))
        order_layout.addWidget(self.order_date)
        order_layout.addWidget(QLabel('Order Number:'))
        order_layout.addWidget(self.order_number)
        order_layout.addWidget(select_order_btn)
        
        order_frame.setLayout(order_layout)
        upload_layout.addWidget(order_frame)
        
        # Photographer selection
        photographer_frame = QFrame()
        photographer_layout = QHBoxLayout()
        
        self.photographer_info = QLineEdit()
        self.photographer_info.setPlaceholderText("Select photographers...")
        self.photographer_info.setReadOnly(True)
        
        select_photographer_btn = QPushButton('Select Photographers')
        select_photographer_btn.clicked.connect(self.select_photographers)
        
        photographer_layout.addWidget(QLabel('Photographers:'))
        photographer_layout.addWidget(self.photographer_info)
        photographer_layout.addWidget(select_photographer_btn)
        
        photographer_frame.setLayout(photographer_layout)
        upload_layout.addWidget(photographer_frame)
        
        # Task list for multiple uploads
        task_list_label = QLabel("Upload Tasks:")
        upload_layout.addWidget(task_list_label)
        
        self.task_list = QListWidget()
        self.task_list.setMinimumHeight(150)
        upload_layout.addWidget(self.task_list)
        
        # Progress bar and buttons
        self.progress_bar = QProgressBar()
        
        button_layout = QHBoxLayout()
        self.upload_btn = QPushButton('Add Upload Task')
        self.upload_btn.clicked.connect(self.add_upload_task)
        
        self.start_all_btn = QPushButton('Start All Tasks')
        self.start_all_btn.clicked.connect(self.start_all_tasks)
        self.start_all_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton('Cancel Selected')
        self.cancel_btn.clicked.connect(self.cancel_selected_task)
        self.cancel_btn.setEnabled(False)
        
        button_layout.addWidget(self.upload_btn)
        button_layout.addWidget(self.start_all_btn)
        button_layout.addWidget(self.cancel_btn)
        
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
        
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.show_order_details)
        
        refresh_btn = QPushButton('Refresh')
        refresh_btn.clicked.connect(self.load_upload_history)
        
        history_layout.addWidget(QLabel("Today's Uploads:"))
        history_layout.addWidget(self.history_list)
        history_layout.addWidget(refresh_btn)
        
        self.upload_details = QTextBrowser()
        self.upload_details.setReadOnly(True)
        history_layout.addWidget(QLabel("Upload Details:"))
        history_layout.addWidget(self.upload_details)
        
        history_tab.setLayout(history_layout)
        
        # Add tabs to widget
        self.tabs.addTab(upload_tab, "Upload Files")
        self.tabs.addTab(history_tab, "Upload History")
        
        layout.addWidget(self.tabs)
        
        main_widget.setLayout(layout)
        
        # Initialize history
        self.load_upload_history()
    
    def setup_tray(self):
        """Setup system tray icon and menu"""
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'icon.png')
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
        self.log_text.append(f"[{timestamp}] {message}")
    
    def browse_folder(self):
        """Browse for source folder"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Source Folder')
        if folder:
            self.folder_path.setText(folder)
            self.analyze_folder(folder)
    
    def browse_local_storage(self):
        """Browse for local storage location"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Local Storage Location')
        if folder:
            self.local_storage.setText(folder)
            self.local_storage_path = folder
            self.settings.setValue("local_storage_path", folder)
            self.log_message(f"Local storage location set to: {folder}")
    
    def validate_order_number_entry(self):
        """Validate manually entered order number"""
        # This method can be implemented to validate the order number format
        # For now, it's just a placeholder
        pass
    
    def date_changed(self):
        """Handle date selection changes"""
        # When date changes, clear the order number
        self.order_number.setText("")
        
        # Check if there are orders for the selected date
        selected_date = self.order_date.date().toPyDate().strftime('%Y-%m-%d')
        self.db_manager.selected_date = selected_date
        orders = self.db_manager.get_todays_orders()
        
        # If there are orders, make the order number field read-only
        # Otherwise, allow manual entry
        if orders:
            self.order_number.setReadOnly(True)
            self.log_message(f"Found {len(orders)} orders for {selected_date}. Use 'Select Order' to choose one.")
        else:
            self.order_number.setReadOnly(False)
            self.log_message(f"No orders found for {selected_date}. You can enter an order number manually.")
    
    def select_order(self):
        """Open order selection dialog"""
        # Set the selected date in the database manager
        selected_date = self.order_date.date().toPyDate().strftime('%Y-%m-%d')
        self.db_manager.selected_date = selected_date
        
        # Get orders for the selected date
        orders = self.db_manager.get_todays_orders()
        if not orders:
            QMessageBox.information(self, "Information", f"No orders found for {selected_date}")
            # Allow manual entry since there are no orders
            self.order_number.setReadOnly(False)
            self.log_message(f"No orders found for {selected_date}. You can enter an order number manually.")
            return
            
        # Check if the user wants to enter a manual order number instead
        manual_entry = QMessageBox.question(
            self, 
            "Manual Entry", 
            f"There are {len(orders)} orders for {selected_date}. Do you want to select from existing orders or enter a new order number manually?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if manual_entry == QMessageBox.No:  # User wants to enter manually
            self.order_number.setReadOnly(False)
            self.log_message("Manual order number entry enabled.")
            return
            
        # User wants to select from existing orders
        dialog = OrderSelectorDialog(orders, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_order_number = dialog.get_selected_order_id()
            if selected_order_number:
                self.order_number.setText(str(selected_order_number))
                
                # Create folder structure and set it as source
                order_path = self.create_local_folders(selected_order_number)
                if order_path:
                    self.current_order_path = order_path
                    self.folder_path.setText(str(order_path))
                    
                    # Open the folder for the user
                    self.open_folder(order_path)
    
    def select_photographers(self):
        """Open photographer selection dialog"""
        photographers = self.db_manager.get_photographers()
        if not photographers:
            QMessageBox.warning(self, "Warning", "Could not fetch photographer list from database")
            return
        
        dialog = PhotographersDialog(photographers, self)
        if dialog.exec_() == QDialog.Accepted:
            self.photographers = dialog.get_selected_photographers()
            
            # Update the display
            photographer_text = []
            
            for photographer in photographers:
                if photographer['Emp_ID'] == self.photographers['main']:
                    photographer_text.append(f"Main: {photographer['Emp_FullName']}")
            
            for photographer in photographers:
                if photographer['Emp_ID'] == self.photographers['assistant']:
                    photographer_text.append(f"Assistant: {photographer['Emp_FullName']}")
            
            for photographer in photographers:
                if photographer['Emp_ID'] == self.photographers['video']:
                    photographer_text.append(f"Video: {photographer['Emp_FullName']}")
            
            if photographer_text:
                self.photographer_info.setText(", ".join(photographer_text))
            else:
                self.photographer_info.setText("")
    
    def create_local_folders(self, order_number):
        """
        Create folder structure for the selected order
        
        Args:
            order_number (str): Order number
            
        Returns:
            Path: Path to created folder structure or None if failed
        """
        if not self.local_storage_path:
            QMessageBox.warning(self, "Warning", "Please select a local storage location first")
            self.browse_local_storage()
            if not self.local_storage_path:
                return None
        
        date_obj = self.order_date.date().toPyDate()
        year = date_obj.year
        month = f"{date_obj.month:02d}-{year}"
        day = f"{date_obj.day:02d}-{month}"
        
        # Create folder structure
        base_path = Path(self.local_storage_path) / str(year) / month / day / f"Order_{order_number}"
        
        # Create the main folders
        folders = [
            base_path / "CR2",
            base_path / "JPG",
            base_path / "Reels/Videos"
        ]
        
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            self.log_message(f"Created folder: {folder}")
        
        return base_path
    
    def open_folder(self, folder_path):
        """
        Open the folder in the default file explorer
        
        Args:
            folder_path (Path): Path to open
        """
        try:
            folder_str = str(folder_path)
            if sys.platform == 'win32':
                os.startfile(folder_str)
            elif sys.platform == 'darwin':  # macOS
                import subprocess
                subprocess.Popen(['open', folder_str])
            else:  # Linux
                import subprocess
                subprocess.Popen(['xdg-open', folder_str])
                
            self.log_message(f"Opened folder: {folder_str}")
        except Exception as e:
            self.log_message(f"Error opening folder: {str(e)}")
    
    def analyze_folder(self, folder_path):
        """
        Analyze the source folder and categorize files
        
        Args:
            folder_path (str): Path to analyze
            
        Returns:
            dict: Dictionary with file extension statistics
        """
        extensions = {}
        file_count = 0
        total_size = 0
        
        for path in Path(folder_path).rglob('*'):
            if path.is_file():
                ext = path.suffix[1:].upper() or 'NO_EXTENSION'
                size = path.stat().st_size
                
                if ext not in extensions:
                    extensions[ext] = {
                        'count': 0,
                        'size': 0,
                        'files': []
                    }
                
                extensions[ext]['count'] += 1
                extensions[ext]['size'] += size
                extensions[ext]['files'].append(str(path))
                
                file_count += 1
                total_size += size
        
        # Show summary
        if extensions:
            size_mb = total_size / (1024 * 1024)
            self.log_message(f"Found {file_count} files ({size_mb:.2f} MB)")
            
            for ext, data in sorted(extensions.items()):
                ext_size_mb = data['size'] / (1024 * 1024)
                self.log_message(f"  {ext}: {data['count']} files ({ext_size_mb:.2f} MB)")
        
        return extensions
    
    def validate_inputs(self):
        """
        Validate all inputs before starting upload
        
        Returns:
            bool: True if all inputs are valid, False otherwise
        """
        if not self.folder_path.text():
            QMessageBox.warning(self, "Error", "Please select a source folder!")
            return False
        
        if not self.local_storage_path:
            QMessageBox.warning(self, "Error", "Please select a local storage location!")
            return False
        
        if not self.order_number.text():
            QMessageBox.warning(self, "Error", "Please select an order!")
            return False
        
        if not self.photographers['main']:
            QMessageBox.warning(self, "Error", "Please select a main photographer!")
            return False
        
        return True
    
    def add_upload_task(self):
        """Add a new upload task to the list"""
        if not self.validate_inputs():
            return
            
        try:
            # Create task record in database first
            task_data = {
                'order_number': self.order_number.text(),
                'order_date': self.order_date.date().toPyDate(),
                'folder_path': str(self.folder_path.text()),  # Convert to string
                'main_photographer_id': int(self.photographers['main']) if self.photographers['main'] else None,
                'assistant_photographer_id': int(self.photographers['assistant']) if self.photographers['assistant'] else None,
                'video_photographer_id': int(self.photographers['video']) if self.photographers['video'] else None,
                'status': 'pending',
                'progress': 0,
                'local_path': str(self.current_order_path) if self.current_order_path else ''  # Convert to string
            }
            
            # Insert into upload_tasks table
            cursor = self.db_manager.connection.cursor()
            insert_query = """
            INSERT INTO upload_tasks (
                order_number, order_date, folder_path, main_photographer_id,
                assistant_photographer_id, video_photographer_id, status,
                progress, local_path, created_by, created_by_emp_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
            cursor.execute(insert_query, (
                task_data['order_number'],
                task_data['order_date'],
                task_data['folder_path'],
                task_data['main_photographer_id'],
                task_data['assistant_photographer_id'],
                task_data['video_photographer_id'],
                task_data['status'],
                task_data['progress'],
                task_data['local_path'],
                self.user_info.get('username', 'system'),
                self.user_info.get('emp_id')
            ))
            task_id = cursor.lastrowid
            self.db_manager.connection.commit()
            cursor.close()
            
            # Create a task item for the list
            task_item = QListWidgetItem()
            task_item.setText(f"Task {task_id}: Order {task_data['order_number']} - Pending")
            task_item.setData(Qt.UserRole, {
                'id': task_id,
                **task_data
            })
            
            # Add to the list widget
            self.task_list.addItem(task_item)
            
            # Store the task data
            self.upload_tasks.append({
                'id': task_id,
                'item': task_item,
                **task_data,
                'uploader': None
            })
            
            # Enable the start all button if we have tasks
            self.start_all_btn.setEnabled(len(self.upload_tasks) > 0)
            
            # Clear the form for the next task
            self.folder_path.clear()
            self.order_number.clear()
            self.photographer_info.clear()
            self.photographers = {
                'main': None,
                'assistant': None, 
                'video': None
            }
            
            self.log_message(f"Added upload task {task_id} for order {task_data['order_number']}")
            
            # Start the task automatically if no other tasks are running
            if not any(task['status'] == 'running' for task in self.upload_tasks):
                self.start_task(self.upload_tasks[-1])
                
        except Exception as e:
            self.log_message(f"Error creating task: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def start_all_tasks(self):
        """Start all pending upload tasks"""
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
        
        Args:
            task (dict): Task information
        """
        try:
            # Update task status in database
            cursor = self.db_manager.connection.cursor()
            update_query = """
            UPDATE upload_tasks 
            SET status = 'running',
                last_action_by = %s,
                last_action_by_emp_id = %s,
                last_action_time = NOW()
            WHERE task_id = %s
            """
            cursor.execute(update_query, (
                self.user_info.get('username', 'system'),
                self.user_info.get('emp_id'),
                task['id']
            ))
            self.db_manager.connection.commit()
            cursor.close()
            
            # First, organize files into their respective folders before uploading
            source_folder = task['folder_path']
            if source_folder:
                self.organize_files(source_folder, task['local_path'])
            
            # Create a new uploader for this task
            uploader = BackgroundUploader(
                folder_path=task['folder_path'],
                order_number=task['order_number'],
                order_date=task['order_date'],
                aws_session=self.aws_session,
                photographers={
                    'main': task['main_photographer_id'],
                    'assistant': task['assistant_photographer_id'],
                    'video': task['video_photographer_id']
                },
                local_path=task['local_path'],
                parent=self
            )
            
            # Connect signals with task-specific handlers
            uploader.progress.connect(lambda current, total, task_id=task['id']: 
                                    self.update_task_progress(task_id, current, total))
            uploader.log.connect(lambda message, task_id=task['id']: 
                                self.log_task_message(task_id, message))
            uploader.finished.connect(lambda task_id=task['id']: 
                                    self.task_finished(task_id))
            
            # Update task status
            task['uploader'] = uploader
            task['status'] = 'running'
            
            # Update the list item
            task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Running (0%)")
            
            # Start the uploader
            uploader.start()
            
            self.log_message(f"Started upload task {task['id']} for order {task['order_number']}")
            
        except Exception as e:
            self.log_message(f"Error starting task: {str(e)}")
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
        
        # Calculate percentage
        percentage = int((current / total) * 100)
        task['progress'] = percentage
        
        # Update the list item
        task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Running ({percentage}%)")
        
        # Update the main progress bar with average progress of all running tasks
        running_tasks = [t for t in self.upload_tasks if t['status'] == 'running']
        if running_tasks:
            avg_progress = sum(t['progress'] for t in running_tasks) / len(running_tasks)
            self.progress_bar.setValue(int(avg_progress))
    
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
        try:
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                return
            
            # Update task status in database
            cursor = self.db_manager.connection.cursor()
            update_query = """
            UPDATE upload_tasks 
            SET status = 'completed',
                progress = 100,
                completed_timestamp = NOW(),
                last_action_by = %s,
                last_action_by_emp_id = %s,
                last_action_time = NOW()
            WHERE task_id = %s
            """
            cursor.execute(update_query, (
                self.user_info.get('username', 'system'),
                self.user_info.get('emp_id'),
                task_id
            ))
            self.db_manager.connection.commit()
            cursor.close()
            
            # Update task status
            task['status'] = 'completed'
            task['progress'] = 100
            
            # Update the list item
            task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Completed")
            
            # Find the next pending task
            pending_tasks = [t for t in self.upload_tasks if t['status'] == 'pending']
            if pending_tasks:
                # Sort by task ID to ensure oldest tasks are processed first
                next_task = min(pending_tasks, key=lambda x: x['id'])
                self.start_task(next_task)
            
            # Check if all tasks are completed
            if all(t['status'] in ['completed', 'cancelled'] for t in self.upload_tasks):
                self.all_tasks_finished()
            
            # Refresh the upload history
            self.load_upload_history()
            
        except Exception as e:
            self.log_message(f"Error finishing task: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
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
    
    def cancel_selected_task(self):
        """Cancel the selected upload task"""
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Information", "No task selected")
            return
        
        for item in selected_items:
            task_data = item.data(Qt.UserRole)
            task_id = task_data['id']
            
            # Find the task
            task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
            if not task:
                continue
            
            # Cancel the uploader if it's running
            if task['status'] == 'running' and task['uploader']:
                task['uploader'].stop()
            
            # Update task status
            task['status'] = 'cancelled'
            
            # Update the list item
            item.setText(f"Task {task_id}: Order {task['order_number']} - Cancelled")
            
            self.log_message(f"Cancelled upload task {task_id}")
        
        # Check if all tasks are now completed or cancelled
        if all(t['status'] in ['completed', 'cancelled'] for t in self.upload_tasks):
            self.cancel_btn.setEnabled(False)
    
    def start_upload(self):
        """Legacy method for backward compatibility"""
        self.add_upload_task()
        # Start the task immediately
        if self.upload_tasks:
            self.start_task(self.upload_tasks[-1])
    
    def organize_files(self, source_folder, target_order_path=None):
        """
        Organize files into their respective folders by file type and move them
        
        Args:
            source_folder (str): Source folder path
            target_order_path (Path, optional): Target path. Defaults to None.
        """
        try:
            self.log_message("Starting file organization by type...")
            
            # Make sure we have a valid order folder structure
            order_path = target_order_path or self.current_order_path
            if not order_path or not Path(order_path).exists():
                self.log_message("Error: Order folder structure not found")
                return
            
            source_path = Path(source_folder)
            files_organized = 0
            
            # Process all files in the source folder and its subfolders
            for file_path in source_path.rglob('*'):
                if not file_path.is_file():
                    continue
                
                ext = file_path.suffix[1:].lower()  # Use lowercase for better matching
                target_folder = None
                
                # Determine target folder based on file extension
                if ext.upper() in ["CR2", "NEF", "ARW", "RAF", "DNG"]:
                    target_folder = Path(order_path) / "CR2"
                elif ext.lower() in ["jpg", "jpeg", "png", "tiff", "tif", "heic"]:
                    target_folder = Path(order_path) / "JPG"
                elif ext.lower() in ["mp4", "mov", "avi", "mts", "m2ts"]:
                    target_folder = Path(order_path) / "Reels" / "Videos"
                else:
                    # For all other file types
                    target_folder = Path(order_path) / "OTHER"
                
                # Ensure the target folder exists
                target_folder.mkdir(parents=True, exist_ok=True)
                
                # Move the file to the target folder
                if target_folder:
                    target_file = target_folder / file_path.name
                    
                    # Only move if the file doesn't already exist
                    if not target_file.exists():
                        try:
                            # Use shutil.move instead of shutil.copy2 to move the file instead of copying
                            shutil.move(str(file_path), str(target_file))
                            files_organized += 1
                            self.log_message(f"Moved file to: {target_file}")
                        except shutil.SameFileError:
                            # Skip if source and destination are the same file
                            self.log_message(f"Skipping same file: {file_path.name}")
                        except Exception as move_error:
                            self.log_message(f"Error moving file {file_path.name}: {str(move_error)}")
                    
                    # Log progress every 10 files
                    if files_organized % 10 == 0 and files_organized > 0:
                        self.log_message(f"Organized {files_organized} files so far...")
            
            self.log_message(f"File organization complete. Moved {files_organized} files.")
            
        except Exception as e:
            self.log_message(f"Error during file organization: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
    
    def update_progress(self, current, total):
        """
        Update progress bar
        
        Args:
            current (int): Current progress
            total (int): Total items
        """
        percentage = (current / total) * 100
        self.progress_bar.setValue(int(percentage))
    
    def upload_finished(self):
        """Handle upload completion"""
        self.upload_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.log_message("Upload process finished")
        
        # Refresh the upload history
        self.load_upload_history()
        
        self.tray_icon.showMessage(
            "Upload Complete",
            "All files uploaded successfully",
            QSystemTrayIcon.Information,
            2000
        )
    
    def cancel_upload(self):
        """Legacy method for backward compatibility"""
        self.cancel_selected_task()
    
    def load_upload_history(self):
        """Load today's upload history"""
        self.history_list.clear()
        uploads = self.db_manager.get_uploaded_orders_today()
        
        if not uploads:
            self.history_list.addItem("No uploads found for today")
            return
        
        for upload in uploads:
            # Format display with photographer info if available
            photographer_info = []
            if upload.get('main_photographer_name'):
                photographer_info.append(f"Main: {upload['main_photographer_name']}")
            if upload.get('assistant_photographer_name'):
                photographer_info.append(f"Asst: {upload['assistant_photographer_name']}")
            if upload.get('video_photographer_name'):
                photographer_info.append(f"Video: {upload['video_photographer_name']}")
            
            photographer_text = " | ".join(photographer_info) if photographer_info else ""
            
            item_text = f"{upload['order_number']} - {upload['customer_id']} ({upload['file_count']} files)"
            if photographer_text:
                item_text += f" - {photographer_text}"
                
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, upload['order_number'])
            self.history_list.addItem(item)
    
    def show_order_details(self, item):
        """
        Show details for a selected upload with image preview option
        
        Args:
            item (QListWidgetItem): Selected item
        """
        order_number = item.data(Qt.UserRole)
        if not order_number:
            return
            
        details = self.db_manager.get_order_details(order_number)
        if not details:
            self.upload_details.setText("No details available")
            return
        
        # Format the details nicely
        html = f"""
        <h3>Order {details['order']['order_number']}</h3>
        <p><b>Customer:</b> {details['order']['customer_id']}</p>
        <p><b>Order Date:</b> {details['order']['order_date']}</p>
        <p><b>Type:</b> {details['order']['order_type']}</p>
        <p><b>Created by:</b> {details['order']['creator']}</p>
        """
        
        if details['order']['google_drive_link']:
            html += f"<p><b>Google Drive:</b> <a href='{details['order']['google_drive_link']}'>{details['order']['google_drive_link']}</a></p>"
        
        if details['order']['booking_note']:
            html += f"<p><b>Notes:</b> {details['order']['booking_note']}</p>"
        
        # Upload info
        if details['upload']:
            html += "<h4>Upload Information</h4>"
            html += f"<p><b>Files Count:</b> {details['upload']['file_count']}</p>"
            html += f"<p><b>Upload Time:</b> {details['upload']['upload_timestamp']}</p>"
            
            # Photographers
            html += "<h4>Photographers</h4>"
            if details['upload'].get('main_photographer_name'):
                html += f"<p><b>Main Photographer:</b> {details['upload']['main_photographer_name']}</p>"
            if details['upload'].get('assistant_photographer_name'):
                html += f"<p><b>Assistant Photographer:</b> {details['upload']['assistant_photographer_name']}</p>"
            if details['upload'].get('video_photographer_name'):
                html += f"<p><b>Video Photographer:</b> {details['upload']['video_photographer_name']}</p>"
                
            # Add Preview Images button
            html += "<p><a href='#preview'>View Image Previews</a></p>"
        else:
            html += "<p>No upload information available</p>"
        
        self.upload_details.setHtml(html)
        
        # Connect the link to open image previews
        self.upload_details.anchorClicked.connect(lambda url: self.show_image_previews(order_number) if url.toString() == "#preview" else None)

    def show_image_previews(self, order_number):
        """
        Show image preview dialog for the selected order
        
        Args:
            order_number (str): Order number to show previews for
        """
        preview_dialog = ImagePreviewDialog(order_number, self)
        preview_dialog.exec_()

    def init_database_schema(self):
        """Initialize or update database schema if needed"""
        try:
            cursor = self.db_manager.connection.cursor()
            
            # Check if upload_files table exists
            check_query = """
            SELECT COUNT(*) as table_exists 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_files'
            """
            cursor.execute(check_query, (self.db_manager.rds_config['database'],))
            result = cursor.fetchone()
            
            # Create table if it doesn't exist
            if result[0] == 0:
                self.log_message("Creating upload_files table...")
                
                create_table_query = """
                CREATE TABLE upload_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_number VARCHAR(50) NOT NULL,
                    s3_key VARCHAR(1024) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    upload_status VARCHAR(20) NOT NULL,
                    upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_order_number (order_number),
                    INDEX idx_s3_key (s3_key(255))
                )
                """
                cursor.execute(create_table_query)
                
                # Add unique index to prevent duplicate uploads
                unique_index_query = """
                CREATE UNIQUE INDEX unq_upload_s3_key ON upload_files (s3_key(255))
                """
                cursor.execute(unique_index_query)
                
                self.db_manager.connection.commit()
                self.log_message("Created upload_files table successfully")
            else:
                # Check if we need to add preview columns
                check_column_query = """
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'upload_files' 
                AND COLUMN_NAME = 'has_preview'
                """
                cursor.execute(check_column_query, (self.db_manager.rds_config['database'],))
                has_preview_column = cursor.fetchone()[0]
                
                if has_preview_column == 0:
                    self.log_message("Adding preview columns to upload_files table...")
                    
                    add_columns_query = """
                    ALTER TABLE upload_files 
                    ADD COLUMN has_preview TINYINT(1) DEFAULT 0,
                    ADD COLUMN preview_path VARCHAR(1024)
                    """
                    cursor.execute(add_columns_query)
                    
                    self.db_manager.connection.commit()
                    self.log_message("Added preview columns successfully")
            
            cursor.close()
            
        except Exception as e:
            self.log_message(f"Database schema initialization error: {e}")
            import traceback
            self.log_message(traceback.format_exc())

    def quit_app(self):
        """Properly exit the application"""
        try:
            # Stop all running uploaders
            for task in self.upload_tasks:
                if task['status'] == 'running' and task['uploader']:
                    task['uploader'].stop()
                    task['uploader'].wait()  # Wait for the thread to finish
            
            # Close database connection
            if hasattr(self, 'db_manager'):
                self.db_manager.close()
            
            # Quit the application
            QApplication.quit()
        except Exception as e:
            self.log_message(f"Error during application shutdown: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            QApplication.quit()

    def closeEvent(self, event):
        """
        Handle window close event
        
        Args:
            event (QCloseEvent): Close event
        """
        try:
            # Check if any uploads are in progress
            running_tasks = [t for t in self.upload_tasks if t['status'] == 'running']
            if running_tasks:
                reply = QMessageBox.question(
                    self, 'Exit',
                    f'There are {len(running_tasks)} uploads in progress. Are you sure you want to quit?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    self.quit_app()
                else:
                    event.ignore()
                    return
            
            # If no uploads are running, just quit
            self.quit_app()
            event.accept()
            
        except Exception as e:
            self.log_message(f"Error during window close: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            event.accept()

    def load_pending_tasks(self):
        """Load pending tasks from database when application starts"""
        try:
            cursor = self.db_manager.connection.cursor(dictionary=True)
            query = """
            SELECT * FROM upload_tasks 
            WHERE status IN ('pending', 'running')
            ORDER BY task_id ASC
            """
            cursor.execute(query)
            tasks = cursor.fetchall()
            cursor.close()
            
            for task in tasks:
                # Create a task item for the list
                task_item = QListWidgetItem()
                task_item.setText(f"Task {task['task_id']}: Order {task['order_number']} - {task['status'].title()}")
                
                # Convert paths to Path objects for internal use
                task_data = {
                    'id': task['task_id'],
                    'order_number': task['order_number'],
                    'order_date': task['order_date'],
                    'folder_path': task['folder_path'],
                    'main_photographer_id': task['main_photographer_id'],
                    'assistant_photographer_id': task['assistant_photographer_id'],
                    'video_photographer_id': task['video_photographer_id'],
                    'status': task['status'],
                    'progress': task['progress'],
                    'local_path': task['local_path']
                }
                
                task_item.setData(Qt.UserRole, task_data)
                
                # Add to the list widget
                self.task_list.addItem(task_item)
                
                # Store the task data
                self.upload_tasks.append({
                    'id': task['task_id'],
                    'item': task_item,
                    **task_data,
                    'uploader': None
                })
            
            # Enable the start all button if we have tasks
            self.start_all_btn.setEnabled(len(self.upload_tasks) > 0)
            
            # Start the oldest pending task if no tasks are running
            if not any(task['status'] == 'running' for task in self.upload_tasks):
                pending_tasks = [t for t in self.upload_tasks if t['status'] == 'pending']
                if pending_tasks:
                    oldest_task = min(pending_tasks, key=lambda x: x['id'])
                    self.start_task(oldest_task)
            
        except Exception as e:
            self.log_message(f"Error loading pending tasks: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())