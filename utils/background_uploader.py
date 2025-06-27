#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import random
import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from functools import wraps
import concurrent.futures
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import shutil

import platform
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath


class UploaderSettings:
    """Configuration settings for the uploader"""
    def __init__(self):
        self.max_retries = 3
        self.retry_delay = 2
        self.chunk_size = 8192
        self.progress_update_interval = 1.0
        self.multipart_threshold = 100 * 1024 * 1024  # 100MB
        self.max_parallel_files = 3
        self.state_save_interval = 10  # Save state every 10 files
        self.connection_timeout = 60
        self.read_timeout = 300
        
    @classmethod
    def from_config_file(cls, config_path):
        """Load settings from config file"""
        settings = cls()
        if Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    for key, value in config.items():
                        if hasattr(settings, key):
                            setattr(settings, key, value)
            except Exception as e:
                logging.warning(f"Could not load config file {config_path}: {e}")
        return settings


class StructuredLogger:
    """Enhanced logging with structured output"""
    def __init__(self, order_number):
        self.order_number = order_number
        self.setup_logger()
        
    def setup_logger(self):
        log_dir = Path.home() / '.aws_uploader' / 'logs'
        log_dir.mkdir(exist_ok=True, parents=True)
        
        log_file = log_dir / f"upload_{self.order_number}_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(f"uploader_{self.order_number}")
        
    def log_upload_start(self, total_files, total_size):
        self.logger.info(f"Upload started: {total_files} files, {self._format_bytes(total_size)}")
        
    def log_file_upload(self, file_name, status, duration=None, size=None):
        message = f"File {file_name}: {status}"
        if duration:
            message += f" (took {duration:.2f}s"
            if size:
                speed = size / duration if duration > 0 else 0
                message += f", {self._format_bytes(speed)}/s"
            message += ")"
        self.logger.info(message)
        
    def log_upload_complete(self, uploaded, skipped, total_time):
        self.logger.info(f"Upload completed: {uploaded} uploaded, {skipped} skipped in {total_time:.2f}s")
        
    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.1f} GB"


