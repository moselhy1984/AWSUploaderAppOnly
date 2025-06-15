#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QProgressBar, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

class EnhancedProgressBars(QWidget):
    """
    Enhanced progress bars widget with custom task and file progress bars
    
    Features:
    - Task progress bar showing task number, order number, and percentage
    - File progress bar showing current file name and upload progress with data size
    - 3-pixel spacing between bars
    - Auto-hide when no active tasks
    - Proper height for the bars
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.current_task_id = None
        self.current_order_number = None
        self.total_tasks = 0
        self.completed_tasks = 0
        
    def init_ui(self):
        """Initialize the UI components"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove default margins
        layout.setSpacing(3)  # Exactly 3 pixels spacing between progress bars
        
        # All Tasks Progress Bar
        self.all_tasks_progress_bar = QProgressBar()
        self.all_tasks_progress_bar.setMinimum(0)
        self.all_tasks_progress_bar.setMaximum(100)
        self.all_tasks_progress_bar.setValue(0)
        self.all_tasks_progress_bar.setMinimumHeight(20)  # Reduced height
        self.all_tasks_progress_bar.setMaximumHeight(20)
        self.all_tasks_progress_bar.setFormat("🎯 All Tasks: No active tasks")
        self.all_tasks_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2E86AB;
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                font-size: 10pt;
                color: #FFFFFF;
                background-color: #E8E8E8;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2E86AB, stop:0.5 #1976D2, stop:1 #0D47A1);
                border-radius: 4px;
                margin: 1px;
            }
        """)
        
        # Current Task Progress Bar
        self.task_progress_bar = QProgressBar()
        self.task_progress_bar.setMinimum(0)
        self.task_progress_bar.setMaximum(100)
        self.task_progress_bar.setValue(0)
        self.task_progress_bar.setMinimumHeight(20)  # Reduced height
        self.task_progress_bar.setMaximumHeight(20)
        self.task_progress_bar.setFormat("📋 Current Task: No task running")
        self.task_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #A23B72;
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                font-size: 10pt;
                color: #FFFFFF;
                background-color: #E8E8E8;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #A23B72, stop:0.5 #8E24AA, stop:1 #6A1B9A);
                border-radius: 4px;
                margin: 1px;
            }
        """)
        
        # Current File Progress Bar
        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setMinimum(0)
        self.file_progress_bar.setMaximum(100)
        self.file_progress_bar.setValue(0)
        self.file_progress_bar.setMinimumHeight(20)  # Reduced height
        self.file_progress_bar.setMaximumHeight(20)
        self.file_progress_bar.setFormat("📄 Current File: No file uploading")
        self.file_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #F18F01;
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                font-size: 10pt;
                color: #FFFFFF;
                background-color: #E8E8E8;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #F18F01, stop:0.5 #FF9800, stop:1 #E65100);
                border-radius: 4px;
                margin: 1px;
            }
        """)
        
        # Add progress bars to layout with exact spacing
        layout.addWidget(self.all_tasks_progress_bar)
        layout.addWidget(self.task_progress_bar)
        layout.addWidget(self.file_progress_bar)
        
        self.setLayout(layout)
        
        # Initially hide the progress bars
        self.hide_progress_bars()
        
    def update_all_tasks_progress(self, completed_tasks, total_tasks):
        """
        Update the all tasks progress bar
        
        Args:
            completed_tasks (int): Number of completed tasks
            total_tasks (int): Total number of tasks
        """
        self.completed_tasks = completed_tasks
        self.total_tasks = total_tasks
        
        if total_tasks > 0:
            progress_percent = int((completed_tasks / total_tasks) * 100)
            self.all_tasks_progress_bar.setValue(progress_percent)
            self.all_tasks_progress_bar.setFormat(f"🎯 All Tasks: {completed_tasks}/{total_tasks} completed ({progress_percent}%)")
        else:
            self.all_tasks_progress_bar.setValue(0)
            self.all_tasks_progress_bar.setFormat("🎯 All Tasks: No active tasks")
        
        # Show progress bars if hidden
        self.show_progress_bars()
    
    def update_task_progress(self, task_id, order_number, progress_percent):
        """
        Update the current task progress bar
        
        Args:
            task_id (int): Task ID
            order_number (str): Order number
            progress_percent (float): Progress percentage (0-100)
        """
        # Convert to integer to avoid setValue type error
        progress_percent = int(progress_percent)
        
        # Update task progress bar
        self.task_progress_bar.setValue(progress_percent)
        self.task_progress_bar.setFormat(f"📋 Current Task: Order {order_number} - {progress_percent}%")
        
        # Show progress bars if hidden
        self.show_progress_bars()
        
        # Store current task info
        self.current_task_id = task_id
        self.current_order_number = order_number
        
    def update_file_progress(self, file_name, progress_percent, uploaded_bytes, total_bytes):
        """
        Update the current file progress bar
        
        Args:
            file_name (str): Current file name
            progress_percent (float): File progress percentage (0-100)
            uploaded_bytes (int): Bytes uploaded for current file
            total_bytes (int): Total bytes for current file
        """
        # Convert to integer to avoid setValue type error
        progress_percent = int(progress_percent)
        
        # Format file size
        uploaded_str = self._format_bytes(uploaded_bytes)
        total_str = self._format_bytes(total_bytes)
        
        # Update file progress bar
        self.file_progress_bar.setValue(progress_percent)
        self.file_progress_bar.setFormat(f"📄 Current File: {file_name} ({uploaded_str}/{total_str}) - {progress_percent}%")
        
        # Show progress bars if hidden
        self.show_progress_bars()
        
    def clear_file_progress(self):
        """Clear the file progress bar"""
        self.file_progress_bar.setValue(0)
        self.file_progress_bar.setFormat("📄 Current File: No file uploading")
        
    def show_progress_bars(self):
        """Show the progress bars widget"""
        self.setVisible(True)
        
    def hide_progress_bars(self):
        """Hide the progress bars widget"""
        self.setVisible(False)
        
    def clear_all_progress(self):
        """Clear all progress bars and hide the widget"""
        self.all_tasks_progress_bar.setValue(0)
        self.all_tasks_progress_bar.setFormat("🎯 All Tasks: No active tasks")
        self.task_progress_bar.setValue(0)
        self.task_progress_bar.setFormat("📋 Current Task: No task running")
        self.file_progress_bar.setValue(0)
        self.file_progress_bar.setFormat("📄 Current File: No file uploading")
        self.hide_progress_bars()
        
    def _format_bytes(self, bytes_value):
        """
        Format bytes into human readable format
        
        Args:
            bytes_value (int): Number of bytes
            
        Returns:
            str: Formatted string (e.g., "1.2MB", "500KB")
        """
        if bytes_value < 1024:
            return f"{bytes_value}B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f}KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f}MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.1f}GB"
            
    def has_active_tasks(self):
        """
        Check if there are active tasks
        
        Returns:
            bool: True if there are active tasks, False otherwise
        """
        return self.current_task_id is not None 