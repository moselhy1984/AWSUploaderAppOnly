#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
from datetime import datetime
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import shutil

class ProgressCallback:
    """Callback class to track upload progress for individual files"""
    def __init__(self, uploader, file_name, file_size):
        self.uploader = uploader
        self.file_name = file_name
        self.file_size = file_size
        self.bytes_transferred = 0
        
    def __call__(self, bytes_amount):
        self.bytes_transferred += bytes_amount
        # Emit progress for current file
        if self.file_size > 0:
            file_progress = min(100, (self.bytes_transferred / self.file_size) * 100)
            # Only emit progress updates every 5% or for small files
            if file_progress % 5 < 1 or self.file_size < 1024*1024:  # Every 5% or files < 1MB
                self.uploader.log.emit(f"{self.file_name}: {file_progress:.1f}% uploaded")

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
        self._is_paused = False  # Pause state variable
        self._pause_mutex = QMutex()  # mutex for synchronization
        self.uploaded_file_count = 0
        self.skipped_file_count = 0
        self.total_files = 0
        self.completed_files = []  # List of uploaded files
        self.current_file_index = 0  # Current file index for resuming
        self.all_files = []  # Store all files to be processed
        
        # Progress tracking improvements
        self.total_bytes = 0  # Total bytes to upload
        self.uploaded_bytes = 0  # Bytes uploaded so far
        self.current_file_bytes = 0  # Bytes of current file
        
        # Create state directory if it doesn't exist
        self.state_dir = Path.home() / '.aws_uploader'
        self.state_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / f"task_state_{order_number}.json"
    
    def stop(self):
        """Stop the upload process"""
        self._is_running = False
        
    def pause(self):
        """Pause the upload process"""
        with QMutexLocker(self._pause_mutex):
            self._is_paused = True
            self.log.emit("Upload paused")
        
    def resume(self):
        """Resume the upload process"""
        with QMutexLocker(self._pause_mutex):
            self._is_paused = False
            self.log.emit("Upload resumed")
        
    def is_paused(self):
        """Check if upload is paused"""
        with QMutexLocker(self._pause_mutex):
            return self._is_paused
        
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
        
    def save_state(self):
        """Save the current upload state to a file"""
        try:
            # Create a complete state object with all necessary information
            state = {
                'folder_path': str(self.folder_path) if isinstance(self.folder_path, Path) else self.folder_path,
                'order_number': self.order_number,
                'order_date': self.order_date.isoformat() if hasattr(self.order_date, 'isoformat') else str(self.order_date),
                'photographers': self.photographers,
                'local_path': str(self.local_path) if isinstance(self.local_path, Path) else self.local_path,
                'is_paused': self._is_paused,
                'uploaded_file_count': self.uploaded_file_count,
                'skipped_file_count': self.skipped_file_count,
                'total_files': self.total_files,
                'completed_files': self.completed_files[:1000],  # Limit array size to prevent huge files
                'current_file_index': self.current_file_index,
                # Convert all PosixPath objects to strings in all_files
                'all_files': self._convert_paths_to_str(self.all_files[:1000] if len(self.all_files) > 1000 else self.all_files),
                # Add timestamp for debugging
                'last_saved': datetime.now().isoformat(),
                'status': 'paused' if self._is_paused else 'running',
                'total_bytes': self.total_bytes,
                'uploaded_bytes': self.uploaded_bytes,
                'current_file_bytes': self.current_file_bytes
            }
            
            # Validate state before saving to prevent corrupted files
            if not state['order_number']:
                self.log.emit(f"Error: Order number missing, cannot save state")
                return
            
            if self.current_file_index > len(self.all_files):
                self.log.emit(f"Error: Invalid file index: {self.current_file_index}/{len(self.all_files)}")
                self.current_file_index = min(self.current_file_index, len(self.all_files) - 1)
                if self.current_file_index < 0:
                    self.current_file_index = 0
                state['current_file_index'] = self.current_file_index
            
            # First convert to JSON string to validate it can be serialized
            try:
                json_str = json.dumps(state, indent=2)
            except Exception as e:
                self.log.emit(f"Error converting state to JSON: {str(e)}")
                # Try with a simplified state
                simplified_state = {
                    'folder_path': str(self.folder_path) if isinstance(self.folder_path, Path) else self.folder_path,
                    'order_number': self.order_number,
                    'order_date': str(self.order_date),
                    'photographers': self.photographers,
                    'local_path': str(self.local_path) if isinstance(self.local_path, Path) else self.local_path,
                    'is_paused': self._is_paused,
                    'uploaded_file_count': self.uploaded_file_count,
                    'skipped_file_count': self.skipped_file_count,
                    'total_files': self.total_files,
                    'current_file_index': self.current_file_index,
                    'last_saved': datetime.now().isoformat(),
                    'status': 'paused' if self._is_paused else 'running',
                    'total_bytes': self.total_bytes,
                    'uploaded_bytes': self.uploaded_bytes,
                    'current_file_bytes': self.current_file_bytes
                }
                # Try again with simplified state
                json_str = json.dumps(simplified_state, indent=2)
            
            # Create directories if they don't exist
            self.state_dir.mkdir(exist_ok=True, parents=True)
            
            # Make a backup of the existing state file if it exists
            if self.state_file.exists():
                backup_file = self.state_file.with_suffix('.bak')
                try:
                    shutil.copy2(str(self.state_file), str(backup_file))
                except Exception as e:
                    self.log.emit(f"Warning: Failed to create backup: {str(e)}")
            
            # First write to a temporary file to prevent corruption
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                f.write(json_str)
                # Ensure data is written to disk
                f.flush()
                os.fsync(f.fileno())
            
            # Then rename the temporary file to the actual state file (safer atomic operation)
            if temp_file.exists():
                # On Windows, we need to remove the destination file first
                if os.name == 'nt' and self.state_file.exists():
                    try:
                        self.state_file.unlink()
                    except Exception as e:
                        self.log.emit(f"Warning: Failed to delete old state file: {str(e)}")
                
                # Use atomic rename/replace
                try:
                    temp_file.replace(self.state_file)
                except Exception as e:
                    # Fallback if replace fails
                    self.log.emit(f"Warning: Failed to replace state file, using copy as alternative: {str(e)}")
                    try:
                        shutil.copy2(str(temp_file), str(self.state_file))
                        temp_file.unlink()
                    except Exception as copy_err:
                        self.log.emit(f"Error during alternative copy: {str(copy_err)}")
                
            self.log.emit(f"Success: Upload state saved for order {self.order_number} (index: {self.current_file_index+1}/{self.total_files})")
        except Exception as e:
            self.log.emit(f"Error saving state: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
    
    def _convert_paths_to_str(self, data):
        """
        Convert PosixPath objects to strings in nested data structures
        
        Args:
            data: Data structure to process
            
        Returns:
            The processed data structure with Path objects converted to strings
        """
        if isinstance(data, list):
            return [self._convert_paths_to_str(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._convert_paths_to_str(v) for k, v in data.items()}
        elif isinstance(data, Path):
            return str(data)
        else:
            return data
    
    def load_state(self):
        """Load the upload state from a file"""
        if not self.state_file.exists():
            self.log.emit("No saved state file exists")
            return False
        
        try:
            # First validate that file isn't empty
            if self.state_file.stat().st_size == 0:
                self.log.emit(f"State file is empty: {self.state_file}")
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
                
                # Try to recover by checking for any backup files
                backup_file = self.state_file.with_suffix('.bak')
                temp_file = self.state_file.with_suffix('.tmp')
                
                # First try the backup file
                if backup_file.exists() and backup_file.stat().st_size > 0:
                    self.log.emit(f"Attempting to restore state from backup: {backup_file}")
                    try:
                        with open(backup_file, 'r') as f:
                            state = json.load(f)
                        # If successful, copy to main state file
                        shutil.copy2(str(backup_file), str(self.state_file))
                        self.log.emit("State successfully restored from backup")
                        primary_success = True
                    except Exception as backup_error:
                        self.log.emit(f"Failed to restore state from backup: {str(backup_error)}")
                
                # If backup file failed, try the temp file
                if not primary_success and temp_file.exists() and temp_file.stat().st_size > 0:
                    self.log.emit(f"Attempting to restore state from temporary file: {temp_file}")
                    try:
                        with open(temp_file, 'r') as f:
                            state = json.load(f)
                        # If successful, copy to main state file
                        shutil.copy2(str(temp_file), str(self.state_file))
                        self.log.emit("State successfully restored from temporary file")
                        primary_success = True
                    except Exception as temp_error:
                        self.log.emit(f"Failed to restore state from temporary file: {str(temp_error)}")
                
                # If all recovery attempts failed
                if not primary_success:
                    self.log.emit("All state restoration attempts failed")
                    return False
            
            # Verify required fields exist in state
            required_fields = ['order_number', 'folder_path', 'current_file_index', 'total_files']
            missing_fields = [field for field in required_fields if field not in state]
            if missing_fields:
                self.log.emit(f"State file missing essential fields: {', '.join(missing_fields)}")
                return False
            
            # Load state values with validation
            self.folder_path = state['folder_path']
            self.order_number = state['order_number']
            
            # Handle loading order_date which might be stored as string
            try:
                if isinstance(state['order_date'], str):
                    # Try to parse ISO format first
                    try:
                        self.order_date = datetime.fromisoformat(state['order_date'])
                    except (ValueError, TypeError):
                        # Fallback for other string formats
                        self.order_date = state['order_date']
                else:
                    self.order_date = state['order_date']
            except (KeyError, ValueError) as e:
                self.log.emit(f"Warning: Error loading order date: {str(e)}")
                self.order_date = datetime.now()  # Fallback to current date
            
            # Load photographers dictionary or use empty dict as fallback
            if 'photographers' in state and isinstance(state['photographers'], dict):
                self.photographers = state['photographers']
            else:
                self.log.emit("Warning: Photographer data not found in state file")
                self.photographers = {}
            
            # Load local_path with fallback to folder_path
            self.local_path = state.get('local_path', self.folder_path)
            
            # Load paused state
            self._is_paused = state.get('is_paused', True)  # Default to paused
            
            # Load file counters with validation
            self.uploaded_file_count = max(0, state.get('uploaded_file_count', 0))
            self.skipped_file_count = max(0, state.get('skipped_file_count', 0))
            self.total_files = max(0, state.get('total_files', 0))
            
            # Load completed files array with validation
            if 'completed_files' in state and isinstance(state['completed_files'], list):
                self.completed_files = state['completed_files']
            else:
                self.completed_files = []
            
            # Load current file index with validation
            self.current_file_index = max(0, min(state.get('current_file_index', 0), 
                                              state.get('total_files', 0) - 1))
            
            # Load all_files array with validation
            if 'all_files' in state and isinstance(state['all_files'], list):
                self.all_files = state['all_files']
            else:
                self.log.emit("Warning: File list not found in state file")
                self.all_files = []  # Will be reconstructed in run()
            
            # Load total_bytes, uploaded_bytes, and current_file_bytes
            self.total_bytes = max(0, state.get('total_bytes', 0))
            self.uploaded_bytes = max(0, state.get('uploaded_bytes', 0))
            self.current_file_bytes = max(0, state.get('current_file_bytes', 0))
            
            self.log.emit(f"Upload state loaded for order {self.order_number} (index: {self.current_file_index+1}/{self.total_files})")
            return True
            
        except Exception as e:
            self.log.emit(f"Error loading state: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
            return False

    def run(self):
        """Main method that runs in the background thread"""
        # Set thread running flag
        self._is_running = True
        
        # List to store completed files
        self.completed_files = []
        self.uploaded_file_count = 0
        
        # If we have a saved session state, load it
        saved_state = self.load_state()
        if saved_state:
            # If we loaded the state, update our running vars and emit progress
            self.emit_progress_update()
            
        # First, determine if this is a mock session (for testing)
        is_mock_session = False
        
        if self.aws_session is None:
            is_mock_session = True
            self.log.emit("Running with mock AWS session - simulating successful upload")
            
        # También comprobamos si client() devuelve None
        if not is_mock_session and self.aws_session is not None:
            try:
                s3_client = self.aws_session.client('s3')
                is_mock_session = (s3_client is None)
            except Exception:
                # Si ocurre una excepción al crear el cliente, asumimos que es una sesión simulada
                is_mock_session = True
        
        if is_mock_session:
            self.log.emit("Running with mock AWS session - simulating successful upload")
            
            # Ensure order_date is a datetime object
            if hasattr(self.order_date, 'toPyDate'):
                try:
                    # Convert QDate to Python date
                    py_date = self.order_date.toPyDate()
                    
                    # Validate the date is not year 0 or invalid
                    if py_date and py_date.year > 0:
                        year = py_date.year
                        month = f"{py_date.month:02d}-{year}"
                        day = f"{py_date.day:02d}-{month}"
                    else:
                        # Use current date as fallback
                        current_date = datetime.now()
                        year = current_date.year
                        month = f"{current_date.month:02d}-{year}"
                        day = f"{current_date.day:02d}-{month}"
                        self.log.emit(f"Warning: QDate has invalid year ({py_date}), using current date")
                except (ValueError, AttributeError) as e:
                    # Handle any errors with QDate conversion
                    self.log.emit(f"Error converting QDate: {str(e)}")
                    current_date = datetime.now()
                    year = current_date.year
                    month = f"{current_date.month:02d}-{year}"
                    day = f"{current_date.day:02d}-{month}"
                    self.log.emit(f"Using current date as fallback")
            elif isinstance(self.order_date, datetime):
                # It's already a datetime
                year = self.order_date.year
                month = f"{self.order_date.month:02d}-{year}"
                day = f"{self.order_date.day:02d}-{month}"
            elif isinstance(self.order_date, str):
                # Try to parse string date
                try:
                    date_obj = datetime.fromisoformat(self.order_date.replace('Z', '+00:00'))
                    year = date_obj.year
                    month = f"{date_obj.month:02d}-{year}"
                    day = f"{date_obj.day:02d}-{month}"
                except ValueError:
                    # Fallback to current date
                    current_date = datetime.now()
                    year = current_date.year
                    month = f"{current_date.month:02d}-{year}"
                    day = f"{current_date.day:02d}-{month}"
                    self.log.emit(f"Warning: Could not parse order date, using current date")
            else:
                # Fallback to current date
                current_date = datetime.now()
                year = current_date.year
                month = f"{current_date.month:02d}-{year}"
                day = f"{current_date.day:02d}-{month}"
                self.log.emit(f"Warning: Invalid order date type ({type(self.order_date)}), using current date")
                
            base_prefix = f"{year}/{month}/{day}/Order_{self.order_number}"
            
            # Simular carga exitosa
            if self.local_path:
                # Si tenemos una ruta local específica, simular la carga de un solo archivo
                self.log.emit(f"Simulating upload from local path: {self.local_path}")
                
                # Simular escaneo de archivos
                total_files = 10  # Número simulado de archivos
                self.total_files = total_files
                
                # Simular progreso
                for i in range(1, total_files + 1):
                    if not self._is_running:
                        self.log.emit("Upload cancelled")
                        return
                        
                    if self.is_paused():
                        self.log.emit("Upload paused")
                        while self.is_paused() and self._is_running:
                            time.sleep(0.5)
                        
                        if not self._is_running:
                            self.log.emit("Upload cancelled while paused")
                            return
                            
                        self.log.emit("Upload resumed")
                        
                    # Simular algo de trabajo
                    time.sleep(0.2)
                    
                    # Actualizar contador de archivos cargados
                    self.uploaded_file_count = i
                    
                    # Emitir progreso
                    self.emit_progress_update()
                    
                    # Registrar archivo simulado
                    file_name = f"simulated_file_{i}.jpg"
                    mock_s3_path = f"{base_prefix}/{file_name}"
                    self.completed_files.append(mock_s3_path)
                    
                    self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
                
                # Simular carga completa
                self.log.emit(f"Simulated upload successful to path: {base_prefix}")
                self.emit_progress_update()
                
            else:
                # Si tenemos una ruta de carpeta, simular la carga de múltiples archivos
                self.log.emit(f"Simulating upload from folder: {self.folder_path}")
                
                # Simular diferentes categorías de archivos
                categories = ["CR2", "JPG", "Reels/Videos", "OTHER"]
                total_files = 30  # Número simulado total de archivos
                self.total_files = total_files
                
                # Simular progreso
                for i in range(1, total_files + 1):
                    if not self._is_running:
                        self.log.emit("Upload cancelled")
                        return
                        
                    if self.is_paused():
                        self.log.emit("Upload paused")
                        while self.is_paused() and self._is_running:
                            time.sleep(0.5)
                        
                        if not self._is_running:
                            self.log.emit("Upload cancelled while paused")
                            return
                                
                        self.log.emit("Upload resumed")
                        
                    # Simular algo de trabajo
                    time.sleep(0.2)
                    
                    # Actualizar contador de archivos cargados
                    self.uploaded_file_count = i
                    
                    # Seleccionar categoría para este archivo simulado
                    category = categories[i % len(categories)]
                    
                    # Emitir progreso
                    self.emit_progress_update()
                    
                    # Registrar archivo simulado
                    file_name = f"{category}/simulated_file_{i}.jpg"
                    mock_s3_path = f"{base_prefix}/{file_name}"
                    self.completed_files.append(mock_s3_path)
                    
                    self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
                
                # Simular carga completa
                self.log.emit(f"Simulated upload successful to path: {base_prefix}")
                self.emit_progress_update()
            
            # Guardar el estado
            self.save_state()
            
            # Emitir señal de finalización
            self.finished.emit()
            
            return
        
        # Initialize S3 client
        try:
            # Check if aws_session is None or missing required attributes
            if self.aws_session is None:
                self.log.emit("Error: AWS session is not available")
                return
            
            # Check if aws_session has bucket_name attribute
            if not hasattr(self.aws_session, 'bucket_name'):
                # Try to get from parent configuration
                parent = self.parent()
                if parent and hasattr(parent, 'aws_config'):
                    bucket_name = parent.aws_config.get('AWS_S3_BUCKET', 'balistudiostorage')
                    # Attach to aws_session
                    self.aws_session.bucket_name = bucket_name
                    self.log.emit(f"Using bucket name from parent config: {bucket_name}")
                else:
                    # Try to get from environment
                    import os
                    bucket_name = os.environ.get('AWS_S3_BUCKET', 'balistudiostorage')
                    self.aws_session.bucket_name = bucket_name
                    self.log.emit(f"Using bucket name from environment: {bucket_name}")
            
            # Create S3 client
            s3 = self.aws_session.client('s3',
                config=boto3.session.Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'}
                )
            )
            
            # Si el cliente S3 es None, tratarlo como una sesión simulada
            if s3 is None:
                self.log.emit("Detected mock session with None s3 client")
                raise AttributeError("S3 client is None")
                
        except AttributeError as attr_error:
            self.log.emit(f"Error creating AWS connection: AWS session missing required attributes - {str(attr_error)}")
            self.log.emit("Please configure valid AWS credentials before uploading.")
            return
        except Exception as e:
            self.log.emit(f"Error creating AWS connection: {str(e)}")
            self.log.emit("Please check your AWS configuration and try again.")
            return
        
        # Create S3 path structure based on local folder structure
        try:
            # Get all files to upload
            try:
                # Use local_path if available, otherwise fallback to folder_path
                search_path = self.local_path if self.local_path else self.folder_path
                
                # Check if search path exists
                if not Path(search_path).exists():
                    self.log.emit(f"Error: Search path does not exist: {search_path}")
                    self.log.emit(f"🔍 Checked paths:")
                    self.log.emit(f"   • local_path: {self.local_path}")
                    self.log.emit(f"   • folder_path: {self.folder_path}")
                    return
                
                self.log.emit(f"🔍 Searching for files in: {search_path}")
                
                # Temporarily update folder_path for organize_files_by_extension
                original_folder_path = self.folder_path
                self.folder_path = search_path
                
                # Organize files by extension (this will also move loose files)
                organized_files = self.organize_files_by_extension()
                
                # Restore original folder_path
                self.folder_path = original_folder_path
            except Exception as e:
                self.log.emit(f"Error organizing files: {str(e)}")
                return
        except Exception as e:
            self.log.emit(f"Error creating path structure: {str(e)}")
            # Use fallback path structure with current date
            now = datetime.now()
            year = now.year
            month = f"{now.month:02d}-{year}"
            day = f"{now.day:02d}-{now.month:02d}-{year}"
            base_prefix = f"{year}/{month}/{day}/Order_{self.order_number}"
            self.log.emit(f"Using alternative path structure: {base_prefix}")
        
        # Verify bucket exists
        try:
            s3.head_bucket(Bucket=self.aws_session.bucket_name)
            self.log.emit(f"Connected to bucket: {self.aws_session.bucket_name}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '403':
                self.log.emit("Error: Access denied. Please check AWS permissions.")
            elif error_code == '404':
                self.log.emit("Error: Bucket does not exist. Please check bucket name.")
            else:
                self.log.emit(f"AWS error: {str(e)}")
            return
            
        # If we don't have saved state, scan files and calculate totals
        if not saved_state:
            # Scan files and calculate total size
            self.log.emit("Scanning files and calculating total size...")
            
            # Get all files to upload
            try:
                # Use local_path if available, otherwise fallback to folder_path
                search_path = self.local_path if self.local_path else self.folder_path
                
                # Check if search path exists
                if not Path(search_path).exists():
                    self.log.emit(f"Error: Search path does not exist: {search_path}")
                    self.log.emit(f"🔍 Checked paths:")
                    self.log.emit(f"   • local_path: {self.local_path}")
                    self.log.emit(f"   • folder_path: {self.folder_path}")
                    return
                
                self.log.emit(f"🔍 Searching for files in: {search_path}")
                
                # Temporarily update folder_path for organize_files_by_extension
                original_folder_path = self.folder_path
                self.folder_path = search_path
                
                # Organize files by extension (this will also move loose files)
                organized_files = self.organize_files_by_extension()
                
                # Restore original folder_path
                self.folder_path = original_folder_path
            except Exception as e:
                self.log.emit(f"Error organizing files: {str(e)}")
                return
            
            # Check if we found any files
            total_files_found = sum(len(files) for files in organized_files.values())
            if total_files_found == 0:
                self.log.emit("⚠️  No files found for upload!")
                self.log.emit("📝 Possible reasons:")
                self.log.emit("   • Folder is empty")
                self.log.emit("   • All files are in Archive folder (ignored)")
                self.log.emit("   • Only system files present (.DS_Store, etc.)")
                self.log.emit("   • Files have unsupported extensions")
                
                # Still create empty task to avoid errors
                self.all_files = []
                self.total_files = 0
                self.total_bytes = 0
                self.uploaded_file_count = 0
                self.skipped_file_count = 0
                self.completed_files = []
                
                # Save state and finish
                self.save_state()
                self.finished.emit()
                return
            
            # Flatten the organized files into a single list
            self.all_files = []
            total_size = 0
            
            for category, files in organized_files.items():
                for file_info in files:
                    self.all_files.append(file_info)
                    total_size += file_info.get('size', 0)
            
            self.total_files = len(self.all_files)
            self.total_bytes = total_size
            
            self.log.emit(f"✅ Ready to upload: {self.total_files} files ({self._format_bytes(self.total_bytes)} total)")
            
            # Get list of already uploaded files from database to optimize skipping
            try:
                uploaded_files = self.get_uploaded_files(self.order_number)
                uploaded_file_keys = set(uploaded_files)
                
                if uploaded_file_keys:
                    self.log.emit(f"🔄 Found {len(uploaded_file_keys)} files already uploaded in database")
                    
                    # Set completed files from previous uploads
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
                # If database query fails, assume this is a fresh upload
                self.log.emit("📄 Assuming fresh upload due to database error")
                self.completed_files = []
                self.uploaded_bytes = 0
            
            # Reset counters for new uploads
            self.current_file_index = 0
            self.uploaded_file_count = len([f for f in self.all_files if f['s3_key'] in self.completed_files])
            self.skipped_file_count = 0
            
            # Save initial state
            self.save_state()
            
            return
        
        # Initialize counters for resumed upload
        processed_files = self.current_file_index
        uploaded_files = self.uploaded_file_count
        skipped_files = self.skipped_file_count
        uploaded_files_metadata = []  # to store uploaded files information to keep in the database
        
        # Update progress to show initial state
        self.emit_progress_update()
        
        # Add safeguards to ensure valid indices
        if self.current_file_index >= len(self.all_files):
            self.log.emit(f"Warning: Current file index ({self.current_file_index}) out of range, resetting to 0")
            self.current_file_index = 0
        
        # Process files from the current_file_index (for resuming)
        for i in range(self.current_file_index, len(self.all_files)):
            # Check for pause state
            while self.is_paused():
                # Wait during pause
                time.sleep(0.5)
                if not self._is_running:  # Check if cancelled during pause
                    self.log.emit("Upload cancelled during pause")
                    break
            
            if not self._is_running:
                self.log.emit("Upload cancelled")
                # Save state before exiting
                self.save_state()
                break
            
            # Save current file index for resume capability
            self.current_file_index = i
            
            # Save state periodically (every 10 files)
            if i % 10 == 0:
                self.save_state()
            
            try:
                file_info = self.all_files[i]
                local_path = file_info['local_path']
                s3_key = file_info['s3_key']
                file_size = file_info['size']
                
                # Set current file size for progress calculation
                self.current_file_bytes = file_size
                
                # Check if file already uploaded
                if s3_key in self.completed_files:
                    # Ignore system files
                    if Path(s3_key).name == '.DS_Store':
                        skipped_files += 1
                        self.skipped_file_count = skipped_files
                        continue
                    self.log.emit(f"تم تخطي {Path(s3_key).name} (مرفوع سابقًا)")
                    skipped_files += 1
                    self.skipped_file_count = skipped_files
                    # Update progress for skipped files
                    self.emit_progress_update()
                    continue
                
                # Verify file still exists
                local_file_path = Path(local_path)
                if not local_file_path.exists():
                    self.log.emit(f"Warning: File doesn't exist, skipping: {local_path}")
                    skipped_files += 1
                    self.skipped_file_count = skipped_files
                    self.emit_progress_update()
                    continue
                
                # Upload the file to S3
                try:
                    # Ignore system files
                    if Path(local_path).name == '.DS_Store':
                        uploaded_files += 1
                        self.uploaded_file_count = uploaded_files
                        self.uploaded_bytes += file_size
                        self.emit_progress_update()
                        continue
                    
                    # Calculate overall progress percentage
                    overall_progress = ((uploaded_files + skipped_files) / self.total_files) * 100 if self.total_files > 0 else 0
                    bytes_progress = (self.uploaded_bytes / self.total_bytes) * 100 if self.total_bytes > 0 else 0
                    
                    # Get file info for better logging
                    file_category = file_info.get('category', 'Unknown')
                    file_extension = file_info.get('extension', Path(local_path).suffix.lower())
                    original_location = file_info.get('original_location', 'unknown')
                    
                    location_emoji = "📁" if original_location == "organized" else "📄"
                    category_emoji = {
                        'CR2': '📷',
                        'JPG': '🖼️', 
                        'Reels/Videos': '🎬',
                        'OTHER': '📄'
                    }.get(file_category, '📄')
                    
                    self.log.emit(f"{location_emoji} جارٍ رفع {Path(local_path).name} ({uploaded_files + skipped_files + 1}/{self.total_files})")
                    self.log.emit(f"   {category_emoji} النوع: {file_category} | الامتداد: {file_extension} | المصدر: {original_location}")
                    self.log.emit(f"   📊 التقدم: {overall_progress:.1f}% ملفات، {bytes_progress:.1f}% بيانات")
                    
                    # Get file extension to determine content type
                    file_ext = Path(local_path).suffix.lower()
                    content_type = 'application/octet-stream'  # Default content type
                    
                    # Set appropriate content type based on file extension
                    if file_ext in ['.jpg', '.jpeg']:
                        content_type = 'image/jpeg'
                    elif file_ext == '.png':
                        content_type = 'image/png'
                    elif file_ext in ['.mp4', '.mov']:
                        content_type = 'video/mp4'
                    elif file_ext in ['.cr2', '.cr3', '.raw', '.dng']:
                        content_type = 'image/x-canon-cr2'
                    elif file_ext in ['.tif', '.tiff']:
                        content_type = 'image/tiff'
                    
                    # Create progress callback for this file
                    callback = ProgressCallback(self, Path(local_path).name, file_size)
                    
                    # Upload file to S3
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
                    
                    # Update counters
                    uploaded_files += 1
                    self.uploaded_file_count = uploaded_files
                    self.uploaded_bytes += file_size
                    
                    # Add file to completed files list
                    self.completed_files.append(s3_key)
                    
                    # Store metadata for database
                    uploaded_files_metadata.append({
                        'order_number': self.order_number,
                        's3_key': s3_key,
                        'file_name': Path(local_path).name,
                        'file_size': file_size,
                        'file_type': content_type,
                        'status': 'completed'
                    })
                    
                    # Emit progress update after successful upload
                    self.emit_progress_update()
                    
                    # Calculate final progress percentages
                    final_overall_progress = ((uploaded_files + skipped_files) / self.total_files) * 100 if self.total_files > 0 else 0
                    final_bytes_progress = (self.uploaded_bytes / self.total_bytes) * 100 if self.total_bytes > 0 else 0
                    
                    self.log.emit(f"✅ تم رفع {Path(s3_key).name} بنجاح!")
                    self.log.emit(f"   📈 التقدم الإجمالي: {final_overall_progress:.1f}% ملفات، {final_bytes_progress:.1f}% بيانات ({uploaded_files + skipped_files}/{self.total_files})")
                    
                except Exception as upload_error:
                    self.log.emit(f"❌ خطأ في رفع {Path(s3_key).name}: {str(upload_error)}")
                    skipped_files += 1
                    self.skipped_file_count = skipped_files
                    self.emit_progress_update()
            except Exception as file_error:
                self.log.emit(f"Error processing file at index {i}: {str(file_error)}")
                skipped_files += 1
                self.skipped_file_count = skipped_files
                self.emit_progress_update()
                continue
        
        # Final update of counters
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
            
            if not self.is_paused():  # Only report completion if not paused
                # Generate final upload report
                self.log.emit("=" * 50)
                self.log.emit("🎉 UPLOAD COMPLETED SUCCESSFULLY!")
                self.log.emit("=" * 50)
                
                # Calculate statistics
                total_processed = uploaded_files + skipped_files
                upload_percentage = (uploaded_files / total_processed * 100) if total_processed > 0 else 0
                
                self.log.emit(f"📊 FINAL STATISTICS:")
                self.log.emit(f"   ✅ Files uploaded: {uploaded_files}")
                self.log.emit(f"   ⏭️  Files skipped: {skipped_files}")
                self.log.emit(f"   📁 Total processed: {total_processed}")
                self.log.emit(f"   📈 Upload rate: {upload_percentage:.1f}%")
                self.log.emit(f"   💾 Data uploaded: {self._format_bytes(self.uploaded_bytes)}")
                
                # Show upload breakdown by category if available
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
                        for category, stats in category_stats.items():
                            emoji = {
                                'CR2': '📷',
                                'JPG': '🖼️', 
                                'Reels/Videos': '🎬',
                                'OTHER': '📄'
                            }.get(category, '📄')
                            self.log.emit(f"   {emoji} {category}: {stats['count']} files ({self._format_bytes(stats['size'])})")
                
                self.log.emit("=" * 50)
                
                self.log.emit(f"Upload complete. {uploaded_files} files uploaded, {skipped_files} files skipped.")
            else:
                self.log.emit(f"Upload paused. {uploaded_files} files uploaded, {skipped_files} files skipped so far.")
        
        self.finished.emit()
    
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
            is_connected = False
            try:
                is_connected = db_manager.connection and db_manager.connection.is_connected()
            except Exception:
                is_connected = False
                
            if not is_connected:
                db_manager.connect()
                
            cursor = None
            
            try:
                cursor = db_manager.connection.cursor()
                
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
                            total_files, 
                            main_id,
                            assistant_id,
                            video_id,
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
                            total_files, 
                            main_id,
                            assistant_id,
                            video_id,
                            existing_record['upload_id']
                        ))
                
                db_manager.connection.commit()
                return True
            finally:
                if cursor:
                    cursor.close()
                
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
            is_connected = False
            try:
                is_connected = db_manager.connection and db_manager.connection.is_connected()
            except Exception:
                is_connected = False
                
            if not is_connected:
                db_manager.connect()
                
            cursor = None
            
            try:
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
                
                self.log.emit(f"Recorded {len(file_metadata)} files in upload history")
                return True
            finally:
                if cursor:
                    cursor.close()
                
        except Exception as e:
            self.log.emit(f"Error recording file upload details: {e}")
            import traceback
            self.log.emit(traceback.format_exc())
            return False

    def organize_files_by_extension(self):
        """Scan, organize, and return files by extension for upload"""
        # Define extension mappings
        extension_mappings = {
            'CR2': ['.cr2', '.cr3', '.nef', '.arw', '.raw', '.dng'],  # Raw image files
            'JPG': ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.heic', '.webp'],  # Image files
            'Reels/Videos': ['.mp4', '.mov', '.avi', '.wmv', '.flv', '.m4v', '.mkv', '.webm', '.3gp'],  # Video files
            'OTHER': []  # Default category for other types
        }
        
        # Get base S3 prefix using local path structure
        base_prefix = self.get_local_path_structure()
        
        # Convert Path to string if needed
        folder_path = self.folder_path
        if isinstance(folder_path, Path):
            folder_path = Path(folder_path)
        else:
            folder_path = Path(str(folder_path))
            
        self.log.emit(f"Scanning {folder_path} for files to organize and upload...")
        
        # Dictionary to store organized files by category
        organized_files = {category: [] for category in extension_mappings.keys()}
        
        # Statistics for reporting
        stats = {
            'total_scanned': 0,
            'organized_files': 0,
            'skipped_archive': 0,
            'skipped_system': 0,
            'by_category': {category: 0 for category in extension_mappings.keys()}
        }
        
        # First, organize loose files in the main directory
        self.log.emit("Step 1: Organizing loose files by extension...")
        loose_files_organized = self._organize_loose_files(folder_path, extension_mappings)
        if loose_files_organized > 0:
            self.log.emit(f"Organized {loose_files_organized} loose files into category folders")
        
        # Now scan all files (both organized and any remaining loose files)
        self.log.emit("Step 2: Scanning all files for upload...")
        
        # Scan the entire folder structure
        for file_path in folder_path.rglob('*'):
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
            
            # Determine file category
            file_extension = file_path.suffix.lower()
            file_category = 'OTHER'  # Default
            
            for category, extensions in extension_mappings.items():
                if file_extension in extensions:
                    file_category = category
                    break
            
            # Determine S3 key based on file location
            if len(path_parts) > 1 and path_parts[0] in extension_mappings:
                # File is already in a category folder
                category_from_path = path_parts[0]
                rel_path_in_category = Path(*path_parts[1:])
                s3_category_prefix = category_from_path.replace('/', '_')  # Handle nested paths
                s3_key = f"{base_prefix}/{s3_category_prefix}/{rel_path_in_category}"
                actual_category = category_from_path
            else:
                # File is loose or in a non-category folder
                s3_key = f"{base_prefix}/{file_category}/{relative_path}"
                actual_category = file_category
            
            try:
                file_size = file_path.stat().st_size
                
                file_info = {
                    'local_path': str(file_path),
                    's3_key': s3_key,
                    'size': file_size,
                    'category': actual_category,
                    'extension': file_extension,
                    'original_location': 'organized' if len(path_parts) > 1 and path_parts[0] in extension_mappings else 'loose'
                }
                
                organized_files[actual_category].append(file_info)
                stats['organized_files'] += 1
                stats['by_category'][actual_category] += 1
                
            except Exception as file_err:
                self.log.emit(f"Error processing file {file_path}: {str(file_err)}")
        
        # Generate detailed report
        self._generate_scan_report(stats, organized_files)
        
        return organized_files
    
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
        
        # Find loose files in the main directory (not in subdirectories)
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
            target_category = 'OTHER'  # Default category
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
        # Define extension mappings
        extension_mappings = {
            'CR2': ['.cr2', '.cr3', '.nef', '.arw', '.raw'],  # Raw image files
            'JPG': ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.heic'],  # Image files
            'Reels/Videos': ['.mp4', '.mov', '.avi', '.wmv', '.flv', '.m4v', '.mkv', '.webm'],  # Video files
            'OTHER': []  # Default category for other types
        }
        
        # Convert Path to string if needed
        folder_path = self.folder_path
        if isinstance(folder_path, Path):
            folder_path = Path(folder_path)
        else:
            folder_path = Path(str(folder_path))
            
        total_moved = 0
        self.log.emit(f"Organizing files in {folder_path} by extension...")
        
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
                if parts and parts[0] in extension_mappings:
                    # File is already in a category folder, skip
                    continue
                all_files.append(file_path)
        
        self.log.emit(f"Found {len(all_files)} files to organize")
        
        # Move each file to appropriate folder based on extension
        for file_path in all_files:
            extension = file_path.suffix.lower()
            
            # Determine target category
            target_category = 'OTHER'  # Default category
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
        """
        Extract the local path structure to replicate it on S3
        Starting from the year folder instead of Booking_Folders
        
        Returns:
            str: The relative path structure to use as S3 prefix
        """
        try:
            # Get the local folder path
            folder_path = Path(self.folder_path)
            
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
                self.log.emit(f"📁 Using year-based structure: {relative_structure}")
                return str(relative_structure)
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
                            self.log.emit(f"📁 Found year folder, using: {relative_structure}")
                            return str(relative_structure)
                
                # If no year found in expected location, try pattern matching
                folder_name = folder_path.name
                parent_folder = folder_path.parent.name
                grandparent_folder = folder_path.parent.parent.name
                
                # Check if grandparent looks like a year
                if grandparent_folder.isdigit() and len(grandparent_folder) == 4 and grandparent_folder.startswith('20'):
                    relative_structure = Path(grandparent_folder) / parent_folder / folder_name
                    self.log.emit(f"📁 Detected year structure: {relative_structure}")
                    return str(relative_structure)
                
                # Check if parent looks like a year
                elif parent_folder.isdigit() and len(parent_folder) == 4 and parent_folder.startswith('20'):
                    relative_structure = Path(parent_folder) / folder_name
                    self.log.emit(f"📁 Detected year structure: {relative_structure}")
                    return str(relative_structure)
                
                else:
                    # Ultimate fallback: use just the order folder
                    self.log.emit(f"📁 No year found, using order folder only: {folder_name}")
                    return folder_name
                    
        except Exception as e:
            self.log.emit(f"⚠️ Error extracting local path structure: {str(e)}")
            # Ultimate fallback
            return f"Order_{self.order_number}"

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
            self.log.emit("🔍 No database manager available - treating as fresh upload")
            return []
        
        db_manager = parent.db_manager
        is_connected = False
        try:
            is_connected = db_manager.connection and db_manager.connection.is_connected()
        except Exception:
            is_connected = False
            
        if not is_connected:
            try:
                db_manager.connect()
            except Exception as conn_error:
                self.log.emit(f"🔍 Cannot connect to database: {str(conn_error)} - treating as fresh upload")
                return []
        
        cursor = None
        files = []
        
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
        finally:
            if cursor:
                cursor.close()
    
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
            # Create a new connection for this thread if needed
            is_connected = False
            try:
                is_connected = db_manager.connection and db_manager.connection.is_connected()
            except Exception:
                is_connected = False
                
            if not is_connected:
                # Create a fresh connection to avoid conflict with other threads
                db_manager.connect()
                
            cursor = None
            result = None
            
            try:
                cursor = db_manager.connection.cursor(dictionary=True)
                query = """
                SELECT upload_id, file_count
                FROM uploads
                WHERE order_number = %s
                """
                cursor.execute(query, (order_number,))
                result = cursor.fetchone()
            finally:
                if cursor:
                    cursor.close()
            
            return result
            
        except Exception as e:
            self.log.emit(f"Error checking existing upload: {e}")
            return None