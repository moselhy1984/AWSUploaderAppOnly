#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QDateEdit, QFileDialog, QMessageBox, 
                            QGroupBox, QFormLayout, QCheckBox, QProgressBar, 
                            QTextEdit, QRadioButton, QButtonGroup, QWidget)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication

from ui.photographers_dialog import PhotographersDialog
from ui.order_selector_dialog import OrderSelectorDialog

class SimpleCopyWorker(QThread):
    """عامل بسيط لنسخ الملفات مع تقدم"""
    
    progress_updated = pyqtSignal(int, str)
    copy_completed = pyqtSignal(bool, str)
    
    def __init__(self, source_paths, destination_path, copy_all_files=True):
        super().__init__()
        self.source_paths = source_paths
        self.destination_path = Path(destination_path)
        self.copy_all_files = copy_all_files
        self.cancelled = False
        
    def cancel(self):
        self.cancelled = True
        
    def run(self):
        try:
            # إنشاء مجلد الوجهة
            self.destination_path.mkdir(parents=True, exist_ok=True)
            
            # جمع جميع الملفات
            all_files = []
            for source_path in self.source_paths:
                source = Path(source_path)
                if source.is_file():
                    all_files.append(source)
                elif source.is_dir():
                    if self.copy_all_files:
                        # نسخ جميع الملفات من المجلد
                        for file_path in source.rglob('*'):
                            if file_path.is_file() and not file_path.name.startswith('.'):
                                all_files.append(file_path)
                    else:
                        # نسخ فقط ملفات الكاميرا
                        camera_extensions = {'.jpg', '.jpeg', '.cr2', '.cr3', '.nef', 
                                           '.arw', '.raw', '.dng', '.mp4', '.mov'}
                        for file_path in source.rglob('*'):
                            if (file_path.is_file() and 
                                file_path.suffix.lower() in camera_extensions and 
                                not file_path.name.startswith('.')):
                                all_files.append(file_path)
            
            if not all_files:
                self.copy_completed.emit(False, "No files found to copy")
                return
                
            self.progress_updated.emit(0, f"Starting copy of {len(all_files)} files...")
            
            copied_count = 0
            for i, file_path in enumerate(all_files):
                if self.cancelled:
                    self.copy_completed.emit(False, "Copy cancelled")
                    return
                    
                try:
                    # تحديد مسار الوجهة
                    dest_file = self.destination_path / file_path.name
                    
                    # تجنب تكرار الأسماء
                    counter = 1
                    original_dest = dest_file
                    while dest_file.exists():
                        stem = original_dest.stem
                        suffix = original_dest.suffix
                        dest_file = original_dest.parent / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    # نسخ الملف
                    shutil.copy2(file_path, dest_file)
                    copied_count += 1
                    
                    # تحديث التقدم
                    progress = int((i + 1) / len(all_files) * 100)
                    self.progress_updated.emit(progress, f"Copied {file_path.name}")
                    
                except Exception as e:
                    continue  # تجاهل الملفات التي فشل نسخها
                    
            if copied_count > 0:
                self.copy_completed.emit(True, f"Successfully copied {copied_count} files")
            else:
                self.copy_completed.emit(False, "No files were copied successfully")
                
        except Exception as e:
            self.copy_completed.emit(False, f"Copy failed: {str(e)}")

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
        
        # إعداد نظام النسخ البسيط
        self.copy_worker = None
        self.selected_source_paths = []
        
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
            
        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'Uploadicon.ico')
        if os.path.exists(icon_path):
            from PyQt5.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        else:
            # Try alternative path
            icon_path = 'Uploadicon.ico'
            if os.path.exists(icon_path):
                from PyQt5.QtGui import QIcon
                self.setWindowIcon(QIcon(icon_path))
            
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        
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
        self.order_number.textChanged.connect(self.order_number_changed)
        order_layout_h.addWidget(self.order_number)
        
        select_order_btn = QPushButton("Select")
        select_order_btn.clicked.connect(self.select_order)
        order_layout_h.addWidget(select_order_btn)
        order_layout.addRow("Order Number:", order_layout_h)
        
        order_group.setLayout(order_layout)
        main_layout.addWidget(order_group)

        # Copy from Source Group (فقط في وضع الإضافة)
        if not self.is_edit_mode:
            copy_group = QGroupBox("📁 Copy Files from Source (Optional)")
            copy_layout = QVBoxLayout()
            
            # اختيار المصدر - نشط دائماً
            source_select_layout = QHBoxLayout()
            self.source_path_edit = QLineEdit()
            self.source_path_edit.setPlaceholderText("No source selected...")
            self.source_path_edit.setReadOnly(True)
            
            self.browse_files_btn = QPushButton("📄 Select Files")
            self.browse_files_btn.clicked.connect(self.browse_files)
            
            self.browse_folder_btn = QPushButton("📁 Select Folder")
            self.browse_folder_btn.clicked.connect(self.browse_source_folder)
            
            source_select_layout.addWidget(self.source_path_edit)
            source_select_layout.addWidget(self.browse_files_btn)
            source_select_layout.addWidget(self.browse_folder_btn)
            copy_layout.addLayout(source_select_layout)
            
            # ملاحظة للمستخدم
            note_label = QLabel("Note: Only camera files will be copied automatically when adding task")
            note_label.setStyleSheet("color: gray; font-style: italic;")
            copy_layout.addWidget(note_label)
            
            copy_group.setLayout(copy_layout)
            main_layout.addWidget(copy_group)
        
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
        self.folder_path.setPlaceholderText("Order folder will be created automatically...")
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
        
        folder_layout.addRow("Order Folder:", source_layout)
        
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
    
    def order_number_changed(self):
        """عند تغيير رقم الأوردر، لا نفعل شيء - سيتم إنشاء المجلد عند إضافة المهمة"""
        pass
            
    def browse_files(self):
        """اختيار ملفات للنسخ"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files to Copy", "", 
            "Image/Video Files (*.jpg *.jpeg *.cr2 *.cr3 *.nef *.arw *.raw *.dng *.mp4 *.mov);;All Files (*)"
        )
        if files:
            self.source_path_edit.setText(f"{len(files)} files selected")
            self.selected_source_paths = files
            
    def browse_source_folder(self):
        """اختيار مجلد للنسخ"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Copy")
        if folder:
            self.source_path_edit.setText(folder)
            self.selected_source_paths = [folder]
    
    def start_copy_process(self):
        """بدء عملية النسخ البسيطة - ملفات الكاميرا فقط"""
        if not self.selected_source_paths:
            return False, "No source files or folder selected"
            
        if not self.folder_path.text():
            return False, "Order folder not created yet"
            
        try:
            # إنشاء العامل للنسخ - ملفات الكاميرا فقط
            self.copy_worker = SimpleCopyWorker(
                self.selected_source_paths,
                self.folder_path.text(),
                False  # copy_all_files = False (ملفات الكاميرا فقط)
            )
            
            self.copy_worker.start()
            
            # انتظار انتهاء النسخ
            while self.copy_worker and self.copy_worker.isRunning():
                QApplication.processEvents()
            
            return True, "Camera files copied successfully"
            
        except Exception as e:
            return False, f"Copy failed: {str(e)}"
            
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
        for role, photographer_id in self.photographers.items():
            if photographer_id:
                photographer = next((p for p in photographers_list if p['Emp_ID'] == photographer_id), None)
                if photographer:
                    role_label = {
                        'main': 'Main',
                        'assistant': 'Assistant', 
                        'video': 'Video'
                    }.get(role, role.title())
                    photographer_text.append(f"{role_label}: {photographer['Emp_FullName']}")
        
        if photographer_text:
            self.photographer_info.setText(" | ".join(photographer_text))
        else:
            self.photographer_info.setText("No photographers selected")
    
    def browse_folder(self):
        """Browse for source folder"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Source Folder')
        if folder:
            self.folder_path.setText(folder)
            # Store the selected path
            self.current_order_path = folder
    
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
        """Create local folder structure for the order"""
        try:
            # Get the selected date
            selected_date = self.order_date.date().toPyDate()
            
            # Create the folder path
            year = selected_date.year
            month = f"{selected_date.month:02d}-{year}"
            day = f"{selected_date.day:02d}-{selected_date.month:02d}-{year}"
            
            # Create the full path
            base_path = Path(self.local_storage_path) / "Booking_Folders"
            order_folder = base_path / str(year) / month / day / f"Order_{order_number}"
            
            # Create the directories
            order_folder.mkdir(parents=True, exist_ok=True)
            
            # Create category subfolders
            categories = ['CR2', 'JPG', 'Reels/Videos', 'OTHER', 'Archive']
            for category in categories:
                category_path = order_folder / category
                category_path.mkdir(parents=True, exist_ok=True)
            
            return order_folder
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error creating folders: {str(e)}")
            return None
    
    def open_folder(self, folder_path):
        """Open folder in file explorer"""
        try:
            import subprocess
            import platform
            
            folder_str = str(folder_path)
            
            if platform.system() == "Windows":
                os.startfile(folder_str)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", folder_str])
            else:  # Linux
                subprocess.Popen(["xdg-open", folder_str])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open folder: {str(e)}")
    
    def move_files(self, source_path, target_path):
        """Move files from source to target path"""
        try:
            # Create target directory if it doesn't exist
            target_path.mkdir(parents=True, exist_ok=True)
            
            # Move all files and subdirectories
            for item in source_path.iterdir():
                target_item = target_path / item.name
                if item.is_dir():
                    shutil.move(str(item), str(target_item))
                else:
                    shutil.move(str(item), str(target_item))
            
            # Remove the empty source directory
            source_path.rmdir()
            
            return True, f"Files moved successfully from {source_path} to {target_path}"
            
        except Exception as e:
            return False, f"Error moving files: {str(e)}"
    
    def accept(self):
        """Process the dialog when accepted"""
        # Validate inputs
        if not self.order_number.text():
            QMessageBox.warning(self, "Error", "Please enter or select an order number")
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
        
        # في وضع الإضافة: إنشاء المجلد والنسخ
        if not self.is_edit_mode:
            # إنشاء مجلد الأوردر
            if not self.folder_path.text():  # إذا لم يتم إنشاء المجلد بعد
                order_path = self.create_local_folders(self.order_number.text())
                if not order_path:
                    QMessageBox.critical(self, "Error", "Failed to create order folder")
                    return
                self.current_order_path = order_path
                self.folder_path.setText(str(order_path))
            
            # إذا تم اختيار ملفات للنسخ - تنفيذ تلقائي
            if self.selected_source_paths:
                # إظهار رسالة التقدم
                progress_msg = QMessageBox(self)
                progress_msg.setWindowTitle("Processing Task")
                progress_msg.setText("Copying camera files, please wait...")
                progress_msg.setStandardButtons(QMessageBox.NoButton)
                progress_msg.show()
                QApplication.processEvents()
                
                success, message = self.start_copy_process()
                progress_msg.close()
                
                if not success:
                    QMessageBox.warning(self, "Copy Failed", message)
                    return
        
        # Accept the dialog
        super().accept()
        
        # بدء الرفع التلقائي بعد إضافة المهمة (في وضع الإضافة فقط)
        if not self.is_edit_mode and self.parent:
            try:
                # الحصول على آخر مهمة مضافة والبدء بالرفع
                if hasattr(self.parent, 'upload_tasks') and self.parent.upload_tasks:
                    # العثور على المهمة الأخيرة المضافة
                    latest_task = self.parent.upload_tasks[-1]
                    # بدء الرفع تلقائياً
                    if hasattr(self.parent, 'start_task'):
                        self.parent.start_task(latest_task)
            except Exception as e:
                pass  # تجاهل الأخطاء في بدء الرفع
    
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