#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import traceback
from pathlib import Path
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QWidget, QLabel, QPushButton,
                            QScrollArea, QGridLayout, QFrame, QTextEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import os

class ImagePreviewDialog(QDialog):
    """
    Dialog for displaying image previews for an order
    """
    def __init__(self, order_number, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Image Previews - Order {order_number}')
        self.setFixedSize(800, 600)
        self.order_number = order_number
        self.parent = parent
        
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
        
        # Main layout
        layout = QVBoxLayout()
        
        # Information label
        info_label = QLabel(f"Image previews for Order {order_number}")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # Thumbnail grid
        self.grid_layout = QVBoxLayout()
        grid_container = QWidget()
        grid_container.setLayout(self.grid_layout)
        
        # Create a scroll area for the thumbnails
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_container)
        layout.addWidget(scroll_area)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
        
        self.setLayout(layout)
        
        # Load the preview images
        self.load_previews()
    
    def load_previews(self):
        """
        Load preview thumbnails for the order
        """
        try:
            # Get list of image files for this order
            if hasattr(self.parent, 'db_manager'):
                db_manager = self.parent.db_manager
                
                if not db_manager.connection or not db_manager.connection.is_connected():
                    db_manager.connect()
                
                cursor = db_manager.connection.cursor(dictionary=True)
                
                # Check if the upload_files table exists
                check_query = """
                SELECT COUNT(*) as table_exists 
                FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'upload_files'
                """
                cursor.execute(check_query, (db_manager.rds_config['database'],))
                result = cursor.fetchone()
                
                if not result or result['table_exists'] == 0:
                    # Table doesn't exist yet
                    label = QLabel("No image previews available. Upload files first.")
                    label.setAlignment(Qt.AlignCenter)
                    self.grid_layout.addWidget(label)
                    return
                
                # Get image files for this order (JPG, PNG, etc.)
                query = """
                SELECT file_name, s3_key, file_type
                FROM upload_files
                WHERE order_number = %s
                AND (file_type = 'JPG' OR file_name LIKE '%.jpg' OR file_name LIKE '%.jpeg' 
                     OR file_name LIKE '%.png' OR file_name LIKE '%.gif')
                ORDER BY upload_timestamp DESC
                LIMIT 20
                """
                cursor.execute(query, (self.order_number,))
                images = cursor.fetchall()
                cursor.close()
                
                if not images:
                    label = QLabel("No image files found for this order.")
                    label.setAlignment(Qt.AlignCenter)
                    self.grid_layout.addWidget(label)
                    return
                
                # Find local storage path from parent
                local_storage_path = ""
                if hasattr(self.parent, 'local_storage_path'):
                    local_storage_path = self.parent.local_storage_path
                
                if not local_storage_path:
                    label = QLabel("Local storage path not configured. Cannot display previews.")
                    label.setAlignment(Qt.AlignCenter)
                    self.grid_layout.addWidget(label)
                    return
                
                # Create date path components from current order
                order_details = db_manager.get_order_details(self.order_number)
                if not order_details or not order_details.get('order'):
                    label = QLabel("Could not retrieve order details.")
                    label.setAlignment(Qt.AlignCenter)
                    self.grid_layout.addWidget(label)
                    return
                
                order_date = order_details['order']['order_date']
                if isinstance(order_date, str):
                    # Convert string to datetime if needed
                    from datetime import datetime
                    try:
                        order_date = datetime.strptime(order_date.split()[0], '%Y-%m-%d')
                    except Exception:
                        # Try another format
                        try:
                            order_date = datetime.strptime(order_date, '%Y-%m-%d')
                        except Exception:
                            label = QLabel("Could not parse order date.")
                            label.setAlignment(Qt.AlignCenter)
                            self.grid_layout.addWidget(label)
                            return
                
                year = order_date.year
                month = f"{order_date.month:02d}-{year}"
                day = f"{order_date.day:02d}-{month}"
                
                # Add a label with the count of images
                count_label = QLabel(f"Found {len(images)} images (showing up to 20)")
                count_label.setAlignment(Qt.AlignCenter)
                self.grid_layout.addWidget(count_label)
                
                # Create a grid for the thumbnails
                image_grid = QGridLayout()
                columns = 4  # Number of columns in the grid
                
                for i, image_info in enumerate(images):
                    # Try to find the local file path
                    file_name = image_info['file_name']
                    file_type = image_info['file_type']
                    
                    # Construct path based on the S3 key structure
                    s3_key = image_info['s3_key']
                    s3_parts = s3_key.split('/')
                    
                    # Look in the relevant category folder
                    if file_type == 'JPG' or file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        category = "JPG"
                    else:
                        continue  # Skip non-image files
                    
                    local_file_path = Path(local_storage_path) / str(year) / month / day / f"Order_{self.order_number}" / category / file_name
                    
                    # Check if file exists
                    if local_file_path.exists():
                        # Create a thumbnail
                        
                        # Create frame for the image and label
                        frame = QFrame()
                        frame.setFrameShape(QFrame.Box)
                        frame.setLineWidth(1)
                        frame_layout = QVBoxLayout()
                        
                        # Add the image
                        pixmap = QPixmap(str(local_file_path))
                        pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        
                        image_label = QLabel()
                        image_label.setPixmap(pixmap)
                        image_label.setAlignment(Qt.AlignCenter)
                        frame_layout.addWidget(image_label)
                        
                        # Add the filename (truncated if too long)
                        name_label = QLabel(file_name if len(file_name) < 20 else file_name[:17] + "...")
                        name_label.setAlignment(Qt.AlignCenter)
                        frame_layout.addWidget(name_label)
                        
                        frame.setLayout(frame_layout)
                        
                        # Add to grid
                        row = i // columns
                        col = i % columns
                        image_grid.addWidget(frame, row, col)
                
                # Add the grid to the main layout
                grid_widget = QWidget()
                grid_widget.setLayout(image_grid)
                self.grid_layout.addWidget(grid_widget)
                
                # If no images were displayed
                if image_grid.count() == 0:
                    label = QLabel("No local image files found. Files may have been moved or deleted.")
                    label.setAlignment(Qt.AlignCenter)
                    self.grid_layout.addWidget(label)
            
        except Exception as e:
            error_label = QLabel(f"Error loading previews: {str(e)}")
            error_label.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(error_label)
            
            # Add detailed error for debugging
            error_details = QTextEdit()
            error_details.setPlainText(traceback.format_exc())
            error_details.setReadOnly(True)
            error_details.setMaximumHeight(100)
            self.grid_layout.addWidget(error_details)
