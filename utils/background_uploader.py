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
                 photographers, local_path=None, parent=None, missing_files_list=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.order_number = order_number
        self.order_date = order_date
        self.aws_session = aws_session
        self.photographers = photographers
        self.local_path = local_path
        self.missing_files_list = missing_files_list  # Lista de archivos pendientes
        self._is_running = True
        self._is_paused = False  # Pause state variable
        self._pause_mutex = QMutex()  # mutex for synchronization
        self.uploaded_file_count = 0
        self.skipped_file_count = 0
        self.total_files = 0
        self.completed_files = []  # List of uploaded files
        self.current_file_index = 0  # Current file index for resuming
        self.all_files = []  # Store all files to be processed
        
        # Create state directory if it doesn't exist
        self.state_dir = Path.home() / '.aws_uploader'
        self.state_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / f"task_state_{order_number}.json"
        
        # If we have a missing files list, log the first few items for debugging
        if missing_files_list and len(missing_files_list) > 0:
            self.log.emit(f"Initialized with {len(missing_files_list)} missing files to upload")
            examples = missing_files_list[:3]
            for i, example in enumerate(examples):
                self.log.emit(f"Missing file {i+1}: {example}")
            if len(missing_files_list) > 3:
                self.log.emit(f"...and {len(missing_files_list) - 3} more files")
    
    def stop(self):
        """Stop the upload process"""
        self._is_running = False
        
    def pause(self):
        """Pause the upload process"""
        # Using QMutexLocker for safe handling of shared variables
        locker = QMutexLocker(self._pause_mutex)
        self._is_paused = True
        self.log.emit("Upload paused. Task will complete current file and then wait.")
        # Save state when paused
        self.save_state()
        
    def resume(self):
        """Resume the paused upload process"""
        # Using QMutexLocker for safe handling of shared variables
        locker = QMutexLocker(self._pause_mutex)
        self._is_paused = False
        self.log.emit("Upload resumed.")
        
    def is_paused(self):
        """Check if the uploader is paused"""
        # Using QMutexLocker for safe handling of shared variables
        locker = QMutexLocker(self._pause_mutex)
        return self._is_paused
        
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
                # Save missing files list if provided
                'missing_files_list': self.missing_files_list
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
                    'status': 'paused' if self._is_paused else 'running'
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
            
            if not primary_success:
                # If all attempts failed, we can't load state
                self.log.emit("Could not load any valid state file")
                return False
            
            # Validate required fields
            if not state.get('order_number') or state.get('order_number') != self.order_number:
                self.log.emit(f"State file for wrong order number. Expected {self.order_number}, got {state.get('order_number')}")
                return False
                
            # Some versions have different folder_path format
            if isinstance(state.get('folder_path'), list):
                self.log.emit("State file has old format folder_path (list)")
                folder_str = str(self.folder_path)
                self.log.emit(f"Using current folder path: {folder_str}")
            else:
                # Use folder path from state if not already set
                folder_from_state = state.get('folder_path')
                if folder_from_state and not self.folder_path:
                    self.log.emit(f"Using folder path from state: {folder_from_state}")
                    self.folder_path = folder_from_state
            
            # Use local path from state if not already set
            local_path_from_state = state.get('local_path')
            if local_path_from_state and not self.local_path:
                self.log.emit(f"Using local path from state: {local_path_from_state}")
                self.local_path = local_path_from_state
            
            # Set completion data
            self.uploaded_file_count = state.get('uploaded_file_count', 0)
            self.skipped_file_count = state.get('skipped_file_count', 0)
            self.total_files = state.get('total_files', 0)
            self.current_file_index = state.get('current_file_index', 0)
            self.completed_files = state.get('completed_files', [])
            
            # Set pause state
            pause_state = state.get('is_paused', False)
            locker = QMutexLocker(self._pause_mutex)
            self._is_paused = pause_state
            
            # Load missing files list if it exists in the saved state
            if 'missing_files_list' in state and not self.missing_files_list:
                self.missing_files_list = state.get('missing_files_list')
                self.log.emit(f"Loaded {len(self.missing_files_list)} missing files from saved state")
            
            # Get all files - need to be careful because it might be a very large list
            all_files_from_state = state.get('all_files', [])
            if all_files_from_state:
                self.all_files = all_files_from_state
                self.log.emit(f"Loaded {len(self.all_files)} files from state")
                self.log.emit(f"Resuming upload of order {self.order_number} at file {self.current_file_index+1}/{self.total_files}")
            
            # Log important state values
            self.log.emit(f"State loaded: files={self.total_files}, current={self.current_file_index}, uploaded={self.uploaded_file_count}")
            
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
            self.progress.emit(self.current_file_index, self.total_files)
            
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
                    progress = int((i / total_files) * 100)
                    self.progress.emit(i, total_files)
                    
                    # Registrar archivo simulado
                    file_name = f"simulated_file_{i}.jpg"
                    mock_s3_path = f"{base_prefix}/{file_name}"
                    self.completed_files.append(mock_s3_path)
                    
                    self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
                
                # Simular carga completa
                self.log.emit(f"Simulated upload successful to path: {base_prefix}")
                self.progress.emit(total_files, total_files)
                
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
                    progress = int((i / total_files) * 100)
                    self.progress.emit(i, total_files)
                    
                    # Registrar archivo simulado
                    file_name = f"{category}/simulated_file_{i}.jpg"
                    mock_s3_path = f"{base_prefix}/{file_name}"
                    self.completed_files.append(mock_s3_path)
                    
                    self.log.emit(f"Simulated upload {i}/{total_files}: {mock_s3_path}")
                
                # Simular carga completa
                self.log.emit(f"Simulated upload successful to path: {base_prefix}")
                self.progress.emit(total_files, total_files)
            
            # Guardar el estado
            self.save_state()
            
            # Emitir señal de finalización
            self.finished.emit()
            
            return
        
        # Initialize S3 client
        try:
            # Use the supplied AWS session to initialize S3 client
            s3_client = self.aws_session.client('s3')
            bucket_name = self.aws_session.bucket_name if hasattr(self.aws_session, 'bucket_name') else "balistudiostorage"
            
            self.log.emit(f"Connected to AWS S3 bucket: {bucket_name}")
            
            # Check if files were previously loaded from state
            if not self.all_files:
                # First time loading files
                # If we have a missing_files_list, use that instead of scanning the directory
                if self.missing_files_list and len(self.missing_files_list) > 0:
                    self.log.emit(f"Using provided list of {len(self.missing_files_list)} missing files")
                    
                    # Convert relative paths to full paths
                    base_path = self.local_path if self.local_path else self.folder_path
                    all_files = []
                    
                    for rel_path in self.missing_files_list:
                        full_path = os.path.join(base_path, rel_path)
                        if os.path.exists(full_path):
                            all_files.append(full_path)
                        else:
                            self.log.emit(f"Warning: Missing file not found: {full_path}")
                    
                    self.all_files = all_files
                    self.total_files = len(all_files)
                    
                    self.log.emit(f"Prepared {self.total_files} missing files for upload")
                    
                elif self.local_path and os.path.isdir(self.local_path):
                    # If local_path is set and is a directory, get files from there
                    self.log.emit(f"Getting files from local path: {self.local_path}")
                    all_files = []
                    
                    # Walk through directory and collect files
                    for root, dirs, files in os.walk(self.local_path):
                        for file in files:
                            # Skip hidden files and temporary files
                            if file.startswith('.') or '.tmp' in file or '.crdownload' in file:
                                continue
                                
                            file_path = os.path.join(root, file)
                            all_files.append(file_path)
                    
                    self.all_files = all_files
                    self.total_files = len(all_files)
                    
                    self.log.emit(f"Found {self.total_files} files in: {self.local_path}")
                    
                elif self.folder_path and os.path.isdir(self.folder_path):
                    # Get files from folder_path
                    self.log.emit(f"Getting files from folder path: {self.folder_path}")
                    all_files = []
                    
                    # Walk through directory and collect files
                    for root, dirs, files in os.walk(self.folder_path):
                        for file in files:
                            # Skip hidden files and temporary files
                            if file.startswith('.') or '.tmp' in file or '.crdownload' in file:
                                continue
                                
                            file_path = os.path.join(root, file)
                            all_files.append(file_path)
                    
                    self.all_files = all_files
                    self.total_files = len(all_files)
                    
                    self.log.emit(f"Found {self.total_files} files in: {self.folder_path}")
                    
                else:
                    # No valid path, can't upload
                    self.log.emit("Error: No valid folder path or local path specified")
                    return
            
            # Ensure we have a reasonable total_files value
            if self.total_files <= 0 and len(self.all_files) > 0:
                self.total_files = len(self.all_files)
                
            # Validate current file index is within range
            if self.current_file_index >= self.total_files:
                self.log.emit(f"Warning: Current file index ({self.current_file_index}) is >= total files ({self.total_files})")
                self.current_file_index = 0
                
            # Emit initial progress
            self.progress.emit(self.current_file_index, self.total_files)
            
            # Get date parts for constructing S3 path
            date_str = self._parse_order_date()
            
            # Upload files
            for i in range(self.current_file_index, len(self.all_files)):
                if not self._is_running:
                    self.log.emit("Upload cancelled")
                    break
                    
                if self.is_paused():
                    self.log.emit("Upload paused")
                    self.save_state()  # Save state before waiting
                    
                    while self.is_paused() and self._is_running:
                        time.sleep(0.5)
                    
                    if not self._is_running:
                        self.log.emit("Upload cancelled while paused")
                        break
                        
                    self.log.emit("Upload resumed")
                    
                # Get current file
                file_path = self.all_files[i]
                
                try:
                    # Check if file exists
                    if not os.path.isfile(file_path):
                        self.log.emit(f"Skipping non-existent file: {file_path}")
                        self.skipped_file_count += 1
                        continue
                        
                    # Get file size
                    file_size = os.path.getsize(file_path)
                    
                    # Skip empty files
                    if file_size == 0:
                        self.log.emit(f"Skipping empty file: {file_path}")
                        self.skipped_file_count += 1
                        continue
                    
                    # Process file based on its type and determine appropriate S3 path
                    file_name = os.path.basename(file_path)
                    self.log.emit(f"Processing file: {file_name}")
                    
                    # Determine file extension
                    _, ext = os.path.splitext(file_name)
                    ext = ext.lower()
                    
                    # Determine S3 object key based on file type
                    relative_path = os.path.dirname(os.path.relpath(file_path, self.local_path or self.folder_path))
                    
                    # Replace backslashes with forward slashes for S3 paths
                    relative_path = relative_path.replace('\\', '/')
                    
                    # Construct S3 path based on order number and date
                    if relative_path and relative_path != '.':
                        s3_key = f"orders/{date_str}/{self.order_number}/{relative_path}/{file_name}"
                    else:
                        s3_key = f"orders/{date_str}/{self.order_number}/{file_name}"
                    
                    # Normalize path
                    s3_key = s3_key.replace('//', '/')
                    
                    # Upload file to S3
                    self.log.emit(f"Uploading to: {s3_key}")
                    
                    # Create a callback to track upload progress for this file
                    # Create a callback to track upload progress
                    def progress_callback(bytes_transferred):
                        if not self._is_running:
                            raise Exception("Upload cancelled")
                    
                    # Upload file to S3 with progress tracking
                    with open(file_path, 'rb') as f:
                        s3_client.upload_fileobj(
                            f, 
                            bucket_name, 
                            s3_key,
                            Callback=progress_callback
                        )
                    
                    # Add file to completed list
                    self.completed_files.append(s3_key)
                    self.uploaded_file_count += 1
                    
                    # Update current file index for state saving
                    self.current_file_index = i + 1
                    
                    # Emit progress update
                    self.progress.emit(self.current_file_index, self.total_files)
                    
                    # Save state periodically (every 5 files)
                    if self.uploaded_file_count % 5 == 0:
                        self.save_state()
                    
                except Exception as e:
                    if not self._is_running:
                        self.log.emit("Upload cancelled during file transfer")
                        break
                        
                    self.log.emit(f"Error uploading file {file_path}: {str(e)}")
                    
                    # Still update the index so we don't get stuck on a problematic file
                    self.current_file_index = i + 1
                    self.skipped_file_count += 1
            
            # Save final state
            self.save_state()
            
            # Log completion
            self.log.emit(f"Upload complete for order {self.order_number}")
            self.log.emit(f"Uploaded {self.uploaded_file_count} files, skipped {self.skipped_file_count}")
            
            # Emit finished signal
            self.finished.emit()
            
        except Exception as e:
            self.log.emit(f"Error during upload: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
            
            # Try to save state before exiting
            self.save_state()
            
            # Still emit finished to keep UI responsive
            self.finished.emit()

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
        is_connected = False
        try:
            is_connected = db_manager.connection and db_manager.connection.is_connected()
        except Exception:
            is_connected = False
            
        if not is_connected:
            db_manager.connect()
        
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
            
            return [file['s3_key'] for file in files] if files else []
            
        except Exception as e:
            self.log.emit(f"Error checking uploaded files: {e}")
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
        """
        Organize files by their extension
        
        Returns:
            dict: Dictionary mapping file extensions to lists of files
        """
        file_extensions = {}
        
        for file_path in self.all_files:
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            if ext in file_extensions:
                file_extensions[ext].append(file_path)
            else:
                file_extensions[ext] = [file_path]
                
        return file_extensions
    
    def scan_for_missing_files(self, db_manager=None):
        """
        Scan local files and compare with S3 to find files that need to be uploaded
        
        Args:
            db_manager: Optional database manager for checking uploaded files
            
        Returns:
            dict: Dictionary with scan results containing:
                - total_files: Total number of local files
                - uploaded_files: Number of files already in S3
                - missing_files: Number of files not in S3
                - missing_file_list: List of relative paths of missing files
        """
        self.log.emit(f"Scanning for missing files in order {self.order_number}")
        
        try:
            # Initialize result data
            result = {
                'total_files': 0,
                'uploaded_files': 0,
                'missing_files': 0,
                'missing_file_list': [],
                'has_partial_uploads': False
            }
            
            # Make sure we have a valid local path
            base_path = self.local_path if self.local_path else self.folder_path
            if not base_path or not os.path.exists(base_path):
                self.log.emit(f"Error: Invalid folder path for scan: {base_path}")
                return None
                
            # Get date parts for constructing S3 path
            date_str = self._parse_order_date()
            
            # Get S3 client
            if not self.aws_session:
                self.log.emit("No AWS session available for S3 scan")
                return None
                
            s3_client = self.aws_session.client('s3')
            bucket_name = getattr(self.aws_session, 'bucket_name', "balistudiostorage")
            
            # Build prefix for S3 paths based on order and date
            s3_prefix = f"orders/{date_str}/{self.order_number}/"
            
            # Scan local files
            local_files = []
            local_file_sizes = {}
            
            for root, _, files in os.walk(base_path):
                for file in files:
                    # Skip hidden and temporary files
                    if file.startswith('.') or file.endswith('.tmp') or file.endswith('.crdownload'):
                        continue
                        
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_path)
                    # Normalize to forward slashes for comparison with S3
                    rel_path = rel_path.replace('\\', '/')
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        local_files.append(rel_path)
                        local_file_sizes[rel_path] = file_size
                    except OSError:
                        self.log.emit(f"Warning: Could not access file: {file_path}")
            
            self.log.emit(f"Found {len(local_files)} local files in {base_path}")
            
            # Check for files in S3
            s3_files = []
            s3_file_sizes = {}
            
            try:
                # Use pagination to handle large directories
                paginator = s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)
                
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Get the key and remove the prefix to get the relative path
                            key = obj['Key']
                            if key.startswith(s3_prefix):
                                rel_key = key[len(s3_prefix):]
                                s3_files.append(rel_key)
                                s3_file_sizes[rel_key] = obj['Size']
                
                self.log.emit(f"Found {len(s3_files)} files already uploaded to S3 in {s3_prefix}")
            except Exception as e:
                self.log.emit(f"Error listing S3 objects: {str(e)}")
                # If we can't get S3 files, we'll assume all files need to be uploaded
                s3_files = []
            
            # Find missing files (files in local directory but not in S3)
            missing_files = []
            size_mismatch_files = []
            
            for file in local_files:
                if file not in s3_files:
                    missing_files.append(file)
                elif local_file_sizes.get(file, 0) != s3_file_sizes.get(file, -1):
                    # Size mismatch means the file might be partially uploaded
                    size_mismatch_files.append(file)
            
            # Combine missing and size mismatched files as both need to be uploaded
            all_missing_files = missing_files + size_mismatch_files
            
            # Update the result dictionary
            result['total_files'] = len(local_files)
            result['uploaded_files'] = len(s3_files)
            result['missing_files'] = len(all_missing_files)
            result['missing_file_list'] = all_missing_files
            result['has_partial_uploads'] = len(size_mismatch_files) > 0
            
            # Log some examples of missing files for debugging
            if all_missing_files:
                examples = all_missing_files[:5]
                self.log.emit("Examples of missing files:")
                for example in examples:
                    self.log.emit(f" - {example}")
                
                if len(all_missing_files) > 5:
                    self.log.emit(f" - And {len(all_missing_files) - 5} more...")
            
            return result
            
        except Exception as e:
            self.log.emit(f"Error scanning for missing files: {str(e)}")
            import traceback
            self.log.emit(traceback.format_exc())
            return None
    
    def _parse_order_date(self):
        """
        Parse the order date into a string format suitable for S3 paths
        
        Returns:
            str: Date string in the format "YYYY/MM-YYYY/DD-MM-YYYY"
        """
        try:
            # Handle different date formats
            if hasattr(self.order_date, 'toPyDate'):
                # It's a QDate
                try:
                    py_date = self.order_date.toPyDate()
                    if py_date and py_date.year > 0:
                        year = py_date.year
                        month = f"{py_date.month:02d}-{year}"
                        day = f"{py_date.day:02d}-{month}"
                        return f"{year}/{month}/{day}"
                except Exception as e:
                    self.log.emit(f"Error converting QDate: {str(e)}")
            
            elif isinstance(self.order_date, datetime):
                # It's a datetime object
                year = self.order_date.year
                month = f"{self.order_date.month:02d}-{year}"
                day = f"{self.order_date.day:02d}-{month}"
                return f"{year}/{month}/{day}"
            
            elif isinstance(self.order_date, str):
                # Try to parse string date in various formats
                try:
                    # Try ISO format first
                    date_obj = datetime.fromisoformat(self.order_date.replace('Z', '+00:00'))
                    year = date_obj.year
                    month = f"{date_obj.month:02d}-{year}"
                    day = f"{date_obj.day:02d}-{month}"
                    return f"{year}/{month}/{day}"
                except ValueError:
                    # Try common date formats
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']:
                        try:
                            date_obj = datetime.strptime(self.order_date, fmt)
                            year = date_obj.year
                            month = f"{date_obj.month:02d}-{year}"
                            day = f"{date_obj.day:02d}-{month}"
                            return f"{year}/{month}/{day}"
                        except ValueError:
                            continue
            
            # If we get here, we couldn't parse the date
            self.log.emit(f"Could not parse order date: {self.order_date}, using current date")
            
        except Exception as e:
            self.log.emit(f"Error parsing order date: {str(e)}")
        
        # Default to current date if all parsing fails
        now = datetime.now()
        year = now.year
        month = f"{now.month:02d}-{year}"
        day = f"{now.day:02d}-{month}"
        return f"{year}/{month}/{day}"