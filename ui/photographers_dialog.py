#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QComboBox, QPushButton)

class PhotographersDialog(QDialog):
    """
    Dialog for selecting main, assistant, and video photographers
    """
    def __init__(self, photographers, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select Photographers')
        self.setFixedWidth(500)
        
        self.photographers = photographers
        
        layout = QVBoxLayout()
        
        # Main photographer selector
        main_layout = QHBoxLayout()
        main_layout.addWidget(QLabel("Main Photographer:"))
        
        self.main_photographer = QComboBox()
        self.main_photographer.addItem("-- Select Main Photographer --", None)
        for photog in photographers:
            self.main_photographer.addItem(photog['Emp_FullName'], photog['Emp_ID'])
        main_layout.addWidget(self.main_photographer)
        layout.addLayout(main_layout)
        
        # Assistant photographer selector
        assistant_layout = QHBoxLayout()
        assistant_layout.addWidget(QLabel("Assistant Photographer:"))
        
        self.assistant_photographer = QComboBox()
        self.assistant_photographer.addItem("-- Select Assistant (Optional) --", None)
        for photog in photographers:
            self.assistant_photographer.addItem(photog['Emp_FullName'], photog['Emp_ID'])
        assistant_layout.addWidget(self.assistant_photographer)
        layout.addLayout(assistant_layout)
        
        # Video photographer selector
        video_layout = QHBoxLayout()
        video_layout.addWidget(QLabel("Video Photographer:"))
        
        self.video_photographer = QComboBox()
        self.video_photographer.addItem("-- Select Video Photographer (Optional) --", None)
        for photog in photographers:
            self.video_photographer.addItem(photog['Emp_FullName'], photog['Emp_ID'])
        video_layout.addWidget(self.video_photographer)
        layout.addLayout(video_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
    
    def get_selected_photographers(self):
        """
        Get the selected photographers IDs
        
        Returns:
            dict: Dictionary with main, assistant, and video photographer IDs
        """
        return {
            'main': self.main_photographer.currentData(),
            'assistant': self.assistant_photographer.currentData(),
            'video': self.video_photographer.currentData()
        }
