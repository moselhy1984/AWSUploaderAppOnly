#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QDateEdit, QFileDialog, QMessageBox, 
                            QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, QDate  # Make sure to import QDate here

from ui.photographers_dialog import PhotographersDialog
from ui.order_selector_dialog import OrderSelectorDialog

class TaskEditorDialog(QDialog):
    """
    Dialog for adding or modifying upload tasks
    """
    def __init__(self, db_manager, local_storage_path, task_data=None, parent=None):
        """
        Initialize the task editor dialog
        
        Args:
            db_manager: Database manager instance
            local_storage_path (str): Path to local storage
            task_data (dict, optional): Existing task data for editing. Defaults to None.
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.db_manager = db_manager
        self.local_storage_path = local_storage_path
        self.task_data = task_data
        self.parent = parent
        self.is_edit_mode = task_data is not None
        
        # Initialize photographers data
        if self.is_edit_mode:
            self.photographers = self.task_data['photographers'].copy()
        else:
            self.photographers = {
                'main': None,
                'assistant': None, 
                'video': None
            }
        
        self.current_order_path = None
        if self.is_edit_mode:
            # Ensure local_path exists in task_data, use folder_path if missing
            if 'local_path' not in self.task_data or not self.task_data['local_path']:
                self.task_data['local_path'] = self.task_data['folder_path']
                
            self.current_order_path = self.task_data['local_path']
        
        # Setup UI
        self.init_ui()
        
        # Load existing data if in edit mode
        if self.is_edit_mode:
            self.load_task_data()
    
    def init_ui(self):
        """Initialize user interface"""
        if self.is_edit_mode:
            self.setWindowTitle("Modify Upload Task")
        else:
            self.setWindowTitle("Add New Upload Task")
            
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        main_layout = QVBoxLayout()
        
        # Order Details Group
        order_group = QGroupBox("Order Details")
        order_layout = QFormLayout()
        
        # Date selection
        self.order_date = QDateEdit()
        self.order_date.setCalendarPopup(True)
        self.order_date.setDate(QDate.currentDate())
        self.order_date.dateChanged.connect(self.date_changed)
        order_layout.addRow("Order Date:", self.order_date)
        
        # Order number with selection button
        order_layout_h = QHBoxLayout()
        self.order_number = QLineEdit()
        self.order_number.setPlaceholderText("Enter or select order number")
        self.order_number.setEnabled(False)  # Disable by default
        order_layout_h.addWidget(self.order_number)
        
        select_order_btn = QPushButton("Select")
        select_order_btn.clicked.connect(self.select_order)
        order_layout_h.addWidget(select_order_btn)
        order_layout.addRow("Order Number:", order_layout_h)
        
        order_group.setLayout(order_layout)
        main_layout.addWidget(order_group)
        
        # Photographers Group
        photographers_group = QGroupBox("Photographers")
        photographers_layout = QFormLayout()
        
        # Photographer selection
        photographer_layout_h = QHBoxLayout()
        self.photographer_info = QLineEdit()
        self.photographer_info.setPlaceholderText("Select photographers...")
        self.photographer_info.setReadOnly(True)
        photographer_layout_h.addWidget(self.photographer_info)
        
        select_photographer_btn = QPushButton("Select")
        select_photographer_btn.clicked.connect(self.select_photographers)
        photographer_layout_h.addWidget(select_photographer_btn)
        photographers_layout.addRow("Photographers:", photographer_layout_h)
        
        photographers_group.setLayout(photographers_layout)
        main_layout.addWidget(photographers_group)
        
        # Folder Group
        folder_group = QGroupBox("Folders")
        folder_layout = QFormLayout()
        
        # Source folder
        source_layout = QHBoxLayout()
        self.folder_path = QLineEdit()
        self.folder_path.setPlaceholderText("Select source folder...")
        self.folder_path.setReadOnly(True)
        source_layout.addWidget(self.folder_path)
        
        browse_src_btn = QPushButton("Browse")
        browse_src_btn.clicked.connect(self.browse_folder)
        source_layout.addWidget(browse_src_btn)
        
        # Auto create path button
        create_path_btn = QPushButton("Auto Create")
        create_path_btn.clicked.connect(self.auto_create_path)
        create_path_btn.setToolTip("Automatically create order folders based on date and order number")
        source_layout.addWidget(create_path_btn)
        
        folder_layout.addRow("Source Folder:", source_layout)
        
        if self.is_edit_mode:
            # Add move files option in edit mode
            move_layout = QHBoxLayout()
            self.new_folder_path = QLineEdit()
            self.new_folder_path.setPlaceholderText("Select new location...")
            self.new_folder_path.setReadOnly(True)
            move_layout.addWidget(self.new_folder_path)
            
            browse_new_btn = QPushButton("Browse")
            browse_new_btn.clicked.connect(self.browse_new_folder)
            move_layout.addWidget(browse_new_btn)
            
            folder_layout.addRow("Move Files To:", move_layout)
        
        folder_group.setLayout(folder_layout)
        main_layout.addWidget(folder_group)
        
        # Add stretch to push buttons to bottom
        main_layout.addStretch()
        
        # Buttons at bottom
        button_layout = QHBoxLayout()
        if self.is_edit_mode:
            save_btn = QPushButton("Save Changes")
        else:
            save_btn = QPushButton("Add Task")
        save_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def load_task_data(self):
        """Load existing task data for editing"""
        # Set order date
        if isinstance(self.task_data['order_date'], QDate):
            self.order_date.setDate(self.task_data['order_date'])
        else:
            # If it's a Python date object
            qdate = QDate(
                self.task_data['order_date'].year,
                self.task_data['order_date'].month,
                self.task_data['order_date'].day
            )
            self.order_date.setDate(qdate)
        
        # Set order number
        self.order_number.setText(self.task_data['order_number'])
        self.order_number.setEnabled(True)  # Enable the field in edit mode
        
        # Set folder path
        self.folder_path.setText(self.task_data['folder_path'])
        
        # Set photographer info
        self.update_photographer_display()
    
    def date_changed(self):
        """Handle date selection changes"""
        if not self.is_edit_mode:
            # Clear order number in add mode
            self.order_number.setText("")
            # Disable the order number field when date changes
            self.order_number.setEnabled(False)
    
    def select_order(self):
        """Open order selection dialog"""
        # Enable the order number field when the select button is clicked
        self.order_number.setEnabled(True)
        
        # Set the selected date in the database manager
        selected_date = self.order_date.date().toPyDate().strftime('%Y-%m-%d')
        self.db_manager.selected_date = selected_date
        
        # Get orders for the selected date
        orders = self.db_manager.get_todays_orders()
        if not orders:
            # No orders found, ask if user wants to enter manually
            reply = QMessageBox.question(
                self, 
                "No Orders Found", 
                f"No orders found for {selected_date}. Would you like to enter an order number manually?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.order_number.setFocus()
            else:
                # If user chooses not to enter manually, disable the field again
                self.order_number.setEnabled(False)
            return
            
        # User wants to select from existing orders
        dialog = OrderSelectorDialog(orders, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_order_number = dialog.get_selected_order_id()
            if selected_order_number:
                self.order_number.setText(str(selected_order_number))
                
                # Auto create folder structure if not in edit mode
                if not self.is_edit_mode:
                    self.auto_create_path()
        else:
            # If user cancels the dialog without selecting, disable the field again
            if not self.order_number.text():
                self.order_number.setEnabled(False)
    
    def select_photographers(self):
        """Open photographer selection dialog"""
        photographers = self.db_manager.get_photographers()
        if not photographers:
            QMessageBox.warning(self, "Warning", "Could not fetch photographer list from database")
            return
        
        dialog = PhotographersDialog(photographers, self)
        if dialog.exec_() == QDialog.Accepted:
            self.photographers = dialog.get_selected_photographers()
            self.update_photographer_display(photographers)
    
    def update_photographer_display(self, photographers_list=None):
        """Update the photographer display text"""
        if photographers_list is None:
            # Fetch photographers if not provided
            photographers_list = self.db_manager.get_photographers()
            if not photographers_list:
                return
        
        photographer_text = []
        
        for photographer in photographers_list:
            if photographer['Emp_ID'] == self.photographers['main']:
                photographer_text.append(f"Main: {photographer['Emp_FullName']}")
        
        for photographer in photographers_list:
            if photographer['Emp_ID'] == self.photographers['assistant']:
                photographer_text.append(f"Assistant: {photographer['Emp_FullName']}")
        
        for photographer in photographers_list:
            if photographer['Emp_ID'] == self.photographers['video']:
                photographer_text.append(f"Video: {photographer['Emp_FullName']}")
        
        if photographer_text:
            self.photographer_info.setText(", ".join(photographer_text))
        else:
            self.photographer_info.setText("")
    
    def browse_folder(self):
        """Browse for source folder"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Source Folder')
        if folder:
            self.folder_path.setText(folder)
    
    def browse_new_folder(self):
        """Browse for new folder location (edit mode only)"""
        if not self.is_edit_mode:
            return
            
        folder = QFileDialog.getExistingDirectory(self, 'Select New Folder Location')
        if folder:
            self.new_folder_path.setText(folder)
    
    def auto_create_path(self):
        """Automatically create folder structure based on order details"""
        if not self.order_number.text():
            QMessageBox.warning(self, "Warning", "Please enter or select an order number first")
            return
            
        if not self.local_storage_path:
            QMessageBox.warning(self, "Warning", "Local storage path not configured")
            return
        
        try:
            # Create folder structure
            order_path = self.create_local_folders(self.order_number.text())
            if order_path:
                self.current_order_path = order_path
                self.folder_path.setText(str(order_path))
                
                # Ask if user wants to open the folder
                reply = QMessageBox.question(
                    self, 
                    "Open Folder", 
                    "Folder structure created successfully. Do you want to open it now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    self.open_folder(order_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create folder structure: {str(e)}")
    
    def create_local_folders(self, order_number):
        """
        Create folder structure for the selected order
        Format: YYYY/MM-YYYY/DD-MM-YYYY/Order_XXXXXX
        
        Args:
            order_number (str): Order number
            
        Returns:
            Path: Path to created folder structure or None if failed
        """
        if not self.local_storage_path:
            return None
        
        date_obj = self.order_date.date().toPyDate()
        year = date_obj.year
        month = f"{date_obj.month:02d}-{year}"  # MM-YYYY format
        day = f"{date_obj.day:02d}-{date_obj.month:02d}-{year}"  # DD-MM-YYYY format
        
        # Create folder structure: base_path/YYYY/MM-YYYY/DD-MM-YYYY/Order_XXXXXX
        base_path = Path(self.local_storage_path) / str(year) / month / day / f"Order_{order_number}"
        
        # Create the main folders
        folders = [
            base_path / "CR2",
            base_path / "JPG", 
            base_path / "Reels/Videos",
            base_path / "OTHER"
        ]
        
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        
        return base_path
    
    def open_folder(self, folder_path):
        """
        Open the folder in the default file explorer
        
        Args:
            folder_path (Path): Path to open
        """
        try:
            folder_str = str(folder_path)
            import sys
            if sys.platform == 'win32':
                os.startfile(folder_str)
            elif sys.platform == 'darwin':  # macOS
                import subprocess
                subprocess.Popen(['open', folder_str])
            else:  # Linux
                import subprocess
                subprocess.Popen(['xdg-open', folder_str])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open folder: {str(e)}")
    
    def move_files(self, source_path, target_path):
        """
        Move files from source to target path
        
        Args:
            source_path (Path): Source path
            target_path (Path): Target path
            
        Returns:
            tuple: (success, message)
        """
        try:
            if not source_path.exists():
                return False, "Source path does not exist"
                
            if not target_path.exists():
                # Create target path if it doesn't exist
                target_path.mkdir(parents=True, exist_ok=True)
            
            # For each category folder
            categories = ["CR2", "JPG", "Reels/Videos", "OTHER"]
            files_moved = 0
            
            for category in categories:
                category_path = source_path / category
                if not category_path.exists():
                    continue
                
                target_category_path = target_path / category
                target_category_path.mkdir(parents=True, exist_ok=True)
                
                # Move all files in this category
                for file_path in category_path.rglob('*'):
                    if not file_path.is_file():
                        continue
                    
                    # Calculate relative path from the category folder
                    rel_path = file_path.relative_to(category_path)
                    
                    # Create target directory structure
                    target_file_dir = target_category_path / rel_path.parent
                    target_file_dir.mkdir(parents=True, exist_ok=True)
                    
                    target_file = target_file_dir / rel_path.name
                    
                    # Move the file if it doesn't already exist
                    if not target_file.exists():
                        shutil.move(str(file_path), str(target_file))
                        files_moved += 1
            
            return True, f"Moved {files_moved} files successfully"
            
        except Exception as e:
            import traceback
            return False, f"Error moving files: {str(e)}\n{traceback.format_exc()}"
    
    def accept(self):
        """Process the dialog when accepted"""
        # Validate inputs
        if not self.order_number.text():
            QMessageBox.warning(self, "Error", "Please enter or select an order number")
            return
            
        if not self.folder_path.text():
            QMessageBox.warning(self, "Error", "Please select a source folder")
            return
            
        if not self.photographers['main']:
            QMessageBox.warning(self, "Error", "Please select a main photographer")
            return
        
        # If in edit mode and new folder path is specified, move files
        if self.is_edit_mode and hasattr(self, 'new_folder_path') and self.new_folder_path.text():
            source_path = Path(self.task_data['folder_path'])
            target_path = Path(self.new_folder_path.text())
            
            if source_path != target_path:
                reply = QMessageBox.question(
                    self, 
                    "Move Files", 
                    f"Are you sure you want to move all files from:\n{source_path}\nto:\n{target_path}?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    success, message = self.move_files(source_path, target_path)
                    if success:
                        QMessageBox.information(self, "Success", message)
                        # Update folder path
                        self.folder_path.setText(str(target_path))
                    else:
                        QMessageBox.warning(self, "Error", message)
                        return
        
        # Accept the dialog
        super().accept()
    
    def get_task_data(self):
        """
        Get the task data from the dialog
        
        Returns:
            dict: Task data
        """
        # Ensure current_order_path is set, use folder_path if it's None
        if self.current_order_path is None:
            self.current_order_path = self.folder_path.text()
        
        # Calculate relative path from base storage path
        full_path = Path(self.folder_path.text())
        base_storage = Path(self.local_storage_path)
        
        try:
            # Get the relative path from base storage (this will be the part from year onwards)
            relative_path = full_path.relative_to(base_storage)
            local_path_str = "/" + str(relative_path).replace("\\", "/")
        except ValueError:
            # If the path is not relative to base storage, use the full path
            local_path_str = str(full_path)
            
        task_data = {
            'order_number': self.order_number.text(),
            'order_date': self.order_date.date().toPyDate(),
            'folder_path': self.folder_path.text(),
            'photographers': self.photographers.copy(),
            'local_path': local_path_str
        }
        
        # If editing, preserve task ID
        if self.is_edit_mode:
            task_data['id'] = self.task_data['id']
        
        return task_data