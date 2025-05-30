#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QLineEdit, QFileDialog, QMessageBox,
                            QFrame, QGroupBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

class SettingsDialog(QDialog):
    """
    Settings dialog for managing application settings
    """
    def __init__(self, db_manager, mac_address, current_path=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.mac_address = mac_address
        self.current_path = current_path
        self.new_path = None
        
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setFixedSize(500, 200)
        
        # Set application icon
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'Uploadicon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # Try alternative path
            icon_path = 'Uploadicon.ico'
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Storage settings group
        storage_group = QGroupBox("Local Storage Settings")
        storage_layout = QVBoxLayout()
        
        # Current path display
        current_label = QLabel("Current Local Storage Path:")
        current_label.setStyleSheet("font-weight: bold;")
        storage_layout.addWidget(current_label)
        
        self.current_path_label = QLabel(self.current_path or "Not set")
        self.current_path_label.setStyleSheet("color: #666; padding: 5px; background-color: #f0f0f0; border-radius: 3px;")
        storage_layout.addWidget(self.current_path_label)
        
        # New path selection
        new_label = QLabel("Select New Path:")
        new_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        storage_layout.addWidget(new_label)
        
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select a folder for local storage...")
        self.path_input.setReadOnly(True)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_folder)
        
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_btn)
        storage_layout.addLayout(path_layout)
        
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }")
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_current_settings(self):
        """Load current settings from database"""
        if self.current_path:
            self.current_path_label.setText(self.current_path)
            self.path_input.setText(self.current_path)
    
    def browse_folder(self):
        """Browse for folder selection"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            'Select Local Storage Location',
            self.current_path or str(Path.home())
        )
        
        if folder:
            self.path_input.setText(folder)
            self.new_path = folder
    
    def save_settings(self):
        """Save settings to database"""
        new_path = self.path_input.text().strip()
        
        if not new_path:
            QMessageBox.warning(self, "Warning", "Please select a local storage path.")
            return
        
        if not os.path.exists(new_path):
            QMessageBox.warning(self, "Warning", "The selected path does not exist.")
            return
        
        # Update database
        if self.db_manager.update_device_storage_path(self.mac_address, new_path):
            self.new_path = new_path
            QMessageBox.information(self, "Success", "Settings saved successfully!")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save settings to database.")
    
    def get_new_path(self):
        """Get the new path if changed"""
        return self.new_path 