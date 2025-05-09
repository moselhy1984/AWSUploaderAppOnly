#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton)

class LoginDialog(QDialog):
    """
    Dialog for user login with username and password fields
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Login')
        self.setFixedWidth(400)
        self.layout = QVBoxLayout()
        
        instructions = QLabel("Please enter your username and password")
        instructions.setWordWrap(True)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        
        self.submit_btn = QPushButton('Login')
        self.submit_btn.clicked.connect(self.accept)
        
        self.layout.addWidget(instructions)
        self.layout.addWidget(QLabel("Username:"))
        self.layout.addWidget(self.username_input)
        self.layout.addWidget(QLabel("Password:"))
        self.layout.addWidget(self.password_input)
        self.layout.addWidget(self.submit_btn)
        
        self.setLayout(self.layout)
    
    def get_credentials(self):
        """
        Get entered username and password
        
        Returns:
            tuple: (username, password)
        """
        return self.username_input.text(), self.password_input.text()
