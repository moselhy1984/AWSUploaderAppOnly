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
from ui.task_editor_dialog import TaskEditorDialog
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
        
        # Add buttons in logical order
        button_layout.addWidget(self.modify_task_btn)
        button_layout.addWidget(self.start_all_btn)
        button_layout.addWidget(self.pause_btn)
        button_layout.addWidget(self.resume_btn)
        button_layout.addWidget(self.restart_btn)
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
        self.log_text.append(f"[{timestamp}] {message}")
    
    def browse_local_storage(self):
        """Browse for local storage location"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Local Storage Location')
        if folder:
            self.local_storage.setText(folder)
            self.local_storage_path = folder
            self.settings.setValue("local_storage_path", folder)
            self.log_message(f"Local storage location set to: {folder}")
    
    def add_photoshoot_task(self):
        """Open dialog for adding a new photoshoot upload task"""
        if not self.local_storage_path:
            QMessageBox.warning(self, "Warning", "Please select a local storage location first")
            self.browse_local_storage()
            if not self.local_storage_path:
                return
        
        dialog = TaskEditorDialog(self.db_manager, self.local_storage_path, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            # Get task data from dialog
            task_data = dialog.get_task_data()
            
            # Create a unique task ID
            task_id = len(self.upload_tasks) + 1
            
            # Create a task item for the list
            task_item = QListWidgetItem()
            task_item.setText(f"Task {task_id}: Order {task_data['order_number']} - Pending")
            task_data_for_item = {
                'id': task_id,
                'order_number': task_data['order_number'],
                'order_date': task_data['order_date'],
                'folder_path': task_data['folder_path'],
                'photographers': task_data['photographers'],
                'status': 'pending',
                'progress': 0,
                'local_path': task_data['local_path']
            }
            task_item.setData(Qt.UserRole, task_data_for_item)
            
            # Add to the list widget
            self.task_list.addItem(task_item)
            
            # Store the task data
            self.upload_tasks.append({
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
            })
            
            # Enable the start all button if we have tasks
            self.start_all_btn.setEnabled(len(self.upload_tasks) > 0)
            
            self.log_message(f"Added new photoshoot task {task_id} for order {task_data['order_number']}")
    
    def modify_selected_task(self):
        """Open dialog for modifying the selected task"""
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Information", "No task selected")
            return
        
        task_data = selected_items[0].data(Qt.UserRole)
        task_id = task_data['id']
        
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
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
                if task['uploader']:
                    task['uploader'].stop()
                task['status'] = 'pending'
                task['progress'] = 0
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
            
            # Update the list item
            task['item'].setText(f"Task {task_id}: Order {updated_data['order_number']} - {task['status'].capitalize()}")
            
            # Update the data in the list item
            task_data_for_item = {
                'id': task_id,
                'order_number': updated_data['order_number'],
                'order_date': updated_data['order_date'],
                'folder_path': updated_data['folder_path'],
                'photographers': updated_data['photographers'],
                'status': task['status'],
                'progress': task['progress'],
                'local_path': updated_data['local_path']
            }
            task['item'].setData(Qt.UserRole, task_data_for_item)
            
            self.log_message(f"Modified task {task_id} for order {updated_data['order_number']}")
    
    def on_task_selected(self):
        """Handle task selection to enable/disable appropriate buttons"""
        selected_items = self.task_list.selectedItems()
        if not selected_items:
            # إذا لم يتم تحديد أي مهمة، قم بتعطيل جميع الأزرار المتعلقة بالمهام
            self.cancel_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.modify_task_btn.setEnabled(False)
            return
        
        # الحصول على المهمة المحددة
        task_data = selected_items[0].data(Qt.UserRole)
        task_id = task_data['id']
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        
        if not task:
            return
        
        # تمكين زر التعديل لجميع حالات المهام
        self.modify_task_btn.setEnabled(True)
        
        # تمكين/تعطيل الأزرار بناءً على حالة المهمة
        if task['status'] == 'running':
            self.cancel_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
        elif task['status'] == 'paused':
            self.cancel_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.restart_btn.setEnabled(False)
        elif task['status'] in ['completed', 'cancelled']:
            self.cancel_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(True)
        elif task['status'] == 'pending':
            self.cancel_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
    
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
        # First, organize files into their respective folders before uploading
        source_folder = task['folder_path']
        if source_folder:
            self.organize_files(source_folder, task['local_path'])
        
        # قبل بدء الرافع، نحتاج لتأكد من أنه لم يتم إيقافه مؤقتًا
        task['paused_state'] = False  # حالة الإيقاف المؤقت
        task['completed_files'] = []  # لتتبع الملفات المكتملة (للاستئناف)
        
        # Create a new uploader for this task
        uploader = BackgroundUploader(
            folder_path=task['folder_path'],
            order_number=task['order_number'],
            order_date=task['order_date'],
            aws_session=self.aws_session,
            photographers=task['photographers'],
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
        
        # تمكين زر الإيقاف المؤقت
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        
        # Start the uploader
        uploader.start()
        
        self.log_message(f"Started upload task {task['id']} for order {task['order_number']}")
    
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
        # Find the task
        task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
        if not task:
            return
        
        # Update task status
        task['status'] = 'completed'
        task['progress'] = 100
        
        # Update the list item
        task['item'].setText(f"Task {task['id']}: Order {task['order_number']} - Completed")
        
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
        """Pause the selected upload task"""
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
            
            # Only allow pausing running tasks
            if task['status'] != 'running':
                self.log_message(f"Can't pause task {task_id} because it's not running")
                continue
            
            # Set the pause flag on the uploader
            if task['uploader']:
                # Implement the pause feature in BackgroundUploader
                task['uploader'].pause()
                task['paused_state'] = True
                
                # Update task status
                task['status'] = 'paused'
                
                # Update the list item
                item.setText(f"Task {task_id}: Order {task['order_number']} - Paused ({task['progress']}%)")
                
                self.log_message(f"Paused upload task {task_id}")
                
                # Enable the resume button and disable the pause button
                self.resume_btn.setEnabled(True)
                self.pause_btn.setEnabled(False)

    def resume_selected_task(self):
        """Resume the paused upload task"""
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
            
            # Only allow resuming paused tasks
            if task['status'] != 'paused':
                self.log_message(f"Can't resume task {task_id} because it's not paused")
                continue
            
            # Reset the pause flag on the uploader
            if task['uploader']:
                # Implement the resume feature in BackgroundUploader
                task['uploader'].resume()
                task['paused_state'] = False
                
                # Update task status
                task['status'] = 'running'
                
                # Update the list item
                item.setText(f"Task {task_id}: Order {task['order_number']} - Running ({task['progress']}%)")
                
                self.log_message(f"Resumed upload task {task_id}")
                
                # Enable the pause button and disable the resume button
                self.pause_btn.setEnabled(True)
                self.resume_btn.setEnabled(False)

    def restart_selected_task(self):
        """Restart a completed or cancelled upload task"""
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
            
            # Only allow restarting completed or cancelled tasks
            if task['status'] not in ['completed', 'cancelled']:
                self.log_message(f"Can't restart task {task_id} because it's still active")
                continue
            
            # Reset task properties
            task['status'] = 'pending'
            task['progress'] = 0
            task['completed_files'] = []
            
            # Update the list item
            item.setText(f"Task {task_id}: Order {task['order_number']} - Pending")
            
            self.log_message(f"Reset upload task {task_id}, ready to restart")
            
            # Start the task immediately
            self.start_task(task)
            
            # Enable the pause button
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
    
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
    
    def save_task_to_database(self, task):
        """
        Save task to database for persistence
        
        Args:
            task (dict): Task information
        
        Returns:
            int: Database task ID or None if failed
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
            
            cursor = self.db_manager.connection.cursor()
            
            # Check if this task already exists in database
            if 'db_id' in task and task['db_id']:
                # Update existing task
                update_query = """
                UPDATE upload_tasks
                SET status = %s,
                    progress = %s,
                    last_updated = NOW(),
                    total_files = %s,
                    uploaded_files = %s,
                    skipped_files = %s
                WHERE task_id = %s
                """
                
                if task['status'] == 'completed' and not task.get('completed_timestamp'):
                    # Set completed timestamp
                    update_query = """
                    UPDATE upload_tasks
                    SET status = %s,
                        progress = %s,
                        last_updated = NOW(),
                        completed_timestamp = NOW(),
                        total_files = %s,
                        uploaded_files = %s,
                        skipped_files = %s
                    WHERE task_id = %s
                    """
                
                # Get file counts from uploader if available
                total_files = 0
                uploaded_files = 0
                skipped_files = 0
                
                if 'uploader' in task and task['uploader']:
                    uploader = task['uploader']
                    uploaded_files = getattr(uploader, 'uploaded_file_count', 0)
                    skipped_files = getattr(uploader, 'skipped_file_count', 0)
                    total_files = uploaded_files + skipped_files
                
                cursor.execute(update_query, (
                    task['status'],
                    task['progress'],
                    total_files,
                    uploaded_files,
                    skipped_files,
                    task['db_id']
                ))
                
                self.db_manager.connection.commit()
                return task['db_id']
            else:
                # Insert new task
                insert_query = """
                INSERT INTO upload_tasks (
                    order_number,
                    order_date,
                    folder_path,
                    main_photographer_id,
                    assistant_photographer_id,
                    video_photographer_id,
                    status,
                    progress
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                # Convert date if needed
                order_date = task['order_date']
                if not isinstance(order_date, str):
                    order_date = order_date.strftime('%Y-%m-%d')
                
                # Get photographer IDs
                main_photographer_id = task['photographers']['main'] if task['photographers']['main'] else None
                assistant_photographer_id = task['photographers']['assistant'] if task['photographers']['assistant'] else None
                video_photographer_id = task['photographers']['video'] if task['photographers']['video'] else None
                
                cursor.execute(insert_query, (
                    task['order_number'],
                    order_date,
                    task['folder_path'],
                    main_photographer_id,
                    assistant_photographer_id,
                    video_photographer_id,
                    task['status'],
                    task['progress']
                ))
                
                self.db_manager.connection.commit()
                db_id = cursor.lastrowid
                
                return db_id
        
        except Exception as e:
            self.log_message(f"Error saving task to database: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return None

    def load_tasks_from_database(self):
        """
        Load tasks from database when app starts
        
        Returns:
            list: List of tasks loaded from database
        """
        try:
            if not self.db_manager.connection or not self.db_manager.connection.is_connected():
                self.db_manager.connect()
            
            cursor = self.db_manager.connection.cursor(dictionary=True)
            
            # Check if upload_tasks table exists
            check_query = """
            SELECT COUNT(*) as table_exists 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks'
            """
            cursor.execute(check_query, (self.db_manager.rds_config['database'],))
            result = cursor.fetchone()
            
            if not result or result['table_exists'] == 0:
                # Create the table if it doesn't exist
                create_table_query = """
                CREATE TABLE `upload_tasks` (
                `task_id` int NOT NULL AUTO_INCREMENT,
                `order_number` varchar(50) NOT NULL,
                `order_date` date NOT NULL,
                `folder_path` varchar(1024) NOT NULL,
                `main_photographer_id` int DEFAULT NULL,
                `assistant_photographer_id` int DEFAULT NULL,
                `video_photographer_id` int DEFAULT NULL,
                `status` varchar(20) NOT NULL,
                `progress` int DEFAULT 0,
                `created_timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
                `last_updated` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                `completed_timestamp` timestamp NULL DEFAULT NULL,
                `total_files` int DEFAULT 0,
                `uploaded_files` int DEFAULT 0,
                `skipped_files` int DEFAULT 0,
                PRIMARY KEY (`task_id`),
                KEY `idx_task_order` (`order_number`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
                """
                cursor.execute(create_table_query)
                self.db_manager.connection.commit()
                self.log_message("Created upload_tasks table for task persistence")
                return []
            
            # Load recent tasks (from last 7 days and non-completed tasks)
            query = """
            SELECT 
                t.*,
                e1.Emp_FullName as main_photographer_name,
                e2.Emp_FullName as assistant_photographer_name,
                e3.Emp_FullName as video_photographer_name
            FROM 
                upload_tasks t
            LEFT JOIN employees e1 ON t.main_photographer_id = e1.Emp_ID
            LEFT JOIN employees e2 ON t.assistant_photographer_id = e2.Emp_ID
            LEFT JOIN employees e3 ON t.video_photographer_id = e3.Emp_ID
            WHERE 
                t.created_timestamp > DATE_SUB(NOW(), INTERVAL 7 DAY)
                OR t.status IN ('pending', 'running', 'paused')
            ORDER BY 
                t.last_updated DESC
            """
            cursor.execute(query)
            db_tasks = cursor.fetchall()
            
            # Convert to our task format
            tasks = []
            for db_task in db_tasks:
                # Create task item for display
                task_item = QListWidgetItem()
                task_status = db_task['status'].capitalize()
                progress = db_task['progress']
                
                if db_task['status'] in ['running', 'paused']:
                    task_item.setText(f"Task {db_task['task_id']}: Order {db_task['order_number']} - {task_status} ({progress}%)")
                else:
                    task_item.setText(f"Task {db_task['task_id']}: Order {db_task['order_number']} - {task_status}")
                
                # Create photographers dict
                photographers = {
                    'main': db_task['main_photographer_id'],
                    'assistant': db_task['assistant_photographer_id'],
                    'video': db_task['video_photographer_id']
                }
                
                # Create task data for item
                item_data = {
                    'id': db_task['task_id'],  # Use database ID for task
                    'order_number': db_task['order_number'],
                    'order_date': db_task['order_date'],
                    'folder_path': db_task['folder_path'],
                    'photographers': photographers,
                    'status': db_task['status'],
                    'progress': db_task['progress'],
                    'local_path': db_task['folder_path'],  # Use folder path as local path
                    'db_id': db_task['task_id']  # Store database ID
                }
                
                # Set data for item
                task_item.setData(Qt.UserRole, item_data)
                
                # Add to list widget
                self.task_list.addItem(task_item)
                
                # Add task to our list
                task = {
                    'id': db_task['task_id'],
                    'item': task_item,
                    'order_number': db_task['order_number'],
                    'order_date': db_task['order_date'],
                    'folder_path': db_task['folder_path'],
                    'photographers': photographers,
                    'uploader': None,  # No active uploader yet
                    'status': db_task['status'],
                    'progress': db_task['progress'],
                    'local_path': db_task['folder_path'],
                    'db_id': db_task['task_id']
                }
                
                tasks.append(task)
                
                # Log loaded task
                photographer_info = []
                if db_task.get('main_photographer_name'):
                    photographer_info.append(f"Main: {db_task['main_photographer_name']}")
                if db_task.get('assistant_photographer_name'):
                    photographer_info.append(f"Asst: {db_task['assistant_photographer_name']}")
                if db_task.get('video_photographer_name'):
                    photographer_info.append(f"Video: {db_task['video_photographer_name']}")
                
                photographer_text = ", ".join(photographer_info) if photographer_info else "No photographers"
                
                self.log_message(f"Loaded task {db_task['task_id']} for order {db_task['order_number']} - Status: {db_task['status']}, {photographer_text}")
            
            return tasks
        
        except Exception as e:
            self.log_message(f"Error loading tasks from database: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            return []


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
        # Check for running tasks
        running_tasks = [t for t in self.upload_tasks if t['status'] in ['running', 'paused']]
        if running_tasks:
            reply = QMessageBox.question(
                self, 'Exit',
                f'There are {len(running_tasks)} active upload tasks. Are you sure you want to quit?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
                
            # Stop all running tasks
            for task in running_tasks:
                if task['uploader']:
                    task['uploader'].stop()
        
        # Close database connection
        self.db_manager.close()
        QApplication.quit()
    
    def closeEvent(self, event):
        """
        Handle window close event
        
        Args:
            event (QCloseEvent): Close event
        """
        # Check for running tasks
        running_tasks = [t for t in self.upload_tasks if t['status'] in ['running', 'paused']]
        if running_tasks:
            reply = QMessageBox.question(
                self, 'Exit',
                f'There are {len(running_tasks)} active upload tasks. Are you sure you want to quit?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                event.ignore()
                return
                
            # Stop all running tasks
            for task in running_tasks:
                if task['uploader']:
                    task['uploader'].stop()
        
        event.accept()