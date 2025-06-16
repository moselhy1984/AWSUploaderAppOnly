#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Full Image Dialog
Shows a single image in full size from S3 bucket
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QScrollArea, QWidget, QFrame)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QFont
import threading


class FullImageDialog(QDialog):
    """Dialog for viewing a single image in full size"""
    
    def __init__(self, image_key, file_name, aws_session, parent=None):
        super().__init__(parent)
        self.image_key = image_key
        self.file_name = file_name
        self.aws_session = aws_session
        
        self.setWindowTitle(f"Full Image - {file_name}")
        self.setModal(True)
        self.resize(800, 600)
        
        self.init_ui()
        self.load_full_image()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Header
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 10px;")
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel(f"🖼️ {self.file_name}")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)
        
        layout.addWidget(header_frame)
        
        # Loading indicator
        self.loading_label = QLabel("🔄 Loading full image...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14pt; color: #007acc; margin: 40px;")
        layout.addWidget(self.loading_label)
        
        # Scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVisible(False)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumSize(100, 35)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_full_image(self):
        """Load the full image from S3"""
        try:
            self.loader_thread = FullImageLoaderThread(
                self.image_key, 
                self.aws_session
            )
            self.loader_thread.image_loaded.connect(self.display_image)
            self.loader_thread.error_occurred.connect(self.show_error)
            self.loader_thread.start()
            
        except Exception as e:
            self.show_error(f"Error loading image: {str(e)}")
    
    def display_image(self, pixmap):
        """Display the loaded image"""
        if pixmap and not pixmap.isNull():
            # Scale image to fit dialog while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                700, 500, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            self.loading_label.setVisible(False)
            self.scroll_area.setVisible(True)
        else:
            self.show_error("Failed to load image")
    
    def show_error(self, message):
        """Show error message"""
        self.loading_label.setText(f"❌ {message}")
        self.loading_label.setStyleSheet("color: #dc3545; font-size: 14pt; margin: 40px;")


class FullImageLoaderThread(QThread):
    """Thread for loading full size image from S3"""
    
    image_loaded = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, image_key, aws_session):
        super().__init__()
        self.image_key = image_key
        self.aws_session = aws_session
    
    def run(self):
        """Load the full image"""
        try:
            bucket_name = "balistudiostorage"
            s3_client = self.aws_session.client('s3')
            
            # Download image
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=self.image_key
            )
            
            image_data = response['Body'].read()
            
            # Convert to QPixmap
            pixmap = QPixmap()
            success = pixmap.loadFromData(image_data)
            
            if success:
                self.image_loaded.emit(pixmap)
            else:
                self.error_occurred.emit("Invalid image format")
                
        except Exception as e:
            self.error_occurred.emit(str(e)) 