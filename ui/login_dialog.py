#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QFrame)
from PyQt5.QtCore import Qt
import hashlib
import os

class LoginDialog(QDialog):
    """Dialog for user authentication"""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Login")
        self.setFixedSize(400, 200)
        
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
        
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Please login to continue")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title_label)
        
        # Form
        form_frame = QFrame()
        form_frame.setFrameShape(QFrame.StyledPanel)
        form_layout = QVBoxLayout()
        
        # Username
        username_layout = QHBoxLayout()
        username_label = QLabel("Username:")
        self.username_input = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        form_layout.addLayout(username_layout)
        
        # Password
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        form_layout.addLayout(password_layout)
        
        form_frame.setLayout(form_layout)
        layout.addWidget(form_frame)
        
        # Buttons
        button_layout = QHBoxLayout()
        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self.try_login)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(login_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to username field
        self.username_input.setFocus()
        
    def try_login(self):
        """Attempt to login with provided credentials"""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "Error", "Please enter both username and password")
            return
        
        # Store credentials for the parent to use
        self._credentials = {
            'username': username,
            'password': password
        }
        
        # In a real app, you would authenticate here
        # For this example, we'll just accept the dialog
        self.accept()
        
    def get_user_credentials(self):
        """
        Get the user credentials entered in the dialog
        
        Returns:
            dict: Dictionary with username and password
        """
        return getattr(self, '_credentials', {'username': '', 'password': ''})
    
    @staticmethod
    def hash_password(password, salt=None):
        """
        Hash a password for secure storage
        
        Args:
            password (str): Password to hash
            salt (bytes, optional): Salt for hash. If None, a new salt is generated.
            
        Returns:
            tuple: (hashed_password, salt)
        """
        if salt is None:
            salt = os.urandom(32)  # 32 bytes for salt
            
        # Hash the password with the salt
        key = hashlib.pbkdf2_hmac(
            'sha256',  # Hash algorithm
            password.encode('utf-8'),  # Convert password to bytes
            salt,  # Salt
            100000  # Number of iterations
        )
        
        return key, salt
