#!/usr/bin/env python3
"""
Task Manager Integration Adapter
Bridges the enhanced task manager with the existing GUI system
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtCore import Qt, QObject, pyqtSignal

from enhanced_task_manager import EnhancedTaskManager, TaskMetadata, TaskStatus, TaskPriority

class TaskManagerAdapter(QObject):
    """
    Adapter class that integrates EnhancedTaskManager with the existing GUI
    """
    
    # Signals for UI updates
    task_status_changed = pyqtSignal(str, str)  # task_uuid, status
    task_progress_updated = pyqtSignal(str, float, str)  # task_uuid, progress, current_file
    task_added = pyqtSignal(str)  # task_uuid
    task_removed = pyqtSignal(str)  # task_uuid
    
    def __init__(self, gui_instance, db_manager):
        super().__init__()
        self.gui = gui_instance
        self.db_manager = db_manager
        
        # Initialize enhanced task manager
        self.task_manager = EnhancedTaskManager(
            db_manager=db_manager,
            logger_callback=self._log_message
        )
        
        # Setup callbacks
        self.task_manager.add_status_callback(self._on_task_status_changed)
        self.task_manager.add_progress_callback(self._on_task_progress_updated)
        
        # Task UUID to list item mapping
        self._task_items: Dict[str, QListWidgetItem] = {}
        
        # Legacy task ID to UUID mapping for backward compatibility
        self._legacy_id_to_uuid: Dict[int, str] = {}
        self._next_legacy_id = 1
        
    def initialize_from_existing_tasks(self):
        """Initialize the enhanced task manager from existing GUI tasks"""
        if not hasattr(self.gui, 'upload_tasks'):
            return
            
        # Store original tasks for conversion
        original_tasks = self.gui.upload_tasks.copy()
        
        # Clear the GUI task list first to prevent conflicts
        self.gui.upload_tasks.clear()
        self.gui.task_list.clear()
        
        self._log_message(f"Converting {len(original_tasks)} legacy tasks to enhanced format")
        
        # Convert each original task
        converted_count = 0
        for old_task in original_tasks:
            try:
                # Convert old task format to new format
                task_uuid = self._convert_legacy_task(old_task)
                if task_uuid:
                    # Queue the task if it's not completed
                    task = self.task_manager.get_task(task_uuid)
                    if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED]:
                        self.task_manager.queue_task(task_uuid)
                    converted_count += 1
                        
            except Exception as e:
                self._log_message(f"Error converting legacy task: {e}")
                continue
        
        self._log_message(f"Successfully converted {converted_count} legacy tasks")
        
        # Rebuild UI from enhanced task manager
        self._rebuild_task_list()
        
        # Update GUI to use enhanced task manager methods
        self._patch_gui_task_access()
    
    def load_tasks_from_database(self, device_id: int):
        """Load tasks from database using enhanced task manager"""
        count = self.task_manager.load_tasks_from_database(device_id)
        self._rebuild_task_list()
        return count
    
    def create_new_task(self, order_number: str, folder_path: str, local_path: str,
                       photographers: Dict, order_date: datetime, device_id: int,
                       created_by: str = "") -> Optional[str]:
        """Create a new task using enhanced task manager"""
        try:
            task_uuid = self.task_manager.create_task(
                order_number=order_number,
                folder_path=folder_path,
                local_path=local_path,
                photographers=photographers,
                order_date=order_date,
                device_id=device_id,
                created_by=created_by
            )
            
            # Add to UI
            self._add_task_to_ui(task_uuid)
            
            # Queue for execution
            self.task_manager.queue_task(task_uuid)
            
            return task_uuid
            
        except ValueError as e:
            self._log_message(f"Error creating task: {e}")
            return None
    
    def start_task(self, task_uuid: str) -> bool:
        """Start a specific task"""
        return self.task_manager.queue_task(task_uuid)
    
    def pause_task(self, task_uuid: str, paused_by: str = "") -> bool:
        """Pause a running task"""
        return self.task_manager.pause_task(task_uuid, paused_by)
    
    def resume_task(self, task_uuid: str, resumed_by: str = "") -> bool:
        """Resume a paused task"""
        return self.task_manager.resume_task(task_uuid, resumed_by)
    
    def cancel_task(self, task_uuid: str, cancelled_by: str = "") -> bool:
        """Cancel a task"""
        return self.task_manager.cancel_task(task_uuid, cancelled_by)
    
    def complete_task(self, task_uuid: str, success: bool = True, error_message: str = ""):
        """Mark task as completed"""
        self.task_manager.complete_task(task_uuid, success, error_message)
    
    def update_task_progress(self, task_uuid: str, progress: float, current_file: str = "",
                           files_completed: int = 0, total_files: int = 0,
                           bytes_uploaded: int = 0, total_bytes: int = 0):
        """Update task progress"""
        self.task_manager.update_task_progress(
            task_uuid=task_uuid,
            progress=progress,
            current_file=current_file,
            files_completed=files_completed,
            total_files=total_files,
            bytes_uploaded=bytes_uploaded,
            total_bytes=total_bytes
        )
    
    def get_task_by_uuid(self, task_uuid: str) -> Optional[TaskMetadata]:
        """Get task by UUID"""
        return self.task_manager.get_task(task_uuid)
    
    def get_task_by_order(self, order_number: str) -> Optional[TaskMetadata]:
        """Get task by order number"""
        return self.task_manager.get_task_by_order(order_number)
    
    def get_all_tasks(self, status_filter: Optional[List[TaskStatus]] = None) -> List[TaskMetadata]:
        """Get all tasks with optional status filter"""
        return self.task_manager.get_all_tasks(status_filter)
    
    def get_selected_task_uuid(self) -> Optional[str]:
        """Get UUID of currently selected task in GUI"""
        selected_items = self.gui.task_list.selectedItems()
        if not selected_items:
            return None
            
        item = selected_items[0]
        return item.data(Qt.UserRole)
    
    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return self.task_manager.get_queue_status()
    
    # Legacy compatibility methods
    def get_legacy_task_id(self, task_uuid: str) -> Optional[int]:
        """Get legacy task ID for backward compatibility"""
        for legacy_id, uuid in self._legacy_id_to_uuid.items():
            if uuid == task_uuid:
                return legacy_id
        return None
    
    def get_task_by_legacy_id(self, legacy_id: int) -> Optional[TaskMetadata]:
        """Get task by legacy ID"""
        task_uuid = self._legacy_id_to_uuid.get(legacy_id)
        if task_uuid:
            return self.task_manager.get_task(task_uuid)
        return None
    
    # Private methods
    def _convert_legacy_task(self, old_task: Dict) -> Optional[str]:
        """Convert legacy task format to enhanced task manager"""
        try:
            # Extract data from old task format
            order_number = old_task.get('order_number', '')
            folder_path = old_task.get('folder_path', '')
            local_path = old_task.get('local_path', folder_path)
            photographers = old_task.get('photographers', {})
            order_date = old_task.get('order_date')
            device_id = old_task.get('device_id', self.gui.device_id)
            
            # Check if task already exists by order number
            existing_task = self.task_manager.get_task_by_order(order_number)
            if existing_task:
                self._log_message(f"Task for order {order_number} already exists, using existing task")
                # Create legacy ID mapping for existing task
                legacy_id = old_task.get('id', self._next_legacy_id)
                self._legacy_id_to_uuid[legacy_id] = existing_task.uuid
                self._next_legacy_id = max(self._next_legacy_id, legacy_id + 1)
                return existing_task.uuid
            
            # Convert QDate to datetime if needed
            if hasattr(order_date, 'toPyDate'):
                order_date = datetime.combine(order_date.toPyDate(), datetime.min.time())
            elif isinstance(order_date, str):
                try:
                    order_date = datetime.strptime(order_date, '%Y-%m-%d')
                except:
                    order_date = datetime.now()
            elif not isinstance(order_date, datetime):
                order_date = datetime.now()
            
            # Create task in enhanced manager
            try:
                task_uuid = self.task_manager.create_task(
                    order_number=order_number,
                    folder_path=folder_path,
                    local_path=local_path,
                    photographers=photographers,
                    order_date=order_date,
                    device_id=device_id,
                    created_by=old_task.get('created_by', '')
                )
            except ValueError as ve:
                # Task might already exist, try to get it
                self._log_message(f"Task creation failed: {ve}")
                existing_task = self.task_manager.get_task_by_order(order_number)
                if existing_task:
                    task_uuid = existing_task.uuid
                else:
                    return None
            
            # Update task with additional legacy data
            task = self.task_manager.get_task(task_uuid)
            if task:
                task.progress = old_task.get('progress', 0)
                try:
                    task.status = TaskStatus(old_task.get('status', 'pending'))
                except ValueError:
                    task.status = TaskStatus.PENDING
                task.db_id = old_task.get('db_id')
                
                # Create legacy ID mapping
                legacy_id = old_task.get('id', self._next_legacy_id)
                self._legacy_id_to_uuid[legacy_id] = task_uuid
                self._next_legacy_id = max(self._next_legacy_id, legacy_id + 1)
                
                self._log_message(f"Converted task {legacy_id} -> {task_uuid[:8]} (Order: {order_number})")
            
            return task_uuid
            
        except Exception as e:
            self._log_message(f"Error converting legacy task for order {old_task.get('order_number', 'unknown')}: {e}")
            import traceback
            self._log_message(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _add_task_to_ui(self, task_uuid: str):
        """Add task to GUI list"""
        task = self.task_manager.get_task(task_uuid)
        if not task:
            return
            
        # Create list item
        item = QListWidgetItem()
        item.setData(Qt.UserRole, task_uuid)
        
        # Update item text
        self._update_task_item_text(item, task)
        
        # Add to list
        self.gui.task_list.addItem(item)
        self._task_items[task_uuid] = item
        
        # Emit signal
        self.task_added.emit(task_uuid)
    
    def _update_task_item_text(self, item: QListWidgetItem, task: TaskMetadata):
        """Update task item display text"""
        # Get legacy ID for display
        legacy_id = self.get_legacy_task_id(task.uuid) or len(self._legacy_id_to_uuid) + 1
        
        # Format status text
        status_text = task.status.value.capitalize()
        if task.status == TaskStatus.COMPLETED and task.completed_at:
            time_str = task.completed_at.strftime("%H:%M")
            status_text = f"Completed ({time_str})"
        elif task.status == TaskStatus.RUNNING and task.progress > 0:
            status_text = f"Uploading ({task.progress:.0f}%)"
        elif task.status == TaskStatus.QUEUED:
            status_text = "Queued"
        
        # Set item text
        item.setText(f"Task {legacy_id}: Order {task.order_number} - {status_text}")
    
    def _rebuild_task_list(self):
        """Rebuild the entire task list from enhanced task manager"""
        # Clear existing UI
        self.gui.task_list.clear()
        self._task_items.clear()
        
        # Get all tasks sorted by priority and creation time
        all_tasks = self.task_manager.get_all_tasks()
        
        # Add each task to UI
        for task in all_tasks:
            self._add_task_to_ui(task.uuid)
    
    def _on_task_status_changed(self, task: TaskMetadata):
        """Handle task status changes"""
        # Update UI item
        item = self._task_items.get(task.uuid)
        if item:
            self._update_task_item_text(item, task)
        
        # Update GUI state
        self._update_gui_buttons()
        
        # Emit signal
        self.task_status_changed.emit(task.uuid, task.status.value)
        
        # Handle specific status changes
        if task.status == TaskStatus.COMPLETED:
            self._handle_task_completion(task)
        elif task.status == TaskStatus.RUNNING:
            self._handle_task_started(task)
    
    def _on_task_progress_updated(self, task: TaskMetadata):
        """Handle task progress updates"""
        # Update UI item
        item = self._task_items.get(task.uuid)
        if item:
            self._update_task_item_text(item, task)
        
        # Update progress bars
        if hasattr(self.gui, 'enhanced_progress_bars'):
            legacy_id = self.get_legacy_task_id(task.uuid) or 0
            self.gui.enhanced_progress_bars.update_task_progress(
                legacy_id, task.order_number, task.progress
            )
            
            if task.current_file:
                self.gui.enhanced_progress_bars.update_file_progress(
                    task.current_file, task.progress, 
                    task.bytes_uploaded, task.total_bytes
                )
        
        # Emit signal
        self.task_progress_updated.emit(task.uuid, task.progress, task.current_file)
    
    def _handle_task_completion(self, task: TaskMetadata):
        """Handle task completion"""
        # Update GUI
        if hasattr(self.gui, 'enhanced_progress_bars'):
            self.gui.enhanced_progress_bars.clear_file_progress()
        
        # Refresh history
        if hasattr(self.gui, 'load_upload_history'):
            self.gui.load_upload_history()
        
        # Show notification
        if hasattr(self.gui, 'tray_icon'):
            self.gui.tray_icon.showMessage(
                "Upload Complete",
                f"Order {task.order_number} uploaded successfully",
                self.gui.tray_icon.Information,
                3000
            )
    
    def _handle_task_started(self, task: TaskMetadata):
        """Handle task start"""
        # Update current task in progress bars
        if hasattr(self.gui, 'enhanced_progress_bars'):
            legacy_id = self.get_legacy_task_id(task.uuid) or 0
            self.gui.enhanced_progress_bars.update_task_progress(
                legacy_id, task.order_number, task.progress
            )
    
    def _update_gui_buttons(self):
        """Update GUI button states based on current selection"""
        if hasattr(self.gui, 'on_task_selected'):
            self.gui.on_task_selected()
    
    def _log_message(self, message: str):
        """Log message to GUI"""
        if hasattr(self.gui, 'log_message'):
            self.gui.log_message(message)
        else:
            print(message)
    
    def _patch_gui_task_access(self):
        """Patch GUI methods that access tasks directly"""
        # Store original method
        if hasattr(self.gui, 'update_buttons_state'):
            original_update_buttons = self.gui.update_buttons_state
            
            def enhanced_update_buttons_state():
                """Enhanced button state update using task manager"""
                selected_items = self.gui.task_list.selectedItems()
                
                # If no task is selected, disable all task-specific buttons
                if not selected_items:
                    if hasattr(self.gui, 'modify_task_btn'):
                        self.gui.modify_task_btn.setEnabled(False)
                    if hasattr(self.gui, 'pause_btn'):
                        self.gui.pause_btn.setEnabled(False)
                    if hasattr(self.gui, 'resume_btn'):
                        self.gui.resume_btn.setEnabled(False)
                    if hasattr(self.gui, 'restart_btn'):
                        self.gui.restart_btn.setEnabled(False)
                    if hasattr(self.gui, 'cancel_btn'):
                        self.gui.cancel_btn.setEnabled(False)
                    if hasattr(self.gui, 'delete_btn'):
                        self.gui.delete_btn.setEnabled(False)
                    return
                    
                # Get the selected task UUID
                task_uuid = selected_items[0].data(Qt.UserRole)
                task = self.task_manager.get_task(task_uuid)
                
                if not task:
                    self._log_message(f"Error: Could not find task with ID {task_uuid}")
                    return
                    
                # Enable modify button for all tasks
                if hasattr(self.gui, 'modify_task_btn'):
                    self.gui.modify_task_btn.setEnabled(True)
                
                # Enable/disable buttons based on task status
                if hasattr(self.gui, 'pause_btn'):
                    self.gui.pause_btn.setEnabled(task.status == TaskStatus.RUNNING)
                if hasattr(self.gui, 'resume_btn'):
                    self.gui.resume_btn.setEnabled(task.status == TaskStatus.PAUSED)
                if hasattr(self.gui, 'restart_btn'):
                    self.gui.restart_btn.setEnabled(task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED])
                if hasattr(self.gui, 'cancel_btn'):
                    self.gui.cancel_btn.setEnabled(task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED])
                if hasattr(self.gui, 'delete_btn'):
                    self.gui.delete_btn.setEnabled(task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED])
            
            # Replace the method
            self.gui.update_buttons_state = enhanced_update_buttons_state

# Integration helper functions
def integrate_enhanced_task_manager(gui_instance):
    """
    Integrate enhanced task manager with existing GUI
    Returns the adapter instance
    """
    # Create adapter
    adapter = TaskManagerAdapter(gui_instance, gui_instance.db_manager)
    
    # Replace GUI methods with adapter methods
    _patch_gui_methods(gui_instance, adapter)
    
    # Initialize from existing tasks
    adapter.initialize_from_existing_tasks()
    
    return adapter

def _patch_gui_methods(gui, adapter):
    """Patch GUI methods to use enhanced task manager"""
    
    # Store original methods
    gui._original_add_photoshoot_task = gui.add_photoshoot_task
    gui._original_start_task = gui.start_task
    gui._original_pause_selected_task = gui.pause_selected_task
    gui._original_resume_selected_task = gui.resume_selected_task
    gui._original_cancel_selected_task = gui.cancel_selected_task
    gui._original_task_finished = gui.task_finished
    gui._original_update_task_progress = gui.update_task_progress
    
    # Patch methods
    def enhanced_add_photoshoot_task():
        """Enhanced add photoshoot task using task manager"""
        # Check if user is logged in first
        if not gui.ensure_user_logged_in():
            return
            
        # Get current storage path from database
        current_storage_path = gui.db_manager.get_device_storage_path(gui.mac_address)
        if not current_storage_path:
            from PyQt5.QtCore import QSettings
            settings = QSettings('AWSUploader', 'Settings')
            current_storage_path = settings.value('local_storage_path', None)
        
        if not current_storage_path:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(gui, "Warning", "Please configure local storage location first in the Storage tab")
            return
        
        # Update local variable
        gui.local_storage_path = current_storage_path
        
        from ui.task_editor_dialog import TaskEditorDialog
        from PyQt5.QtWidgets import QDialog
        
        dialog = TaskEditorDialog(gui.db_manager, gui.local_storage_path, parent=gui)
        if dialog.exec_() == QDialog.Accepted:
            # Get task data from dialog
            task_data = dialog.get_task_data()
            
            # Create task using enhanced manager
            task_uuid = adapter.create_new_task(
                order_number=task_data['order_number'],
                folder_path=task_data['folder_path'],
                local_path=task_data['local_path'],
                photographers=task_data['photographers'],
                order_date=task_data['order_date'],
                device_id=gui.device_id,
                created_by=gui.user_info.get('Emp_FullName', '')
            )
            
            if task_uuid:
                gui.log_message(f"Added new photoshoot task for order {task_data['order_number']}")
                gui.log_message(f"Local path: {task_data['local_path']}")
                
                # Show tray notification
                if hasattr(gui, 'tray_icon'):
                    gui.tray_icon.showMessage(
                        "📤 New Upload Started",
                        f"Started uploading Order {task_data['order_number']}",
                        gui.tray_icon.Information,
                        3000
                    )
    
    def enhanced_pause_selected_task():
        """Enhanced pause task using task manager"""
        if not gui.ensure_user_logged_in():
            return
            
        task_uuid = adapter.get_selected_task_uuid()
        if not task_uuid:
            return
            
        user_name = gui.user_info.get('Emp_FullName', 'Unknown')
        if adapter.pause_task(task_uuid, user_name):
            task = adapter.get_task_by_uuid(task_uuid)
            if task:
                gui.log_activity("task", "pause", 
                               f"Paused upload task for order {task.order_number}", 
                               user_name)
    
    def enhanced_resume_selected_task():
        """Enhanced resume task using task manager"""
        task_uuid = adapter.get_selected_task_uuid()
        if not task_uuid:
            return
            
        user_name = gui.user_info.get('Emp_FullName', 'Unknown')
        if adapter.resume_task(task_uuid, user_name):
            task = adapter.get_task_by_uuid(task_uuid)
            if task:
                gui.log_activity("task", "resume", 
                               f"Resumed upload task for order {task.order_number}", 
                               user_name)
    
    def enhanced_cancel_selected_task():
        """Enhanced cancel task using task manager"""
        if not gui.ensure_user_logged_in():
            return
            
        task_uuid = adapter.get_selected_task_uuid()
        if not task_uuid:
            return
            
        user_name = gui.user_info.get('Emp_FullName', 'Unknown')
        if adapter.cancel_task(task_uuid, user_name):
            task = adapter.get_task_by_uuid(task_uuid)
            if task:
                gui.log_activity("task", "cancel", 
                               f"Cancelled upload task for order {task.order_number}", 
                               user_name)
    
    def enhanced_task_finished(task_id):
        """Enhanced task finished handler"""
        # Convert legacy task ID to UUID if needed
        if isinstance(task_id, int):
            task = adapter.get_task_by_legacy_id(task_id)
            if task:
                adapter.complete_task(task.uuid, success=True)
        else:
            # Assume it's already a UUID
            adapter.complete_task(task_id, success=True)
    
    def enhanced_update_task_progress(task_id, current, total):
        """Enhanced task progress update"""
        # Convert legacy task ID to UUID if needed
        if isinstance(task_id, int):
            task = adapter.get_task_by_legacy_id(task_id)
            if task:
                progress = (current / max(total, 1)) * 100
                adapter.update_task_progress(
                    task.uuid, progress, "", current, total
                )
        else:
            # Assume it's already a UUID
            progress = (current / max(total, 1)) * 100
            adapter.update_task_progress(
                task_id, progress, "", current, total
            )
    
    # Apply patches
    gui.add_photoshoot_task = enhanced_add_photoshoot_task
    gui.pause_selected_task = enhanced_pause_selected_task
    gui.resume_selected_task = enhanced_resume_selected_task
    gui.cancel_selected_task = enhanced_cancel_selected_task
    gui.task_finished = enhanced_task_finished
    gui.update_task_progress = enhanced_update_task_progress
    
    # Store adapter reference
    gui.task_manager_adapter = adapter 