#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from datetime import datetime
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from PyQt5.QtCore import QThread, pyqtSignal

class BackgroundUploader(QThread):
    """
    Background thread for uploading files to S3 storage
    
    Signals:
        progress: Emitted during upload to update progress bar (current, total)
        log: Emitted to log messages to the main UI
        finished: Emitted when upload is complete
    """
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, folder_path, order_number, order_date, aws_session, 
                 photographers, local_path=None, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.order_number = order_number
        self.order_date = order_date
        self.aws_session = aws_session
        self.photographers = photographers
        self.local_path = local_path
        self._is_running = True
        self.uploaded_file_count = 0
        self.skipped_file_count = 0

    def stop(self):
        """Stop the upload process"""
        self._is_running = False

    def run(self):
        """Main method that runs in the background thread"""
        try:
            self.log.emit("Starting upload preparation...")
            
            # Initialize S3 client
            s3 = self.aws_session.client('s3',
                config=boto3.session.Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'}
                )
            )
            
            # Prepare path structure
            year = self.order_date.year
            month = f"{self.order_date.month:02d}-{year}"
            day = f"{self.order_date.day:02d}-{month}"
            base_prefix = f"{year}/{month}/{day}/Order_{self.order_number}"
            
            # Verify bucket exists
            try:
                s3.head_bucket(Bucket=self.aws_session.bucket_name)
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == '403':
                    self.log.emit("Error: Access denied. Please check AWS permissions.")
                elif error_code == '404':
                    self.log.emit("Error: Bucket not found. Please check bucket name.")
                else:
                    self.log.emit(f"AWS Error: {str(e)}")
                return
            
            # Process the local path folders to maintain the same structure
            self.log.emit("Scanning local folders to maintain structure...")
            
            # Track all files to be uploaded
            all_files = []
            uploaded_files_metadata = []
            
            # Process main categories (CR2, JPG, Reels/Videos)
            categories = ["CR2", "JPG", "Reels/Videos", "OTHER"]
            
            for category in categories:
                category_path = Path(self.local_path) / category
                if not category_path.exists():
                    self.log.emit(f"Category folder {category} does not exist, skipping.")
                    continue
                
                self.log.emit(f"Processing {category} folder...")
                
                # If it's a deep path like "Reels/Videos", handle properly
                if "/" in category:
                    parts = category.split("/")
                    s3_category_prefix = "/".join(parts)
                else:
                    s3_category_prefix = category
                
                # Walk through all files in this category folder
                for file_path in category_path.rglob('*'):
                    if not file_path.is_file() or not self._is_running:
                        continue
                    
                    # Calculate relative path from the category folder
                    rel_path = file_path.relative_to(category_path)
                    
                    # S3 key preserves the folder structure
                    s3_key = f"{base_prefix}/{s3_category_prefix}/{rel_path}"
                    
                    file_size = file_path.stat().st_size
                    
                    all_files.append({
                        'local_path': str(file_path),
                        's3_key': s3_key,
                        'size': file_size,
                        'category': category
                    })
            
            # Calculate total files and start uploading
            total_files = len(all_files)
            self.log.emit(f"Found {total_files} files to process")
            
            # Get list of already uploaded files from database
            uploaded_files = self.get_uploaded_files(self.order_number)
            uploaded_file_keys = set(uploaded_files)
            
            processed_files = 0
            uploaded_files = 0
            skipped_files = 0
            
            # Process all files with duplicate detection
            for file_info in all_files:
                if not self._is_running:
                    self.log.emit("Upload cancelled")
                    break
                
                local_path = file_info['local_path']
                s3_key = file_info['s3_key']
                file_size = file_info['size']
                category = file_info['category']
                
                # Check if file was already uploaded
                if s3_key in uploaded_file_keys:
                    self.log.emit(f"Skipping already uploaded file: {os.path.basename(local_path)}")
                    skipped_files += 1
                    processed_files += 1
                    self.progress.emit(processed_files, total_files)
                    continue
                
                # Check if file exists in S3 before uploading
                try:
                    s3.head_object(Bucket=self.aws_session.bucket_name, Key=s3_key)
                    self.log.emit(f"File already exists in S3, skipping: {os.path.basename(local_path)}")
                    skipped_files += 1
                    
                    # Add to upload history even though we skipped
                    uploaded_files_metadata.append({
                        'order_number': self.order_number,
                        's3_key': s3_key,
                        'file_name': os.path.basename(local_path),
                        'file_size': file_size,
                        'file_type': category,
                        'status': 'skipped'
                    })
                    
                except ClientError as e:
                    # File doesn't exist, proceed with upload
                    try:
                        if file_size > 100 * 1024 * 1024:  # 100MB
                            # Use multipart upload for large files
                            multipart_config = {
                                'MultipartUpload': True,
                                'MultipartThreshold': 100 * 1024 * 1024,
                                'MultipartChunksize': 100 * 1024 * 1024
                            }
                            transfer = boto3.s3.transfer.TransferConfig(**multipart_config)
                            s3.upload_file(
                                local_path,
                                self.aws_session.bucket_name,
                                s3_key,
                                Config=transfer
                            )
                        else:
                            # Standard upload for smaller files
                            s3.upload_file(
                                local_path,
                                self.aws_session.bucket_name,
                                s3_key
                            )
                        
                        uploaded_files += 1
                        self.log.emit(f"Uploaded: {os.path.basename(local_path)}")
                        
                        # Add to our upload history
                        uploaded_files_metadata.append({
                            'order_number': self.order_number,
                            's3_key': s3_key,
                            'file_name': os.path.basename(local_path),
                            'file_size': file_size,
                            'file_type': category,
                            'status': 'uploaded'
                        })
                        
                    except ClientError as upload_err:
                        error_msg = str(upload_err)
                        if 'SignatureDoesNotMatch' in error_msg:
                            self.log.emit("Authentication error. Please check AWS credentials.")
                            self.log.emit("Stopping upload process due to authentication error.")
                            return
                        else:
                            self.log.emit(f"Error uploading {os.path.basename(local_path)}: {error_msg}")
                    except Exception as upload_err:
                        self.log.emit(f"Error uploading {os.path.basename(local_path)}: {str(upload_err)}")
                
                processed_files += 1
                self.progress.emit(processed_files, total_files)
            
            self.uploaded_file_count = uploaded_files
            self.skipped_file_count = skipped_files
            
            if self._is_running:
                # Record the upload in the database
                try:
                    # Get database connection from parent
                    parent = self.parent()
                    if parent and hasattr(parent, 'db_manager'):
                        db_manager = parent.db_manager
                        
                        # Convert photographer IDs to integers
                        main_photographer_id = int(self.photographers['main']) if self.photographers['main'] else None
                        assistant_photographer_id = int(self.photographers['assistant']) if self.photographers['assistant'] else None
                        video_photographer_id = int(self.photographers['video']) if self.photographers['video'] else None
                        
                        # First check if there's already an upload record for this order
                        existing_record = self.check_existing_upload(db_manager, self.order_number)
                        
                        if existing_record:
                            # Update the existing record
                            self.log.emit(f"Updating existing upload record for order {self.order_number}")
                            success = self.update_upload_record(
                                db_manager,
                                existing_record,
                                uploaded_files,
                                main_photographer_id,
                                assistant_photographer_id,
                                video_photographer_id
                            )
                        else:
                            # Create a new record
                            self.log.emit(f"Creating new upload record for order {self.order_number}")
                            success = db_manager.record_upload(
                                self.order_number, 
                                uploaded_files + skipped_files,  # Total files count
                                main_photographer_id,
                                assistant_photographer_id,
                                video_photographer_id
                            )
                        
                        # Record detailed file upload history
                        if success and uploaded_files_metadata:
                            success = self.record_upload_details(db_manager, uploaded_files_metadata)
                            
                        if success:
                            self.log.emit(f"Upload recorded in database. {uploaded_files} files uploaded, {skipped_files} files skipped.")
                        else:
                            self.log.emit("Failed to record upload in database")
                    
                except Exception as e:
                    self.log.emit(f"Error recording upload in database: {str(e)}")
                    import traceback
                    self.log.emit(traceback.format_exc())
                
                self.log.emit(f"Upload complete. {uploaded_files} files uploaded, {skipped_files} files skipped.")
            
            self.finished.emit()
            
        except Exception as e:
            self.log.emit(f"Error: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
    
    def get_uploaded_files(self, order_number):
        """
        Get list of already uploaded files for this order
        
        Args:
            order_number (str): Order number to check
            
        Returns:
            list: List of S3 keys for files already uploaded
        """
        parent = self.parent()
        if not parent or not hasattr(parent, 'db_manager'):
            return []
        
        db_manager = parent.db_manager
        if not db_manager.connection or not db_manager.connection.is_connected():
            db_manager.connect()
        
        try:
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
            
            if result and result['table_exists'] == 0:
                # Table doesn't exist yet
                self.log.emit("Creating upload_files table for tracking individual files...")
                
                create_table_query = """
                CREATE TABLE upload_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    order_number VARCHAR(50) NOT NULL,
                    s3_key VARCHAR(1024) NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_size BIGINT NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    upload_status VARCHAR(20) NOT NULL,
                    upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                db_manager.connection.commit()
                self.log.emit("Created upload_files table")
                return []
            
            # Get all files already uploaded for this order
            query = """
            SELECT s3_key
            FROM upload_files
            WHERE order_number = %s
            """
            cursor.execute(query, (order_number,))
            files = cursor.fetchall()
            cursor.close()
            
            return [file['s3_key'] for file in files] if files else []
            
        except Exception as e:
            self.log.emit(f"Error checking uploaded files: {e}")
            return []
    
    def check_existing_upload(self, db_manager, order_number):
        """
        Check if there's already an upload record for this order
        
        Args:
            db_manager: Database manager instance
            order_number (str): Order number to check
            
        Returns:
            dict or None: Existing upload record if found, None otherwise
        """
        try:
            if not db_manager.connection or not db_manager.connection.is_connected():
                db_manager.connect()
                
            cursor = db_manager.connection.cursor(dictionary=True)
            query = """
            SELECT upload_id, file_count
            FROM uploads
            WHERE order_number = %s
            """
            cursor.execute(query, (order_number,))
            result = cursor.fetchone()
            cursor.close()
            
            return result
            
        except Exception as e:
            self.log.emit(f"Error checking existing upload: {e}")
            return None
    
    def update_upload_record(self, db_manager, existing_record, new_files, main_id, assistant_id, video_id):
        """
        Update an existing upload record
        
        Args:
            db_manager: Database manager instance
            existing_record (dict): Existing upload record
            new_files (int): Number of new files uploaded
            main_id (int): ID of main photographer
            assistant_id (int): ID of assistant photographer
            video_id (int): ID of video photographer
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not db_manager.connection or not db_manager.connection.is_connected():
                db_manager.connect()
                
            cursor = db_manager.connection.cursor()
            
            # Check if the uploads table has the photographer columns
            check_query = """
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'uploads' 
            AND COLUMN_NAME = 'main_photographer_id'
            """
            cursor.execute(check_query, (db_manager.rds_config['database'],))
            result = cursor.fetchone()
            column_exists = result[0] if result else 0
            
            # Update the record with new total and update timestamp
            total_files = existing_record['file_count'] + new_files
            
            if column_exists == 0:
                update_query = """
                UPDATE uploads
                SET file_count = %s, upload_timestamp = NOW()
                WHERE upload_id = %s
                """
                cursor.execute(update_query, (total_files, existing_record['upload_id']))
            else:
                update_query = """
                UPDATE uploads
                SET file_count = %s, 
                    upload_timestamp = NOW(),
                    main_photographer_id = %s,
                    assistant_photographer_id = %s,
                    video_photographer_id = %s
                WHERE upload_id = %s
                """
                cursor.execute(update_query, (
                    total_files,
                    main_id,
                    assistant_id,
                    video_id,
                    existing_record['upload_id']
                ))
            
            db_manager.connection.commit()
            cursor.close()
            return True
            
        except Exception as e:
            self.log.emit(f"Error updating upload record: {e}")
            return False
        
    def record_upload_details(self, db_manager, file_metadata):
        """
        Record details of all uploaded files
        
        Args:
            db_manager: Database manager instance
            file_metadata (list): List of dictionaries with file metadata
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not db_manager.connection or not db_manager.connection.is_connected():
                db_manager.connect()
                
            cursor = db_manager.connection.cursor()
            
            insert_query = """
            INSERT INTO upload_files (
                order_number, s3_key, file_name, file_size, file_type, upload_status, upload_timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """
            
            # Use executemany for batch insertion
            values = [
                (
                    file['order_number'],
                    file['s3_key'],
                    file['file_name'],
                    file['file_size'],
                    file['file_type'],
                    file['status']
                )
                for file in file_metadata
            ]
            
            cursor.executemany(insert_query, values)
            db_manager.connection.commit()
            cursor.close()
            
            self.log.emit(f"Recorded {len(file_metadata)} files in upload history")
            return True
            
        except Exception as e:
            self.log.emit(f"Error recording file upload details: {e}")
            return False