class EnhancedProgressTracker:
    """Enhanced progress tracking with speed and ETA calculations"""
    def __init__(self):
        self.start_time = None
        self.bytes_per_second = 0
        self.eta_seconds = 0
        self.last_bytes = 0
        self.last_time = None
        self.speed_history = []
        self.speed_history_size = 10
        
    def update_progress(self, uploaded_bytes, total_bytes):
        current_time = time.time()
        
        if self.start_time is None:
            self.start_time = current_time
            self.last_time = current_time
            self.last_bytes = uploaded_bytes
            return
        
        # Calculate speed
        if self.last_time is not None:
            time_diff = current_time - self.last_time
            if time_diff >= 1.0:  # Update every second
                bytes_diff = uploaded_bytes - self.last_bytes
                current_speed = bytes_diff / time_diff
                # Keep speed history for smoothing
                self.speed_history.append(current_speed)
                if len(self.speed_history) > self.speed_history_size:
                    self.speed_history.pop(0)
                # Calculate average speed
                self.bytes_per_second = sum(self.speed_history) / len(self.speed_history)
                # Calculate ETA
                remaining_bytes = total_bytes - uploaded_bytes
                if self.bytes_per_second > 0:
                    self.eta_seconds = remaining_bytes / self.bytes_per_second
                self.last_bytes = uploaded_bytes
                self.last_time = current_time
            
    def get_eta_formatted(self):
        if self.eta_seconds <= 0:
            return "calculating..."
        
        hours = int(self.eta_seconds // 3600)
        minutes = int((self.eta_seconds % 3600) // 60)
        seconds = int(self.eta_seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def get_speed_formatted(self):
        return self._format_bytes(self.bytes_per_second) + "/s"
    
    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        if bytes_value < 1024:
            return f"{bytes_value:.0f} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.1f} GB"


class DatabaseConnectionManager:
    """Enhanced database connection management with connection pooling"""
    def __init__(self):
        self.connections = {}
        self.lock = threading.Lock()
    
    @contextmanager
    def get_connection(self, db_manager):
        thread_id = threading.current_thread().ident
        
        with self.lock:
            if thread_id not in self.connections:
                self.connections[thread_id] = self._create_connection(db_manager)
                
        connection = self.connections[thread_id]
        try:
            if not connection.is_connected():
                connection.reconnect()
            yield connection
        except Exception:
            # Try to recreate connection on error
            with self.lock:
                self.connections[thread_id] = self._create_connection(db_manager)
            yield self.connections[thread_id]
    
    def _create_connection(self, db_manager):
        """Create a new database connection"""
        import mysql.connector
        return mysql.connector.connect(**db_manager.rds_config)
    
    def cleanup(self):
        """Clean up all connections"""
        with self.lock:
            for connection in self.connections.values():
                try:
                    connection.close()
                except:
                    pass
            self.connections.clear()


def retry_on_failure(max_retries=3, delay=1, backoff=True):
    """Decorator for retrying operations with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    
                    wait_time = delay * (2 ** attempt) if backoff else delay
                    self.log.emit(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator


@contextmanager
def safe_file_operation(file_path, mode='rb'):
    """Context manager for safe file operations"""
    file_handle = None
    try:
        file_handle = open(file_path, mode)
        yield file_handle
    except Exception as e:
        logging.error(f"Error with file {file_path}: {str(e)}")
        raise
    finally:
        if file_handle:
            file_handle.close()


class ProgressCallback:
    """Enhanced callback class to track upload progress for individual files"""
    def __init__(self, uploader, file_name, file_size, settings):
        self.uploader = uploader
        self.file_name = file_name
        self.file_size = file_size
        self.bytes_transferred = 0
        self.last_update_time = time.time()
        self.update_threshold = settings.progress_update_interval
        self.start_time = time.time()
        
    def __call__(self, bytes_amount):
        self.bytes_transferred += bytes_amount
        current_time = time.time()
        
        # Throttle updates to reduce UI overhead
        if current_time - self.last_update_time >= self.update_threshold:
            self._emit_progress()
            self.last_update_time = current_time
            
    def _emit_progress(self):
        # Update uploader's current file tracking
        self.uploader.current_file_name = self.file_name
        self.uploader.current_file_uploaded_bytes = self.bytes_transferred
        self.uploader.current_file_total_bytes = self.file_size
        
        # Calculate speed for current file
        elapsed_time = time.time() - self.start_time
        if elapsed_time > 0:
            speed = self.bytes_transferred / elapsed_time
            # Update uploader's speed tracking
            self.uploader.progress_tracker.update_progress(
                self.uploader.uploaded_bytes + self.bytes_transferred,
                self.uploader.total_bytes
            )
        
        # Emit progress for current file
        if self.file_size > 0:
            file_progress = min(100, (self.bytes_transferred / self.file_size) * 100)
            self.uploader.current_file_progress.emit(
                self.file_name, 
                int(file_progress), 
                self.bytes_transferred, 
                self.file_size
            )


class MockUploadSession:
    """Enhanced mock session for testing"""
    def __init__(self, simulate_errors=False, error_rate=0.1, slow_upload=False):
        self.simulate_errors = simulate_errors
        self.error_rate = error_rate
        self.slow_upload = slow_upload
        self.bucket_name = "mock-bucket"
        
    def client(self, service_name, **kwargs):
        return MockS3Client(self.simulate_errors, self.error_rate, self.slow_upload)


class MockS3Client:
    """Enhanced mock S3 client with realistic behavior simulation"""
    def __init__(self, simulate_errors=False, error_rate=0.1, slow_upload=False):
        self.simulate_errors = simulate_errors
        self.error_rate = error_rate
        self.slow_upload = slow_upload
        
    def head_bucket(self, Bucket):
        if self.simulate_errors and random.random() < self.error_rate:
            raise ClientError({'Error': {'Code': '403'}}, 'HeadBucket')
        return True
        
    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None, Callback=None):
        if self.simulate_errors and random.random() < self.error_rate:
            error_codes = ['NetworkError', 'ServiceUnavailable', 'AccessDenied']
            error_code = random.choice(error_codes)
            raise ClientError({'Error': {'Code': error_code}}, 'PutObject')
            
        # Simulate upload with callback
        if not Path(Filename).exists():
            raise FileNotFoundError(f"File not found: {Filename}")
            
        file_size = Path(Filename).stat().st_size
        chunk_size = 8192
        
        for i in range(0, file_size, chunk_size):
            chunk_upload_size = min(chunk_size, file_size - i)
            if Callback:
                Callback(chunk_upload_size)
            
            # Simulate network delay
            if self.slow_upload:
                time.sleep(0.05)  # Slower upload simulation
            else:
                time.sleep(0.001)  # Fast upload simulation


class CrossPlatformS3PathHandler:
    """
    Cross-platform S3 path handler that ensures consistent forward slash usage
    regardless of the operating system
    """
    
    @staticmethod
    def normalize_s3_path(path_str):
        """
        Normalize a path string to use forward slashes for S3 compatibility
        
        Args:
            path_str (str): Path string to normalize
            
        Returns:
            str: Normalized path with forward slashes
        """
        if not path_str:
            return ""
        
        # Convert backslashes to forward slashes
        normalized = path_str.replace('\\', '/')
        
        # Remove duplicate slashes
        while '//' in normalized:
            normalized = normalized.replace('//', '/')
        
        # Remove leading slash if present
        if normalized.startswith('/'):
            normalized = normalized[1:]
        
        # Remove trailing slash if present
        if normalized.endswith('/'):
            normalized = normalized[:-1]
        
        return normalized
    
    @staticmethod
    def create_s3_key(*parts):
        """
        Create an S3 key from multiple path parts, ensuring forward slash usage
        
        Args:
            *parts: Variable number of path parts
            
        Returns:
            str: S3 key with forward slashes
        """
        # Filter out empty parts and convert all to strings
        clean_parts = [str(part) for part in parts if part]
        
        if not clean_parts:
            return ""
        
        # Join with forward slashes and normalize
        joined = '/'.join(clean_parts)
        return CrossPlatformS3PathHandler.normalize_s3_path(joined)
    
    @staticmethod
    def get_relative_path_posix(file_path, base_path):
        """
        Get relative path in POSIX format (forward slashes) regardless of OS
        
        Args:
            file_path (Path): File path
            base_path (Path): Base path
            
        Returns:
            str: Relative path with forward slashes
        """
        try:
            # Get relative path
            relative = file_path.relative_to(base_path)
            
            # Convert to POSIX format (forward slashes)
            if platform.system() == "Windows":
                # On Windows, convert to forward slashes
                return str(relative).replace('\\', '/')
            else:
                # On Unix-like systems, already uses forward slashes
                return str(relative)
                
        except ValueError:
            # If file_path is not relative to base_path, return just the filename
            return file_path.name


def get_local_path_structure_cross_platform(uploader_instance):
    """
    Cross-platform version of get_local_path_structure that handles path separators correctly
    
    Args:
        uploader_instance: BackgroundUploader instance
        
    Returns:
        str: The relative path structure to use as S3 prefix
    """
    try:
        # Get the local folder path
        folder_path = Path(uploader_instance.folder_path)
        
        # Look for common patterns in the path structure
        path_parts = folder_path.parts
        
        # Find the year folder (4-digit number starting with 20xx)
        year_folder_index = -1
        for i, part in enumerate(path_parts):
            # Check if this part looks like a year (4 digits starting with 20)
            if part.isdigit() and len(part) == 4 and part.startswith('20'):
                year_folder_index = i
                break
        
        if year_folder_index >= 0:
            # Extract the path from the year folder onwards
            relative_structure = Path(*path_parts[year_folder_index:])
            uploader_instance.log.emit(f"📁 Using year-based structure: {relative_structure}")
            # Use CrossPlatformS3PathHandler to ensure forward slashes
            return CrossPlatformS3PathHandler.normalize_s3_path(str(relative_structure))
        else:
            # Fallback: look for the base folder pattern and then find year
            base_folder_index = -1
            for i, part in enumerate(path_parts):
                if 'booking' in part.lower() or 'folders' in part.lower() or 'orders' in part.lower():
                    base_folder_index = i
                    break
            
            if base_folder_index >= 0:
                # Look for year folder after base folder
                for i in range(base_folder_index + 1, len(path_parts)):
                    part = path_parts[i]
                    if part.isdigit() and len(part) == 4 and part.startswith('20'):
                        relative_structure = Path(*path_parts[i:])
                        uploader_instance.log.emit(f"📁 Found year folder, using: {relative_structure}")
                        return CrossPlatformS3PathHandler.normalize_s3_path(str(relative_structure))
            
            # If no year found in expected location, try pattern matching
            folder_name = folder_path.name
            parent_folder = folder_path.parent.name
            grandparent_folder = folder_path.parent.parent.name
            
            # Check if grandparent looks like a year
            if grandparent_folder.isdigit() and len(grandparent_folder) == 4 and grandparent_folder.startswith('20'):
                relative_structure = Path(grandparent_folder) / parent_folder / folder_name
                uploader_instance.log.emit(f"📁 Detected year structure: {relative_structure}")
                return CrossPlatformS3PathHandler.normalize_s3_path(str(relative_structure))
            
            # Check if parent looks like a year
            elif parent_folder.isdigit() and len(parent_folder) == 4 and parent_folder.startswith('20'):
                relative_structure = Path(parent_folder) / folder_name
                uploader_instance.log.emit(f"📁 Detected year structure: {relative_structure}")
                return CrossPlatformS3PathHandler.normalize_s3_path(str(relative_structure))
            
            else:
                # Ultimate fallback: use just the order folder
                uploader_instance.log.emit(f"📁 No year found, using order folder only: {folder_name}")
                return CrossPlatformS3PathHandler.normalize_s3_path(folder_name)
                
    except Exception as e:
        uploader_instance.log.emit(f"⚠️ Error extracting local path structure: {str(e)}")
        # Ultimate fallback
        return CrossPlatformS3PathHandler.normalize_s3_path(f"Order_{uploader_instance.order_number}")


def create_file_info_cross_platform(uploader_instance, file_path, folder_path, base_prefix):
    """
    Cross-platform version of _create_file_info that handles path separators correctly
    
    Args:
        uploader_instance: BackgroundUploader instance
        file_path (Path): File path
        folder_path (Path): Folder path
        base_prefix (str): Base prefix for S3
        
    Returns:
        dict: File info dictionary
    """
    # Get relative path using cross-platform handler
    relative_path_str = CrossPlatformS3PathHandler.get_relative_path_posix(file_path, folder_path)
    relative_path = Path(relative_path_str)
    path_parts = relative_path.parts
    
    # Determine file category
    file_extension = file_path.suffix.lower()
    file_category = 'OTHER'
    
    for category, extensions in uploader_instance.extension_mappings.items():
        if file_extension in extensions:
            file_category = category
            break
    
    # Determine S3 key based on file location
    if len(path_parts) > 1 and path_parts[0] in uploader_instance.extension_mappings:
        # File is already in a category folder
        category_from_path = path_parts[0]
        rel_path_in_category = Path(*path_parts[1:])
        
        # Use CrossPlatformS3PathHandler to create S3 key
        s3_key = CrossPlatformS3PathHandler.create_s3_key(
            base_prefix, 
            category_from_path, 
            CrossPlatformS3PathHandler.get_relative_path_posix(rel_path_in_category, Path('.'))
        )
        actual_category = category_from_path
    else:
        # File is loose or in a non-category folder
        s3_key = CrossPlatformS3PathHandler.create_s3_key(
            base_prefix, 
            file_category, 
            relative_path_str
        )
        actual_category = file_category
    
    file_size = file_path.stat().st_size
    
    return {
        'local_path': str(file_path),
        's3_key': s3_key,
        'size': file_size,
        'category': actual_category,
        'extension': file_extension,
        'original_location': 'organized' if len(path_parts) > 1 and path_parts[0] in uploader_instance.extension_mappings else 'loose'
    }


class BackgroundUploader(QThread):
    """
    Enhanced background thread for uploading files to S3 storage
    
    Signals:
        progress: Emitted during upload to update progress bar (current, total)
        log: Emitted to log messages to the main UI
        finished: Emitted when upload is complete
        current_file_progress: Emitted with current file info (file_name, file_progress, uploaded_bytes, total_bytes)
        speed_update: Emitted with speed and ETA info (speed_str, eta_str)
    """
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    finished = pyqtSignal()
    current_file_progress = pyqtSignal(str, int, int, int)  # file_name, progress_percent, uploaded_bytes, total_bytes
    speed_update = pyqtSignal(str, str)  # speed_str, eta_str

    def __init__(self, folder_path, order_number, order_date, aws_session, 
                 photographers, local_path=None, parent=None, settings=None, task_id=None, **kwargs):
        super().__init__(parent)
        self.folder_path = folder_path
        self.order_number = order_number
        self.order_date = order_date
        self.aws_session = aws_session
        self.photographers = photographers
        self.local_path = local_path
        self.settings = settings or UploaderSettings()
        self.task_id = task_id  # Support for task_id parameter
        
        # Handle any additional keyword arguments that might be passed
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                task_info = f" [Task {self.task_id}]" if self.task_id else ""
                self.log.emit(f"Warning{task_info}: Unknown parameter '{key}' passed to BackgroundUploader")
        
        # Thread control
        self._is_running = True
        self._is_paused = False
        self._pause_mutex = QMutex()
        
        # Progress tracking
        self.uploaded_file_count = 0
        self.skipped_file_count = 0
        self.total_files = 0
        self.completed_files = []
        self.current_file_index = 0
        self.all_files = []
        
        # Enhanced progress tracking
        self.total_bytes = 0
        self.uploaded_bytes = 0
        self.current_file_bytes = 0
        self.progress_tracker = EnhancedProgressTracker()
        
        # Current file tracking for enhanced progress bars
        self.current_file_name = ""
        self.current_file_uploaded_bytes = 0
        self.current_file_total_bytes = 0
        
        # Enhanced logging with task_id support
        self.structured_logger = StructuredLogger(f"{order_number}_{task_id}" if task_id else order_number)
        
        # Database connection manager
        self.db_connection_manager = DatabaseConnectionManager()
        
        # Create state directory if it doesn't exist
        self.state_dir = Path.home() / '.aws_uploader'
        self.state_dir.mkdir(exist_ok=True)
        # Include task_id in state file name if provided for unique identification
        state_filename = f"task_state_{order_number}_{task_id}.json" if task_id else f"task_state_{order_number}.json"
        self.state_file = self.state_dir / state_filename
        
        # Extension mappings
        self.extension_mappings = {
            'CR2': ['.cr2', '.cr3', '.nef', '.arw', '.raw', '.dng'],
            'JPG': ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.heic', '.webp'],
            'Reels/Videos': ['.mp4', '.mov', '.avi', '.wmv', '.flv', '.m4v', '.mkv', '.webm', '.3gp'],
            'OTHER': []
        }
    
    def stop(self):
        """Stop the upload process"""
        self._is_running = False
        task_info = f" [Task {self.task_id}]" if self.task_id else ""
        self.log.emit(f"Upload stopped{task_info}")
        
    def pause(self):
        """Pause the upload process"""
        with QMutexLocker(self._pause_mutex):
            self._is_paused = True
            task_info = f" [Task {self.task_id}]" if self.task_id else ""
            self.log.emit(f"Upload paused{task_info}")
        
    def resume(self):
        """Resume the upload process"""
        with QMutexLocker(self._pause_mutex):
            self._is_paused = False
            task_info = f" [Task {self.task_id}]" if self.task_id else ""
            self.log.emit(f"Upload resumed{task_info}")
        
    def is_paused(self):
        """Check if upload is paused"""
        with QMutexLocker(self._pause_mutex):
            return self._is_paused
    
    def _get_task_info(self):
        """Helper method to get task info for logging"""
        return f" [Task {self.task_id}]" if self.task_id else ""
    
    def log_with_task_id(self, message):
        """Enhanced logging method that includes task ID"""
        task_info = self._get_task_info()
        self.log.emit(f"{message}{task_info}")
        
    def emit_progress_update(self):
        """Emit accurate progress based on uploaded files and bytes"""
        if self.total_files == 0:
            self.progress.emit(0, 1)
            return
            
        # Calculate progress based on completed files + current file progress
        completed_progress = self.uploaded_file_count + self.skipped_file_count
        
        # Add partial progress for current file if uploading
        if self.current_file_bytes > 0 and self.total_bytes > 0:
            current_file_progress = min(1.0, self.uploaded_bytes / self.total_bytes)
            total_progress = completed_progress + current_file_progress
        else:
            total_progress = completed_progress
            
        # Emit progress as (completed_items, total_items)
        progress_value = min(self.total_files, int(total_progress))
        self.progress.emit(progress_value, self.total_files)
        
        # Emit speed and ETA updates
        speed_str = self.progress_tracker.get_speed_formatted()
        eta_str = self.progress_tracker.get_eta_formatted()
        self.speed_update.emit(speed_str, eta_str)
        
    def save_state_atomic(self):
        """Save the current upload state atomically to prevent corruption"""
        try:
            state = self._prepare_state_data()
            
            # Write to temporary file first
            with tempfile.NamedTemporaryFile(
                mode='w', 
                dir=self.state_dir, 
                delete=False,
                suffix='.tmp'
            ) as temp_file:
                json.dump(state, temp_file, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_name = temp_file.name
            
            # Atomic rename
            if os.name == 'nt':  # Windows
                if self.state_file.exists():
                    backup_file = self.state_file.with_suffix('.bak')
                    shutil.move(str(self.state_file), str(backup_file))
                shutil.move(temp_name, str(self.state_file))
            else:  # Unix-like
                os.rename(temp_name, str(self.state_file))
                
            task_info = f" [Task {self.task_id}]" if self.task_id else ""
            self.log.emit(f"Success{task_info}: Upload state saved for order {self.order_number} (index: {self.current_file_index+1}/{self.total_files})")
            
        except Exception as e:
            task_info = f" [Task {self.task_id}]" if self.task_id else ""
            self.log.emit(f"Error{task_info} saving state: {str(e)}")
            # Clean up temp file if it exists
            if 'temp_name' in locals() and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except:
                    pass
    
    def _prepare_state_data(self):
        """Prepare state data for saving"""
        return {
            'folder_path': str(self.folder_path) if isinstance(self.folder_path, Path) else self.folder_path,
            'order_number': self.order_number,
            'task_id': self.task_id,  # Include task_id in state
            'order_date': self.order_date.isoformat() if hasattr(self.order_date, 'isoformat') else str(self.order_date),
            'photographers': self.photographers,
            'local_path': str(self.local_path) if isinstance(self.local_path, Path) else self.local_path,
            'is_paused': self._is_paused,
            'uploaded_file_count': self.uploaded_file_count,
            'skipped_file_count': self.skipped_file_count,
            'total_files': self.total_files,
            'completed_files': self.completed_files[:1000],  # Limit array size
            'current_file_index': self.current_file_index,
            'all_files': self._convert_paths_to_str(self.all_files[:1000] if len(self.all_files) > 1000 else self.all_files),
            'last_saved': datetime.now().isoformat(),
            'status': 'paused' if self._is_paused else 'running',
            'total_bytes': self.total_bytes,
            'uploaded_bytes': self.uploaded_bytes,
            'current_file_bytes': self.current_file_bytes
        }
    
    def save_state(self):
        """Save state using atomic method"""
        self.save_state_atomic()
    
    def _convert_paths_to_str(self, data):
        """Convert PosixPath objects to strings in nested data structures"""
        if isinstance(data, list):
            return [self._convert_paths_to_str(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._convert_paths_to_str(v) for k, v in data.items()}
        elif isinstance(data, Path):
            return str(data)
        else:
            return data
    
    def load_state(self):
        """Load the upload state from a file with enhanced error recovery"""
        if not self.state_file.exists():
            task_info = f" [Task {self.task_id}]" if self.task_id else ""
            self.log.emit(f"No saved state file exists{task_info}")
            return False
        
        try:
            # First validate that file isn't empty
            if self.state_file.stat().st_size == 0:
                task_info = f" [Task {self.task_id}]" if self.task_id else ""
                self.log.emit(f"State file is empty{task_info}: {self.state_file}")
                return False
            
            # Try to load primary state file
            primary_success = False
            try:
                with open(self.state_file, 'r') as f:
                    file_content = f.read()
                    
                # Try to parse JSON
                state = json.loads(file_content)
                primary_success = True
            except json.JSONDecodeError as e:
                self.log.emit(f"Error in basic state file format: {str(e)}")
                
                # Try to recover using backup files
                primary_success = self._try_recovery_from_backups()
                if primary_success:
                    with open(self.state_file, 'r') as f:
                        state = json.load(f)
                else:
                    return False
            
            # Load and validate state
            return self._load_state_from_dict(state)
            
        except Exception as e:
            self.log.emit(f"Error loading state: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
            return False
    
    def _try_recovery_from_backups(self):
        """Try to recover state from backup files"""
        backup_file = self.state_file.with_suffix('.bak')
        temp_file = self.state_file.with_suffix('.tmp')
        
        # First try the backup file
        if backup_file.exists() and backup_file.stat().st_size > 0:
            self.log.emit(f"Attempting to restore state from backup: {backup_file}")
            try:
                with open(backup_file, 'r') as f:
                    json.load(f)  # Validate JSON
                shutil.copy2(str(backup_file), str(self.state_file))
                self.log.emit("State successfully restored from backup")
                return True
            except Exception as backup_error:
                self.log.emit(f"Failed to restore state from backup: {str(backup_error)}")
        
        # Try temp file
        if temp_file.exists() and temp_file.stat().st_size > 0:
            self.log.emit(f"Attempting to restore state from temporary file: {temp_file}")
            try:
                with open(temp_file, 'r') as f:
                    json.load(f)  # Validate JSON
                shutil.copy2(str(temp_file), str(self.state_file))
                self.log.emit("State successfully restored from temporary file")
                return True
            except Exception as temp_error:
                self.log.emit(f"Failed to restore state from temporary file: {str(temp_error)}")
        
        return False
    
    def _load_state_from_dict(self, state):
        """Load state from dictionary with validation"""
        # Verify required fields exist in state
        required_fields = ['order_number', 'folder_path', 'current_file_index', 'total_files']
        missing_fields = [field for field in required_fields if field not in state]
        if missing_fields:
            self.log.emit(f"State file missing essential fields: {', '.join(missing_fields)}")
            return False
        
        # Load state values with validation
        self.folder_path = state['folder_path']
        self.order_number = state['order_number']
        
        # Handle loading order_date
        try:
            if isinstance(state['order_date'], str):
                try:
                    self.order_date = datetime.fromisoformat(state['order_date'])
                except (ValueError, TypeError):
                    self.order_date = state['order_date']
            else:
                self.order_date = state['order_date']
        except (KeyError, ValueError) as e:
            self.log.emit(f"Warning: Error loading order date: {str(e)}")
            self.order_date = datetime.now()
        
        # Load other state variables
        self.photographers = state.get('photographers', {})
        self.local_path = state.get('local_path', self.folder_path)
        self.task_id = state.get('task_id', self.task_id)  # Load task_id from state
        self._is_paused = state.get('is_paused', True)
        self.uploaded_file_count = max(0, state.get('uploaded_file_count', 0))
        self.skipped_file_count = max(0, state.get('skipped_file_count', 0))
        self.total_files = max(0, state.get('total_files', 0))
        self.completed_files = state.get('completed_files', [])
        self.current_file_index = max(0, min(state.get('current_file_index', 0), 
                                          state.get('total_files', 0) - 1))
        self.all_files = state.get('all_files', [])
        self.total_bytes = max(0, state.get('total_bytes', 0))
        self.uploaded_bytes = max(0, state.get('uploaded_bytes', 0))
        self.current_file_bytes = max(0, state.get('current_file_bytes', 0))
        
        # Include task_id in log if available
        task_info = f" (Task: {self.task_id})" if self.task_id else ""
        self.log.emit(f"Upload state loaded for order {self.order_number}{task_info} (index: {self.current_file_index+1}/{self.total_files})")
        return True

    @retry_on_failure(max_retries=3, delay=2, backoff=True)
    def upload_file_with_retry(self, s3, local_path, s3_key, content_type, callback):
        """Upload file with retry mechanism"""
        file_size = Path(local_path).stat().st_size
        
        if file_size > self.settings.multipart_threshold:
            # Use multipart upload for large files
            self._upload_multipart(s3, local_path, s3_key, content_type, callback)
        else:
            # Use regular upload for smaller files
            s3.upload_file(
                Filename=local_path,
                Bucket=self.aws_session.bucket_name,
                Key=s3_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ACL': 'private'
                },
                Callback=callback
            )
    
    def _upload_multipart(self, s3, local_path, s3_key, content_type, callback):
        """Handle multipart upload for large files"""
        # This is a simplified version - in production you'd want more sophisticated multipart handling
        self.log.emit(f"Using multipart upload for large file: {Path(local_path).name}")
        
        # For now, fall back to regular upload but with larger timeout
        s3.upload_file(
            Filename=local_path,
            Bucket=self.aws_session.bucket_name,
            Key=s3_key,
            ExtraArgs={
                'ContentType': content_type,
                'ACL': 'private'
            },
            Callback=callback
        )

    def run(self):
        """Main method that runs in the background thread"""
        self._is_running = True
        self.completed_files = []
        self.uploaded_file_count = 0
        
        # Initialize progress tracker
        self.progress_tracker = EnhancedProgressTracker()
        
        # Load saved state if exists
        saved_state = self.load_state()
        if saved_state:
            self.emit_progress_update()
            
        # Check if this is a mock session
        is_mock_session = self._is_mock_session()
        
        if is_mock_session:
            self._run_mock_upload()
            return
        
        # Initialize S3 client
        try:
            s3 = self._initialize_s3_client()
            if s3 is None:
                return
        except Exception as e:
            self.log.emit(f"Error creating AWS connection: {str(e)}")
            return
        
        # Verify bucket exists
        try:
            s3.head_bucket(Bucket=self.aws_session.bucket_name)
            self.log.emit(f"Connected to bucket: {self.aws_session.bucket_name}")
        except ClientError as e:
            self._handle_bucket_error(e)
            return
            
        # If no saved state, scan files and calculate totals
        if not saved_state:
            if not self._scan_and_prepare_files():
                return
                
        # Start the upload process
        self._process_upload_queue(s3)
        
        # Cleanup
        self.db_connection_manager.cleanup()
        
        # Clear current file progress when upload is finished
        self.current_file_name = ""
        self.current_file_uploaded_bytes = 0
        self.current_file_total_bytes = 0
        self.current_file_progress.emit("", 0, 0, 0)
        
        self.finished.emit()
    
    def _is_mock_session(self):
        """Check if this is a mock session for testing"""
        if self.aws_session is None:
            return True
            
        try:
            s3_client = self.aws_session.client('s3')
            return s3_client is None or isinstance(s3_client, MockS3Client)
        except Exception:
            return True
    
    def _initialize_s3_client(self):
        """Initialize S3 client with proper configuration"""
        if self.aws_session is None:
            self.log.emit("Error: AWS session is not available")
            return None
        
        # Check if aws_session has bucket_name attribute
        if not hasattr(self.aws_session, 'bucket_name'):
            parent = self.parent()
            aws_config = getattr(parent, 'aws_config', None)
            if aws_config:
                bucket_name = aws_config.get('AWS_S3_BUCKET', 'balistudiostorage')
                self.aws_session.bucket_name = bucket_name
                self.log.emit(f"Using bucket name from parent config: {bucket_name}")
            else:
                bucket_name = os.environ.get('AWS_S3_BUCKET', 'balistudiostorage')
                self.aws_session.bucket_name = bucket_name
                self.log.emit(f"Using bucket name from environment: {bucket_name}")
        
        # Create S3 client with enhanced configuration
        return self.aws_session.client('s3',
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'},
                connect_timeout=self.settings.connection_timeout,
                read_timeout=self.settings.read_timeout,
                retries={'max_attempts': self.settings.max_retries}
            )
        )
    
    def _handle_bucket_error(self, error):
        """Handle S3 bucket access errors"""
        error_code = error.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == '403':
            self.log.emit("Error: Access denied. Please check AWS permissions.")
        elif error_code == '404':
            self.log.emit("Error: Bucket does not exist. Please check bucket name.")
        else:
            self.log.emit(f"AWS error: {str(error)}")
    
    def _run_mock_upload(self):
        """Run mock upload simulation"""
        self.log.emit("Running with mock AWS session - simulating successful upload")
        
        # Get base prefix structure
        base_prefix = self.get_local_path_structure()
        
        if self.local_path:
            self._simulate_local_path_upload(base_prefix)
        else:
            self._simulate_folder_upload(base_prefix)
        
        self.save_state()
        self.finished.emit()
    
    def _simulate_local_path_upload(self, base_prefix):
        """Simulate upload from local path"""
        self.log.emit(f"Simulating upload from local path: {self.local_path}")
        total_files = 10
        self.total_files = total_files
        
        for i in range(1, total_files + 1):
            if not self._check_running_state():
                return
                
            time.sleep(0.2)
            self.uploaded_file_count = i
            self.emit_progress_update()
            
            file_name = f"simulated_file_{i}.jpg"
            mock_s3_path = f"{base_prefix}/{file_name}"
            self.completed_files.append(mock_s3_path)
            self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
        
        self.log.emit(f"Simulated upload successful to path: {base_prefix}")
    
    def _simulate_folder_upload(self, base_prefix):
        """Simulate upload from folder"""
        self.log.emit(f"Simulating upload from folder: {self.folder_path}")
        categories = ["CR2", "JPG", "Reels/Videos", "OTHER"]
        total_files = 30
        self.total_files = total_files
        
        for i in range(1, total_files + 1):
            if not self._check_running_state():
                return
                
            time.sleep(0.2)
            self.uploaded_file_count = i
            category = categories[i % len(categories)]
            self.emit_progress_update()
            
            file_name = f"{category}/simulated_file_{i}.jpg"
            mock_s3_path = f"{base_prefix}/{file_name}"
            self.completed_files.append(mock_s3_path)
            self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
        
        self.log.emit(f"Simulated upload successful to path: {base_prefix}")
    
    def _check_running_state(self):
        """Check if upload should continue running"""
        if not self._is_running:
            self.log.emit("Upload cancelled")
            return False
            
        if self.is_paused():
            self.log.emit("Upload paused")
            while self.is_paused() and self._is_running:
                time.sleep(0.5)
            
            if not self._is_running:
                self.log.emit("Upload cancelled while paused")
                return False
                
            self.log.emit("Upload resumed")
        
        return True
    
    def _scan_and_prepare_files(self):
        """Scan files and prepare for upload"""
        self.log.emit("Scanning files and calculating total size...")
        
        try:
            search_path = self.local_path if self.local_path else self.folder_path
            
            if not Path(search_path).exists():
                self.log.emit(f"Error: Search path does not exist: {search_path}")
                return False
            
            self.log.emit(f"🔍 Searching for files in: {search_path}")
            
            # Organize files by extension
            original_folder_path = self.folder_path
            self.folder_path = search_path
            organized_files = self.organize_files_by_extension()
            self.folder_path = original_folder_path
            
        except Exception as e:
            self.log.emit(f"Error organizing files: {str(e)}")
            return False
        
        # Check if files were found
        total_files_found = sum(len(files) for files in organized_files.values())
        if total_files_found == 0:
            self._handle_no_files_found()
            return False
        
        # Prepare file lists and calculate totals
        self._prepare_file_lists(organized_files)
        
        # Get already uploaded files from database
        self._check_previously_uploaded_files()
        
        # Log preparation results
        self.structured_logger.log_upload_start(self.total_files, self.total_bytes)
        
        # Save initial state
        self.save_state()
        return True
    
    def _handle_no_files_found(self):
        """Handle case when no files are found"""
        self.log.emit("⚠️  No files found for upload!")
        self.log.emit("📝 Possible reasons:")
        self.log.emit("   • Folder is empty")
        self.log.emit("   • All files are in Archive folder (ignored)")
        self.log.emit("   • Only system files present (.DS_Store, etc.)")
        self.log.emit("   • Files have unsupported extensions")
        
        # Create empty task to avoid errors
        self.all_files = []
        self.total_files = 0
        self.total_bytes = 0
        self.uploaded_file_count = 0
        self.skipped_file_count = 0
        self.completed_files = []
        
        self.save_state()
        self.finished.emit()
    
    def _prepare_file_lists(self, organized_files):
        """Prepare file lists and calculate totals"""
        self.all_files = []
        total_size = 0
        
        for category, files in organized_files.items():
            for file_info in files:
                self.all_files.append(file_info)
                total_size += file_info.get('size', 0)
        
        self.total_files = len(self.all_files)
        self.total_bytes = total_size
        
        self.log.emit(f"✅ Ready to upload: {self.total_files} files ({self._format_bytes(self.total_bytes)} total)")
    
    def _check_previously_uploaded_files(self):
        """Check for previously uploaded files"""
        try:
            uploaded_files = self.get_uploaded_files(self.order_number)
            uploaded_file_keys = set(uploaded_files)
            
            if uploaded_file_keys:
                self.log.emit(f"🔄 Found {len(uploaded_file_keys)} files already uploaded in database")
                self.completed_files = list(uploaded_file_keys)
                
                # Calculate bytes already uploaded
                uploaded_size = 0
                for file_info in self.all_files:
                    if file_info['s3_key'] in uploaded_file_keys:
                        uploaded_size += file_info.get('size', 0)
                
                self.uploaded_bytes = uploaded_size
                self.log.emit(f"📊 Already uploaded: {self._format_bytes(uploaded_size)}")
                
                # Calculate remaining
                remaining_files = self.total_files - len(uploaded_file_keys)
                remaining_size = self.total_bytes - uploaded_size
                if remaining_files > 0:
                    self.log.emit(f"⏳ Remaining: {remaining_files} files ({self._format_bytes(remaining_size)})")
            else:
                self.log.emit("🆕 No previous uploads found - starting fresh")
                self.completed_files = []
                self.uploaded_bytes = 0
                
        except Exception as db_err:
            self.log.emit(f"⚠️  Error querying database for uploaded files: {str(db_err)}")
            self.log.emit("📄 Assuming fresh upload due to database error")
            self.completed_files = []
            self.uploaded_bytes = 0
        
        # Reset counters
        self.current_file_index = 0
        self.uploaded_file_count = len([f for f in self.all_files if f['s3_key'] in self.completed_files])
        self.skipped_file_count = 0
    
    def _process_upload_queue(self, s3):
        """Process the upload queue"""
        uploaded_files_metadata = []
        start_time = time.time()
        
        # Add safeguards to ensure valid indices
        if self.current_file_index >= len(self.all_files):
            self.log.emit(f"Warning: Current file index ({self.current_file_index}) out of range, resetting to 0")
            self.current_file_index = 0
        
        # Process files from current_file_index (for resuming)
        for i in range(self.current_file_index, len(self.all_files)):
            if not self._check_running_state():
                self.save_state()
                break
            
            # Save current file index for resume capability
            self.current_file_index = i
            
            # Save state periodically
            if i % self.settings.state_save_interval == 0:
                self.save_state()
            
            try:
                file_info = self.all_files[i]
                success, metadata = self._upload_single_file(s3, file_info)
                
                if success and metadata:
                    uploaded_files_metadata.append(metadata)
                    
            except Exception as file_error:
                self.log.emit(f"Error processing file at index {i}: {str(file_error)}")
                self.skipped_file_count += 1
                self.emit_progress_update()
                continue
        
        # Finalize upload
        if self._is_running:
            total_time = time.time() - start_time
            self._finalize_upload(uploaded_files_metadata, total_time)
    
    def _upload_single_file(self, s3, file_info):
        """Upload a single file and return success status and metadata"""
        local_path = file_info['local_path']
        s3_key = file_info['s3_key']
        file_size = file_info['size']
        
        # Set current file size for progress calculation
        self.current_file_bytes = file_size
        
        # Check if file already uploaded
        if s3_key in self.completed_files:
            if Path(s3_key).name == '.DS_Store':
                self.skipped_file_count += 1
                return False, None
            
            self.log.emit(f"{Path(s3_key).name} Skipped (already uploaded)")
            self.skipped_file_count += 1
            self.emit_progress_update()
            return False, None
        
        # Verify file still exists
        local_file_path = Path(local_path)
        if not local_file_path.exists():
            self.log.emit(f"{Path(local_path).name} Skipped (file not found)")
            self.skipped_file_count += 1
            self.emit_progress_update()
            return False, None
        
        # Skip system files
        if Path(local_path).name == '.DS_Store':
            self.uploaded_file_count += 1
            self.uploaded_bytes += file_size
            self.emit_progress_update()
            return False, None
        
        try:
            # Log upload start
            self.log.emit(f"{Path(local_path).name} Uploading")
            upload_start_time = time.time()
            
            # Determine content type
            content_type = self._get_content_type(local_path)
            
            # Create progress callback
            callback = ProgressCallback(self, Path(local_path).name, file_size, self.settings)
            
            # Upload file with retry mechanism
            self.upload_file_with_retry(s3, local_path, s3_key, content_type, callback)
            
            # Update counters after successful upload
            upload_duration = time.time() - upload_start_time
            self.uploaded_file_count += 1
            self.uploaded_bytes += file_size
            
            # Clear current file progress
            self.current_file_name = ""
            self.current_file_uploaded_bytes = 0
            self.current_file_total_bytes = 0
            self.current_file_progress.emit("", 0, 0, 0)
            
            # Add to completed files
            self.completed_files.append(s3_key)
            
            # Log successful upload
            self.log.emit(f"{Path(s3_key).name} Uploaded")
            self.structured_logger.log_file_upload(
                Path(local_path).name, "SUCCESS", upload_duration, file_size
            )
            
            # Emit progress update
            self.emit_progress_update()
            
            # Prepare metadata for database
            metadata = {
                'order_number': self.order_number,
                's3_key': s3_key,
                'file_name': Path(local_path).name,
                'file_size': file_size,
                'file_type': content_type,
                'status': 'completed'
            }
            
            return True, metadata
            
        except Exception as upload_error:
            self.log.emit(f"{Path(s3_key).name} Error - {str(upload_error)}")
            self.structured_logger.log_file_upload(
                Path(local_path).name, f"FAILED: {str(upload_error)}"
            )
            self.skipped_file_count += 1
            self.emit_progress_update()
            return False, None
    
    def _get_content_type(self, local_path):
        """Determine content type based on file extension"""
        file_ext = Path(local_path).suffix.lower()
        content_type_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.mp4': 'video/mp4', '.mov': 'video/mp4',
            '.cr2': 'image/x-canon-cr2', '.cr3': 'image/x-canon-cr2',
            '.raw': 'image/x-canon-cr2', '.dng': 'image/x-canon-cr2',
            '.tif': 'image/tiff', '.tiff': 'image/tiff'
        }
        return content_type_map.get(file_ext, 'application/octet-stream')
    
    def _finalize_upload(self, uploaded_files_metadata, total_time):
        """Finalize the upload process"""
        try:
            # Record upload in database
            self._record_upload_in_database(uploaded_files_metadata)
            
            if not self.is_paused():
                # Generate final report
                self._generate_final_report(total_time)
                self.structured_logger.log_upload_complete(
                    self.uploaded_file_count, self.skipped_file_count, total_time
                )
            else:
                self.log.emit(f"Upload paused. {self.uploaded_file_count} files uploaded, {self.skipped_file_count} files skipped so far.")
                
        except Exception as e:
            self.log.emit(f"Error finalizing upload: {str(e)}")
    
    def _record_upload_in_database(self, uploaded_files_metadata):
        """Record the upload in the database"""
        try:
            parent = self.parent()
            db_manager = getattr(parent, 'db_manager', None)
            if db_manager is None:
                self.log.emit("No database manager available - skipping database operation.")
                return
                
            # Convert photographer IDs to integers
            main_photographer_id = int(self.photographers['main']) if self.photographers['main'] else None
            assistant_photographer_id = int(self.photographers['assistant']) if self.photographers['assistant'] else None
            video_photographer_id = int(self.photographers['video']) if self.photographers['video'] else None
            
            # Check for existing record
            with self.db_connection_manager.get_connection(db_manager) as connection:
                existing_record = self.check_existing_upload(db_manager, self.order_number)
                
                if existing_record:
                    self.log.emit(f"Updating existing upload record for order {self.order_number}")
                    success = self.update_upload_record(
                        db_manager, existing_record, self.uploaded_file_count,
                        main_photographer_id, assistant_photographer_id, video_photographer_id
                    )
                else:
                    self.log.emit(f"Creating new upload record for order {self.order_number}")
                    success = db_manager.record_upload(
                        self.order_number, 
                        self.uploaded_file_count + self.skipped_file_count,
                        main_photographer_id, assistant_photographer_id, video_photographer_id
                    )
                
                # Record detailed file upload history
                if success and uploaded_files_metadata:
                    success = self.record_upload_details(db_manager, uploaded_files_metadata)
                    
                if success:
                    self.log.emit(f"Upload recorded in database. {self.uploaded_file_count} files uploaded, {self.skipped_file_count} files skipped.")
                else:
                    self.log.emit("Failed to record upload in database")
                    
        except Exception as e:
            self.log.emit(f"Error recording upload in database: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
    
    def _generate_final_report(self, total_time):
        """Generate comprehensive final upload report"""
        self.log.emit("=" * 50)
        self.log.emit("🎉 UPLOAD COMPLETED SUCCESSFULLY!")
        self.log.emit("=" * 50)
        
        # Calculate statistics
        total_processed = self.uploaded_file_count + self.skipped_file_count
        upload_percentage = (self.uploaded_file_count / total_processed * 100) if total_processed > 0 else 0
        
        self.log.emit(f"📊 FINAL STATISTICS:")
        self.log.emit(f"   ✅ Files uploaded: {self.uploaded_file_count}")
        self.log.emit(f"   ⏭️  Files skipped: {self.skipped_file_count}")
        self.log.emit(f"   📁 Total processed: {total_processed}")
        self.log.emit(f"   📈 Upload rate: {upload_percentage:.1f}%")
        self.log.emit(f"   💾 Data uploaded: {self._format_bytes(self.uploaded_bytes)}")
        self.log.emit(f"   ⏱️  Total time: {total_time:.1f} seconds")
        
        # Calculate average speed
        if total_time > 0:
            avg_speed = self.uploaded_bytes / total_time
            self.log.emit(f"   🚀 Average speed: {self._format_bytes(avg_speed)}/s")
        
        # Show upload breakdown by category
        self._show_category_breakdown()
        
        self.log.emit("=" * 50)
        self.log.emit(f"Upload complete. {self.uploaded_file_count} files uploaded, {self.skipped_file_count} files skipped.")
    
    def _show_category_breakdown(self):
        """Show upload breakdown by file category"""
        if hasattr(self, 'all_files') and self.all_files:
            category_stats = {}
            for file_info in self.all_files:
                if file_info['s3_key'] in self.completed_files:
                    category = file_info.get('category', 'OTHER')
                    if category not in category_stats:
                        category_stats[category] = {'count': 0, 'size': 0}
                    category_stats[category]['count'] += 1
                    category_stats[category]['size'] += file_info.get('size', 0)
            
            if category_stats:
                self.log.emit(f"\n📂 UPLOAD BREAKDOWN BY CATEGORY:")
                category_emojis = {
                    'CR2': '📷', 'JPG': '🖼️', 
                    'Reels/Videos': '🎬', 'OTHER': '📄'
                }
                for category, stats in category_stats.items():
                    emoji = category_emojis.get(category, '📄')
                    self.log.emit(f"   {emoji} {category}: {stats['count']} files ({self._format_bytes(stats['size'])})")

    def organize_files_by_extension(self):
        """Scan, organize, and return files by extension for upload using parallel processing"""
        base_prefix = self.get_local_path_structure()
        
        folder_path = Path(self.folder_path) if not isinstance(self.folder_path, Path) else self.folder_path
        self.log.emit(f"Scanning {folder_path} for files to organize and upload...")
        
        # Dictionary to store organized files by category
        organized_files = {category: [] for category in self.extension_mappings.keys()}
        
        # Statistics for reporting
        stats = {
            'total_scanned': 0, 'organized_files': 0, 'skipped_archive': 0,
            'skipped_system': 0, 'by_category': {category: 0 for category in self.extension_mappings.keys()}
        }
        
        # First, organize loose files in the main directory
        self.log.emit("Step 1: Organizing loose files by extension...")
        loose_files_organized = self._organize_loose_files(folder_path, self.extension_mappings)
        if loose_files_organized > 0:
            self.log.emit(f"Organized {loose_files_organized} loose files into category folders")
        
        # Now scan all files using parallel processing for large directories
        self.log.emit("Step 2: Scanning all files for upload...")
        
        # Get all files
        all_files = list(folder_path.rglob('*'))
        
        if len(all_files) > 500:  # Use parallel processing for large directories
            organized_files = self._process_files_parallel(all_files, folder_path, base_prefix, stats)
        else:
            organized_files = self._process_files_sequential(all_files, folder_path, base_prefix, stats)
        
        # Generate detailed report
        self._generate_scan_report(stats, organized_files)
        
        return organized_files
    
    def _process_files_parallel(self, all_files, folder_path, base_prefix, stats):
        """Process files using parallel processing for large directories"""
        def process_file_batch(file_batch):
            batch_results = {category: [] for category in self.extension_mappings.keys()}
            batch_stats = {'scanned': 0, 'organized': 0, 'skipped_archive': 0, 'skipped_system': 0}
            
            for file_path in file_batch:
                if not file_path.is_file() or not self._is_running:
                    continue
                
                batch_stats['scanned'] += 1
                
                # Skip files in Archive folder
                relative_path = file_path.relative_to(folder_path)
                path_parts = relative_path.parts
                if 'Archive' in path_parts or 'archive' in path_parts:
                    batch_stats['skipped_archive'] += 1
                    continue
                
                # Skip system files
                if file_path.name.startswith('.') or file_path.name in ['.DS_Store', 'Thumbs.db', 'desktop.ini']:
                    batch_stats['skipped_system'] += 1
                    continue
                
                try:
                    file_info = self._create_file_info(file_path, folder_path, base_prefix)
                    if file_info:
                        category = file_info['category']
                        batch_results[category].append(file_info)
                        batch_stats['organized'] += 1
                except Exception as e:
                    self.log.emit(f"Error processing file {file_path}: {str(e)}")
            
            return batch_results, batch_stats
        
        # Split into batches
        batch_size = 100
        file_batches = [all_files[i:i+batch_size] for i in range(0, len(all_files), batch_size)]
        
        organized_files = {category: [] for category in self.extension_mappings.keys()}
        results_lock = threading.Lock()
        
        # Process in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_batch = {
                executor.submit(process_file_batch, batch): batch 
                for batch in file_batches
            }
            
            for future in concurrent.futures.as_completed(future_to_batch):
                try:
                    batch_results, batch_stats = future.result()
                    with results_lock:
                        for category, files in batch_results.items():
                            organized_files[category].extend(files)
                        
                        # Update stats
                        stats['total_scanned'] += batch_stats['scanned']
                        stats['organized_files'] += batch_stats['organized']
                        stats['skipped_archive'] += batch_stats['skipped_archive']
                        stats['skipped_system'] += batch_stats['skipped_system']
                        
                except Exception as e:
                    self.log.emit(f"Error in batch processing: {str(e)}")
        
        return organized_files
    
    def _process_files_sequential(self, all_files, folder_path, base_prefix, stats):
        """Process files sequentially for smaller directories"""
        organized_files = {category: [] for category in self.extension_mappings.keys()}
        
        for file_path in all_files:
            if not file_path.is_file() or not self._is_running:
                continue
            
            stats['total_scanned'] += 1
            
            # Skip files in Archive folder
            relative_path = file_path.relative_to(folder_path)
            path_parts = relative_path.parts
            if 'Archive' in path_parts or 'archive' in path_parts:
                stats['skipped_archive'] += 1
                continue
            
            # Skip system files
            if file_path.name.startswith('.') or file_path.name in ['.DS_Store', 'Thumbs.db', 'desktop.ini']:
                stats['skipped_system'] += 1
                continue
            
            try:
                file_info = self._create_file_info(file_path, folder_path, base_prefix)
                if file_info:
                    category = file_info['category']
                    organized_files[category].append(file_info)
                    stats['organized_files'] += 1
                    stats['by_category'][category] += 1
            except Exception as e:
                self.log.emit(f"Error processing file {file_path}: {str(e)}")
        
        return organized_files
    
    def _create_file_info(self, file_path, folder_path, base_prefix):
        return create_file_info_cross_platform(self, file_path, folder_path, base_prefix)

    def _organize_loose_files(self, folder_path, extension_mappings):
        """Organize loose files in the main directory into category folders"""
        organized_count = 0
        
        # Create category folders if they don't exist
        for category in extension_mappings.keys():
            category_path = folder_path / category
            if "/" in category:
                # Handle nested folders like "Reels/Videos"
                category_parts = category.split("/")
                current_path = folder_path
                for part in category_parts:
                    current_path = current_path / part
                    if not current_path.exists():
                        current_path.mkdir(exist_ok=True)
                        self.log.emit(f"Created folder: {current_path}")
            else:
                if not category_path.exists():
                    category_path.mkdir(exist_ok=True)
                    self.log.emit(f"Created folder: {category_path}")
        
        # Create Archive folder if it doesn't exist
        archive_path = folder_path / "Archive"
        if not archive_path.exists():
            archive_path.mkdir(exist_ok=True)
            self.log.emit(f"Created Archive folder: {archive_path}")
        
        # Find loose files in the main directory
        loose_files = []
        for item in folder_path.iterdir():
            if item.is_file():
                # Skip system files
                if item.name.startswith('.') or item.name in ['.DS_Store', 'Thumbs.db', 'desktop.ini']:
                    continue
                loose_files.append(item)
        
        if not loose_files:
            self.log.emit("No loose files found in main directory")
            return 0
        
        self.log.emit(f"Found {len(loose_files)} loose files to organize")
        
        # Organize each loose file
        for file_path in loose_files:
            if not self._is_running:
                break
                
            extension = file_path.suffix.lower()
            
            # Determine target category
            target_category = 'OTHER'
            for category, extensions in extension_mappings.items():
                if extension in extensions:
                    target_category = category
                    break
            
            # Create target path
            if "/" in target_category:
                # Handle nested category like "Reels/Videos"
                target_folder = folder_path
                for part in target_category.split('/'):
                    target_folder = target_folder / part
            else:
                target_folder = folder_path / target_category
            
            # Create target filename
            target_file = target_folder / file_path.name
            
            # Check if target file already exists
            if target_file.exists():
                self.log.emit(f"File already exists in {target_category}: {file_path.name}")
                continue
            
            try:
                # Move the file
                shutil.move(str(file_path), str(target_file))
                self.log.emit(f"Moved {file_path.name} → {target_category}/")
                organized_count += 1
            except Exception as e:
                self.log.emit(f"Error moving {file_path.name}: {str(e)}")
        
        return organized_count
    
    def _generate_scan_report(self, stats, organized_files):
        """Generate a detailed report of the scanning and organization process"""
        self.log.emit("=" * 50)
        self.log.emit("📊 SCAN AND ORGANIZATION REPORT")
        self.log.emit("=" * 50)
        
        # Overall statistics
        self.log.emit(f"📁 Total files scanned: {stats['total_scanned']}")
        self.log.emit(f"✅ Files ready for upload: {stats['organized_files']}")
        self.log.emit(f"🗃️ Files skipped (Archive): {stats['skipped_archive']}")
        self.log.emit(f"🔧 System files skipped: {stats['skipped_system']}")
        
        self.log.emit("\n📋 FILES BY CATEGORY:")
        total_size_by_category = {}
        
        for category, files in organized_files.items():
            if files:
                file_count = len(files)
                total_size = sum(f['size'] for f in files)
                total_size_by_category[category] = total_size
                
                # Count by original location
                organized_count = len([f for f in files if f['original_location'] == 'organized'])
                loose_count = len([f for f in files if f['original_location'] == 'loose'])
                
                self.log.emit(f"  📂 {category}: {file_count} files ({self._format_bytes(total_size)})")
                if organized_count > 0 and loose_count > 0:
                    self.log.emit(f"     └─ {organized_count} already organized, {loose_count} from loose files")
                elif loose_count > 0:
                    self.log.emit(f"     └─ {loose_count} organized from loose files")
                
                # Show file extensions in this category
                extensions = set(f['extension'] for f in files if f['extension'])
                if extensions:
                    ext_list = sorted(list(extensions))
                    self.log.emit(f"     └─ Extensions: {', '.join(ext_list)}")
        
        # Total size calculation
        total_upload_size = sum(total_size_by_category.values())
        self.log.emit(f"\n💾 Total upload size: {self._format_bytes(total_upload_size)}")
        
        # Upload strategy
        self.log.emit("\n🚀 UPLOAD STRATEGY:")
        self.log.emit("  • All files will be uploaded to S3 with organized folder structure")
        self.log.emit("  • Archive folder contents are ignored")
        self.log.emit("  • System files (.DS_Store, etc.) are skipped")
        self.log.emit("  • Progress will be tracked per file and by data volume")
        
        self.log.emit("=" * 50)

    def move_files_by_extension(self):
        """Move files to appropriate category folders based on extension (separate from upload scanning)"""
        folder_path = Path(self.folder_path) if not isinstance(self.folder_path, Path) else self.folder_path
        total_moved = 0
        self.log.emit(f"Organizing files in {folder_path} by extension...")
        
        # Create category folders if they don't exist
        for category in self.extension_mappings.keys():
            category_path = folder_path / category
            if "/" in category:
                # Handle nested folders like "Reels/Videos"
                category_parts = category.split("/")
                current_path = folder_path
                for part in category_parts:
                    current_path = current_path / part
                    if not current_path.exists():
                        current_path.mkdir(exist_ok=True)
            else:
                # Simple category folder
                if not category_path.exists():
                    category_path.mkdir(exist_ok=True)
        
        # Find all files in the main folder and subfolders
        all_files = []
        for file_path in folder_path.rglob('*'):
            if file_path.is_file():
                # Skip files already in category folders
                relative_path = file_path.relative_to(folder_path)
                parts = relative_path.parts
                if parts and parts[0] in self.extension_mappings:
                    # File is already in a category folder, skip
                    continue
                all_files.append(file_path)
        
        self.log.emit(f"Found {len(all_files)} files to organize")
        
        # Move each file to appropriate folder based on extension
        for file_path in all_files:
            extension = file_path.suffix.lower()
            
            # Determine target category
            target_category = 'OTHER'
            for category, extensions in self.extension_mappings.items():
                if extension in extensions:
                    target_category = category
                    break
            
            # Create target path
            if "/" in target_category:
                # Handle nested category like "Reels/Videos"
                target_folder = folder_path
                for part in target_category.split('/'):
                    target_folder = target_folder / part
            else:
                target_folder = folder_path / target_category
            
            # Create target filename
            target_file = target_folder / file_path.name
            
            # Check if target file already exists
            if target_file.exists():
                self.log.emit(f"Skipping {file_path.name} - already exists in {target_category}")
                continue
            
            try:
                # Move the file
                shutil.move(str(file_path), str(target_file))
                self.log.emit(f"Moved {file_path.name} to {target_category} folder")
                total_moved += 1
            except Exception as e:
                self.log.emit(f"Error moving {file_path.name}: {str(e)}")
        
        self.log.emit(f"File organization complete: moved {total_moved} files to appropriate folders")

    def _format_bytes(self, bytes_value):
        """Format bytes into human readable format"""
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.1f} KB"
        elif bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_value / (1024 * 1024 * 1024):.1f} GB"

    def get_local_path_structure(self):
        return get_local_path_structure_cross_platform(self)

    def get_uploaded_files(self, order_number):
        """
        Get list of already uploaded files for this order
        
        Args:
            order_number (str): Order number to check
            
        Returns:
            list: List of S3 keys for files already uploaded
        """
        parent = self.parent()
        db_manager = getattr(parent, 'db_manager', None)
        if db_manager is None:
            self.log.emit("No database manager available - treating as fresh upload")
            return []
        
        try:
            with self.db_connection_manager.get_connection(db_manager) as connection:
                cursor = connection.cursor(dictionary=True)
                
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
                    # Table doesn't exist yet - this is a fresh system
                    self.log.emit("🔍 Upload tracking table doesn't exist - treating as fresh upload")
                    return []
                
                # Get all files already uploaded for this order
                query = """
                SELECT s3_key
                FROM upload_files
                WHERE order_number = %s AND upload_status = 'completed'
                """
                cursor.execute(query, (order_number,))
                files = cursor.fetchall()
                
                return [file['s3_key'] for file in files] if files else []
                
        except Exception as e:
            self.log.emit(f"🔍 Error checking uploaded files: {e} - treating as fresh upload")
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
            with self.db_connection_manager.get_connection(db_manager) as connection:
                cursor = connection.cursor(dictionary=True)
                query = """
                SELECT upload_id, file_count
                FROM uploads
                WHERE order_number = %s
                """
                cursor.execute(query, (order_number,))
                result = cursor.fetchone()
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
            with self.db_connection_manager.get_connection(db_manager) as connection:
                cursor = connection.cursor()
                
                # Check if the uploads table has the photographer columns
                check_photographer_query = """
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'uploads' 
                AND COLUMN_NAME = 'main_photographer_id'
                """
                cursor.execute(check_photographer_query, (db_manager.rds_config['database'],))
                result = cursor.fetchone()
                photographer_exists = result[0] if result else 0
                
                # Check if the uploads table has the upload_completed column
                check_completed_query = """
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'uploads' 
                AND COLUMN_NAME = 'upload_completed'
                """
                cursor.execute(check_completed_query, (db_manager.rds_config['database'],))
                result = cursor.fetchone()
                completed_exists = result[0] if result else 0
                
                # Update the record with new total and update timestamp
                total_files = existing_record['file_count'] + new_files
                
                if photographer_exists == 0:
                    if completed_exists == 0:
                        # No upload_completed column
                        update_query = """
                        UPDATE uploads 
                        SET file_count = %s
                        WHERE upload_id = %s
                        """
                        cursor.execute(update_query, (total_files, existing_record['upload_id']))
                    else:
                        # With upload_completed column
                        update_query = """
                        UPDATE uploads 
                        SET file_count = %s, upload_completed = NOW()
                        WHERE upload_id = %s
                        """
                        cursor.execute(update_query, (total_files, existing_record['upload_id']))
                else:
                    # With photographer columns
                    if completed_exists == 0:
                        # No upload_completed column
                        update_query = """
                        UPDATE uploads 
                        SET file_count = %s,
                        main_photographer_id = %s,
                        assistant_photographer_id = %s,
                        video_photographer_id = %s
                        WHERE upload_id = %s
                        """
                        cursor.execute(update_query, (
                            total_files, main_id, assistant_id, video_id,
                            existing_record['upload_id']
                        ))
                    else:
                        # With upload_completed column
                        update_query = """
                        UPDATE uploads 
                        SET file_count = %s, upload_completed = NOW(),
                        main_photographer_id = %s,
                        assistant_photographer_id = %s,
                        video_photographer_id = %s
                        WHERE upload_id = %s
                        """
                        cursor.execute(update_query, (
                            total_files, main_id, assistant_id, video_id,
                            existing_record['upload_id']
                        ))
                
                connection.commit()
                return True
                
        except Exception as e:
            self.log.emit(f"Error updating upload record: {e}")
            import traceback
            self.log.emit(traceback.format_exc())
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
            with self.db_connection_manager.get_connection(db_manager) as connection:
                cursor = connection.cursor()
                
                insert_query = """
                INSERT INTO upload_files (
                    order_number, s3_key, file_name, file_size, file_type, upload_status, upload_timestamp
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """
                
                # Use executemany for batch insertion
                values = [
                    (
                        file['order_number'], file['s3_key'], file['file_name'],
                        file['file_size'], file['file_type'], file['status']
                    )
                    for file in file_metadata
                ]
                
                cursor.executemany(insert_query, values)
                connection.commit()
                
                self.log.emit(f"Recorded {len(file_metadata)} files in upload history")
                return True
                
        except Exception as e:
            self.log.emit(f"Error recording file upload details: {e}")
            import traceback
            self.log.emit(traceback.format_exc())
            return False


# Example usage and configuration
def create_uploader_with_settings(folder_path, order_number, order_date, aws_session, photographers, 
                                local_path=None, parent=None, task_id=None, **kwargs):
    """
    Factory function to create uploader with custom settings
    
    Args:
        folder_path: Path to folder containing files
        order_number: Order number for tracking
        order_date: Date of the order
        aws_session: AWS session for S3 access
        photographers: Dictionary of photographer IDs
        local_path: Specific local path (optional)
        parent: Parent QObject (optional)
        task_id: Unique task identifier (optional)
        **kwargs: Additional keyword arguments
        
    Returns:
        BackgroundUploader: Configured uploader instance
    """
    # Load settings from config file if it exists
    config_path = Path.home() / '.aws_uploader' / 'config.json'
    settings = UploaderSettings.from_config_file(config_path)
    
    # Create uploader with settings
    uploader = BackgroundUploader(
        folder_path=folder_path,
        order_number=order_number,
        order_date=order_date,
        aws_session=aws_session,
        photographers=photographers,
        local_path=local_path,
        parent=parent,
        settings=settings,
        task_id=task_id,
        **kwargs
    )
    
    return uploader


# Example settings configuration
def create_default_config():
    """Create a default configuration file"""
    config_dir = Path.home() / '.aws_uploader'
    config_dir.mkdir(exist_ok=True)
    
    config_path = config_dir / 'config.json'
    
    default_config = {
        "max_retries": 3,
        "retry_delay": 2,
        "chunk_size": 8192,
        "progress_update_interval": 1.0,
        "multipart_threshold": 104857600,  # 100MB
        "max_parallel_files": 3,
        "state_save_interval": 10,
        "connection_timeout": 60,
        "read_timeout": 300
    }
    
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=2)
    
    print(f"Default configuration created at: {config_path}")


if __name__ == "__main__":
    # Create default configuration if run directly
    create_default_config()