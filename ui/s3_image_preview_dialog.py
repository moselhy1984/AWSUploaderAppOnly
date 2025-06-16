#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S3 Image Preview Dialog
Shows thumbnails of images uploaded to S3 for a specific order
"""

import os
import sys
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QScrollArea, QWidget, QGridLayout,
                            QMessageBox, QProgressBar, QFrame)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt5.QtGui import QPixmap, QFont
import threading


class S3ImagePreviewDialog(QDialog):
    """Dialog for previewing images from S3 bucket"""
    
    def __init__(self, order_number, aws_session, parent=None):
        super().__init__(parent)
        self.order_number = order_number
        self.aws_session = aws_session
        self.images = []
        self.thumbnail_widgets = []
        self.loader_thread = None
        self.thumbnail_threads = []
        
        self.setWindowTitle(f"Image Preview - Order {order_number}")
        self.setModal(True)
        self.resize(900, 700)
        
        self.init_ui()
        self.load_images_from_s3()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        
        # Header section
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 10px;")
        header_layout = QVBoxLayout(header_frame)
        
        # Title
        title_label = QLabel(f"📸 Images for Order {self.order_number}")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel("Preview of uploaded images from S3 bucket")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #666; margin-bottom: 5px;")
        header_layout.addWidget(subtitle_label)
        
        layout.addWidget(header_frame)
        
        # Loading indicator
        self.loading_frame = QFrame()
        loading_layout = QVBoxLayout(self.loading_frame)
        
        self.loading_label = QLabel("🔄 Loading images from S3...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14pt; color: #007acc; margin: 20px;")
        loading_layout.addWidget(self.loading_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setVisible(True)
        loading_layout.addWidget(self.progress_bar)
        
        layout.addWidget(self.loading_frame)
        
        # Scroll area for images
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVisible(False)
        self.scroll_area.setStyleSheet("border: 1px solid #ccc;")
        
        # Grid widget for thumbnails
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        
        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)
        
        # Status section
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 3px;")
        status_layout = QVBoxLayout(status_frame)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("padding: 10px; color: #495057;")
        status_layout.addWidget(self.status_label)
        
        layout.addWidget(status_frame)
        
        # Button section
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumSize(100, 35)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_images_from_s3(self):
        """Load list of images from S3 bucket"""
        try:
            if not self.aws_session:
                self.show_error("AWS session not available")
                return
                
            # Stop any existing loader thread
            if self.loader_thread and self.loader_thread.isRunning():
                self.loader_thread.quit()
                self.loader_thread.wait()
                
            # Create separate thread for loading
            self.loader_thread = S3ImageLoaderThread(
                self.order_number, 
                self.aws_session
            )
            self.loader_thread.images_loaded.connect(self.display_images)
            self.loader_thread.error_occurred.connect(self.show_error)
            self.loader_thread.progress_updated.connect(self.update_loading_progress)
            self.loader_thread.finished.connect(lambda: setattr(self, 'loader_thread', None))
            self.loader_thread.start()
            
        except Exception as e:
            self.show_error(f"Error loading images: {str(e)}")
    
    def update_loading_progress(self, message):
        """Update loading progress message"""
        self.loading_label.setText(message)
    
    def display_images(self, images):
        """Display images in grid layout"""
        try:
            self.loading_frame.setVisible(False)
            self.scroll_area.setVisible(True)
            
            if not images:
                self.status_label.setText("❌ No images found for this order")
                self.status_label.setStyleSheet("color: #dc3545; padding: 20px; font-size: 14pt;")
                return
                
            # Display first 12 images maximum for performance
            display_images = images[:12]
            total_count = len(images)
            
            if total_count > 12:
                self.status_label.setText(f"📊 Showing {len(display_images)} of {total_count} images (limited for performance)")
            else:
                self.status_label.setText(f"📊 Found {total_count} image{'' if total_count == 1 else 's'}")
            
            self.status_label.setStyleSheet("color: #28a745; padding: 10px; font-weight: bold;")
            
            # Create thumbnail widgets
            cols = 4  # 4 columns for better layout
            for i, image_key in enumerate(display_images):
                row = i // cols
                col = i % cols
                
                # Create thumbnail widget
                thumbnail_widget = self.create_thumbnail_widget(image_key, i + 1)
                self.grid_layout.addWidget(thumbnail_widget, row, col)
                self.thumbnail_widgets.append(thumbnail_widget)
            
            # Add spacing at the end
            self.grid_layout.setRowStretch(row + 1, 1)
            
        except Exception as e:
            self.show_error(f"Error displaying images: {str(e)}")
    
    def create_thumbnail_widget(self, image_key, index):
        """Create widget for thumbnail display"""
        widget = QFrame()
        widget.setFixedSize(180, 200)
        widget.setStyleSheet("""
            QFrame {
                border: 2px solid #dee2e6;
                border-radius: 8px;
                background-color: white;
            }
            QFrame:hover {
                border-color: #007bff;
                background-color: #f8f9fa;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        
        # Index label
        index_label = QLabel(f"#{index}")
        index_label.setAlignment(Qt.AlignCenter)
        index_label.setStyleSheet("color: #6c757d; font-size: 10pt; font-weight: bold;")
        layout.addWidget(index_label)
        
        # Image display area
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setMinimumSize(150, 120)
        image_label.setMaximumSize(150, 120)
        image_label.setStyleSheet("border: 1px solid #e9ecef; background-color: #f8f9fa;")
        
        # Loading placeholder
        image_label.setText("🖼️\nLoading...")
        image_label.setStyleSheet("border: 1px solid #e9ecef; background-color: #f8f9fa; color: #6c757d;")
        
        layout.addWidget(image_label)
        
        # Image name
        file_name = image_key.split('/')[-1]
        # Truncate long filenames
        if len(file_name) > 20:
            display_name = file_name[:17] + "..."
        else:
            display_name = file_name
            
        name_label = QLabel(display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #495057; font-size: 9pt; border: none;")
        name_label.setToolTip(file_name)  # Show full name on hover
        layout.addWidget(name_label)
        
        # Load thumbnail asynchronously
        self.load_thumbnail_async(image_label, image_key)
        
        # Add click handler for full size view
        def show_full_image():
            self.show_full_image_dialog(image_key, file_name)
            
        widget.mousePressEvent = lambda event: show_full_image()
        widget.setCursor(Qt.PointingHandCursor)
        
        return widget
    
    def load_thumbnail_async(self, label, image_key):
        """Load thumbnail image asynchronously"""
        try:
            # Create thread for loading individual thumbnail
            loader = ThumbnailLoaderThread(image_key, self.aws_session)
            loader.thumbnail_loaded.connect(
                lambda pixmap: self.set_thumbnail(label, pixmap)
            )
            loader.error_occurred.connect(
                lambda: self.set_thumbnail_error(label)
            )
            # Clean up thread when finished
            loader.finished.connect(lambda: self.cleanup_finished_thread(loader))
            
            # Add to tracking list
            self.thumbnail_threads.append(loader)
            loader.start()
        except Exception as e:
            self.set_thumbnail_error(label)
    
    def cleanup_finished_thread(self, thread):
        """Remove finished thread from tracking list"""
        try:
            if thread in self.thumbnail_threads:
                self.thumbnail_threads.remove(thread)
        except Exception:
            pass
    
    def set_thumbnail(self, label, pixmap):
        """Set thumbnail image in label"""
        if pixmap and not pixmap.isNull():
            # Scale image to fit label
            scaled_pixmap = pixmap.scaled(
                140, 110, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            label.setPixmap(scaled_pixmap)
            label.setText("")  # Clear loading text
        else:
            self.set_thumbnail_error(label)
    
    def set_thumbnail_error(self, label):
        """Set error state for thumbnail"""
        label.setText("❌\nFailed to load")
        label.setStyleSheet("border: 1px solid #dc3545; background-color: #f8d7da; color: #721c24;")
    
    def show_full_image_dialog(self, image_key, file_name):
        """Show full size image in a new dialog"""
        try:
            from ui.full_image_dialog import FullImageDialog
            full_dialog = FullImageDialog(image_key, file_name, self.aws_session, self)
            full_dialog.exec_()
        except ImportError:
            QMessageBox.information(self, "Feature Not Available", 
                                   "Full image view feature is not yet implemented.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open full image: {str(e)}")
    
    def show_error(self, message):
        """Show error message with more details"""
        self.loading_frame.setVisible(False)
        self.scroll_area.setVisible(True)
        
        # More detailed error message
        if "No images found" in message or "not found" in message:
            error_html = f"""
            <div style='text-align: center; padding: 40px; color: #dc3545;'>
                <h3>❌ No Images Found</h3>
                <p>Could not find images for Order {self.order_number}</p>
                <p style='font-size: 12px; color: #666;'>
                    Checked these S3 locations:<br/>
                    • orders/{self.order_number}/<br/>
                    • Orders/{self.order_number}/<br/>
                    • {self.order_number}/<br/>
                    • uploads/{self.order_number}/
                </p>
                <p style='font-size: 10px; color: #888; margin-top: 20px;'>
                    Make sure images are uploaded to the correct S3 folder
                </p>
            </div>
            """
        else:
            error_html = f"""
            <div style='text-align: center; padding: 40px; color: #dc3545;'>
                <h3>❌ Connection Error</h3>
                <p>{message}</p>
                <p style='font-size: 12px; color: #666; margin-top: 20px;'>
                    Please check:<br/>
                    • Internet connection<br/>
                    • AWS credentials<br/>
                    • S3 bucket permissions
                </p>
            </div>
            """
        
        error_label = QLabel()
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setText(error_html)
        error_label.setWordWrap(True)
        error_label.setStyleSheet("QLabel { background-color: #f8f9fa; border-radius: 5px; }")
        
        # Clear grid and add error message
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
            
        self.grid_layout.addWidget(error_label, 0, 0, 1, 4)  # Span all columns
        
        self.status_label.setText("")
    
    def cleanup_threads(self):
        """Clean up all running threads"""
        try:
            # Stop and wait for loader thread
            if self.loader_thread and self.loader_thread.isRunning():
                self.loader_thread.stop()
                self.loader_thread.quit()
                if not self.loader_thread.wait(3000):  # Wait up to 3 seconds
                    self.loader_thread.terminate()
                    self.loader_thread.wait()
            
            # Stop and wait for thumbnail threads
            for thread in self.thumbnail_threads:
                if thread and thread.isRunning():
                    thread.stop()
                    thread.quit()
                    if not thread.wait(1000):  # Wait up to 1 second
                        thread.terminate()
                        thread.wait()
            
            self.thumbnail_threads.clear()
            
        except Exception as e:
            print(f"Error cleaning up threads: {e}")
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        self.cleanup_threads()
        super().closeEvent(event)
    
    def reject(self):
        """Handle dialog rejection (ESC key, etc.)"""
        self.cleanup_threads()
        super().reject()


class S3ImageLoaderThread(QThread):
    """Thread for loading image list from S3"""
    
    images_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)
    
    def __init__(self, order_number, aws_session):
        super().__init__()
        self.order_number = order_number
        self.aws_session = aws_session
        self._stop_flag = False
    
    def stop(self):
        """Stop the thread safely"""
        self._stop_flag = True
    
    def run(self):
        """Load images from S3 bucket"""
        try:
            if self._stop_flag:
                return
                
            self.progress_updated.emit("🔍 Connecting to S3...")
            
            # Get bucket name from session or use default
            bucket_name = "balistudiostorage"  # Default bucket
            
            # Try multiple possible S3 path patterns
            possible_prefixes = [
                f"orders/{self.order_number}/",
                f"Orders/{self.order_number}/", 
                f"order_{self.order_number}/",
                f"Order_{self.order_number}/",
                f"{self.order_number}/",
                f"uploads/{self.order_number}/",
                f"Uploads/{self.order_number}/",
            ]
            
            self.progress_updated.emit("📡 Searching for images...")
            
            # Configure S3 client with timeouts
            import botocore.config
            config = botocore.config.Config(
                read_timeout=30,  # 30 seconds timeout for listing
                connect_timeout=10  # 10 seconds connect timeout
            )
            s3_client = self.aws_session.client('s3', config=config)
            all_images = []
            
            # Try each possible prefix
            for prefix in possible_prefixes:
                try:
                    self.progress_updated.emit(f"🔎 Checking: {prefix}")
                    
                    # List objects with this prefix
                    response = s3_client.list_objects_v2(
                        Bucket=bucket_name,
                        Prefix=prefix,
                        MaxKeys=200  # Increased limit
                    )
                    
                    if 'Contents' in response:
                        self.progress_updated.emit(f"📁 Found folder: {prefix}")
                        
                        # Filter for image files
                        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                        
                        for obj in response['Contents']:
                            key = obj['Key']
                            if any(key.lower().endswith(ext) for ext in image_extensions):
                                # Skip thumbnails or system files
                                filename = key.split('/')[-1].lower()
                                if not filename.startswith('.') and 'thumb' not in filename and 'thumbnail' not in filename:
                                    all_images.append(key)
                        
                        # If we found images, break to avoid duplicates
                        if all_images:
                            break
                            
                except Exception as prefix_error:
                    # Continue to next prefix if this one fails
                    continue
            
            # Remove duplicates and sort
            all_images = list(set(all_images))
            all_images.sort()
            
            if all_images:
                self.progress_updated.emit(f"✅ Found {len(all_images)} images")
            else:
                # Try a broad search if specific prefixes failed
                self.progress_updated.emit("🔍 Doing broad search...")
                
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    MaxKeys=1000
                )
                
                if 'Contents' in response:
                    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
                    
                    for obj in response['Contents']:
                        key = obj['Key']
                        # Check if the order number appears anywhere in the key
                        if (self.order_number in key and 
                            any(key.lower().endswith(ext) for ext in image_extensions)):
                            filename = key.split('/')[-1].lower()
                            if not filename.startswith('.') and 'thumb' not in filename:
                                all_images.append(key)
                
                all_images = list(set(all_images))
                all_images.sort()
                
                if all_images:
                    self.progress_updated.emit(f"✅ Found {len(all_images)} images (broad search)")
                else:
                    self.progress_updated.emit("❌ No images found")
            
            self.images_loaded.emit(all_images)
            
        except Exception as e:
            error_msg = str(e)
            if "NoSuchBucket" in error_msg:
                error_msg = f"S3 bucket 'balistudiostorage' not found"
            elif "NoCredentialsError" in error_msg:
                error_msg = "AWS credentials not configured"
            elif "AccessDenied" in error_msg:
                error_msg = "Access denied to S3 bucket"
            elif "EndpointConnectionError" in error_msg:
                error_msg = "Cannot connect to S3 - check internet connection"
            else:
                error_msg = f"S3 error: {error_msg}"
                
            self.error_occurred.emit(error_msg)


class ThumbnailLoaderThread(QThread):
    """Thread for loading individual thumbnail images"""
    
    thumbnail_loaded = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal()
    
    def __init__(self, image_key, aws_session):
        super().__init__()
        self.image_key = image_key
        self.aws_session = aws_session
        self._stop_flag = False
    
    def stop(self):
        """Stop the thread safely"""
        self._stop_flag = True
    
    def run(self):
        """Load and process thumbnail image"""
        try:
            if self._stop_flag:
                return
                
            bucket_name = "balistudiostorage"
            s3_client = self.aws_session.client('s3')
            
            # Download image data with timeout
            import botocore.config
            config = botocore.config.Config(
                read_timeout=10,  # 10 seconds timeout
                connect_timeout=5  # 5 seconds connect timeout
            )
            s3_client = self.aws_session.client('s3', config=config)
            
            response = s3_client.get_object(
                Bucket=bucket_name,
                Key=self.image_key
            )
            
            # Read only first 2MB for thumbnails (faster loading)
            image_data = response['Body'].read(2 * 1024 * 1024)  # 2MB limit
            
            # Convert to QPixmap
            pixmap = QPixmap()
            success = pixmap.loadFromData(image_data)
            
            if success and not pixmap.isNull():
                # Scale down large images immediately to save memory
                if pixmap.width() > 300 or pixmap.height() > 300:
                    pixmap = pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self.thumbnail_loaded.emit(pixmap)
            else:
                self.error_occurred.emit()
                
        except Exception as e:
            print(f"Error loading thumbnail {self.image_key}: {str(e)}")
            self.error_occurred.emit()


if __name__ == "__main__":
    # Test the dialog
    from PyQt5.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Mock AWS session for testing
    class MockAWSSession:
        pass
    
    dialog = S3ImagePreviewDialog("123456", MockAWSSession(), None)
    dialog.show()
    
    sys.exit(app.exec_()) 