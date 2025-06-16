#!/usr/bin/env python3
"""
Enhanced Task Management System
Provides stable, ordered, and thread-safe task execution
"""

import os
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
import uuid

class TaskStatus(Enum):
    """Enumeration of all possible task statuses"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

class TaskPriority(Enum):
    """Task execution priority levels"""
    CRITICAL = 1    # Interrupted tasks
    HIGH = 2        # Paused tasks
    NORMAL = 3      # Pending tasks
    LOW = 4         # New tasks

@dataclass
class TaskMetadata:
    """Enhanced task metadata with stable identification"""
    # Stable identifiers
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    db_id: Optional[int] = None
    order_number: str = ""
    
    # Status and timing
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    # Progress tracking
    progress: float = 0.0
    current_file: str = ""
    files_completed: int = 0
    total_files: int = 0
    bytes_uploaded: int = 0
    total_bytes: int = 0
    
    # Task data
    folder_path: str = ""
    local_path: str = ""
    full_local_path: str = ""
    photographers: Dict = field(default_factory=dict)
    order_date: Optional[datetime] = None
    device_id: Optional[int] = None
    
    # Execution tracking
    uploader_thread: Optional[object] = None
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    
    # User tracking
    created_by: str = ""
    last_action_by: str = ""

class EnhancedTaskManager:
    """
    Enhanced task manager with proper ordering, state management, and queue handling
    """
    
    def __init__(self, db_manager, logger_callback: Optional[Callable] = None):
        self.db_manager = db_manager
        self.logger = logger_callback or print
        
        # Thread-safe data structures
        self._lock = threading.RLock()
        self._tasks: Dict[str, TaskMetadata] = {}  # UUID -> TaskMetadata
        self._execution_queue: List[str] = []  # Ordered list of UUIDs
        self._current_task_uuid: Optional[str] = None
        
        # Callbacks
        self._status_callbacks: List[Callable] = []
        self._progress_callbacks: List[Callable] = []
        
        # Configuration
        self._max_concurrent_tasks = 1  # Sequential execution
        self._auto_retry_failed = True
        
    def add_status_callback(self, callback: Callable):
        """Add callback for status changes"""
        with self._lock:
            self._status_callbacks.append(callback)
    
    def add_progress_callback(self, callback: Callable):
        """Add callback for progress updates"""
        with self._lock:
            self._progress_callbacks.append(callback)
    
    def create_task(self, order_number: str, folder_path: str, local_path: str, 
                   photographers: Dict, order_date: datetime, device_id: int,
                   created_by: str = "") -> str:
        """
        Create a new task with stable UUID
        Returns: Task UUID
        """
        with self._lock:
            # Check for duplicate order numbers
            existing = self._find_task_by_order(order_number)
            if existing and existing.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                raise ValueError(f"Task for order {order_number} already exists")
            
            task = TaskMetadata(
                order_number=order_number,
                folder_path=folder_path,
                local_path=local_path,
                photographers=photographers,
                order_date=order_date,
                device_id=device_id,
                created_by=created_by,
                priority=TaskPriority.NORMAL
            )
            
            # Build full local path
            task.full_local_path = self._build_full_path(task)
            
            # Store task
            self._tasks[task.uuid] = task
            
            # Save to database
            task.db_id = self._save_task_to_database(task)
            
            self.logger(f"Created task {task.uuid[:8]} for order {order_number}")
            self._notify_status_change(task)
            
            return task.uuid
    
    def queue_task(self, task_uuid: str, priority: Optional[TaskPriority] = None) -> bool:
        """
        Add task to execution queue with proper ordering
        """
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task:
                return False
            
            if task.status not in [TaskStatus.PENDING, TaskStatus.INTERRUPTED, TaskStatus.PAUSED]:
                self.logger(f"Cannot queue task {task_uuid[:8]} with status {task.status.value}")
                return False
            
            # Set priority if provided
            if priority:
                task.priority = priority
            
            # Remove from queue if already present
            if task_uuid in self._execution_queue:
                self._execution_queue.remove(task_uuid)
            
            # Insert based on priority and creation time
            inserted = False
            for i, queued_uuid in enumerate(self._execution_queue):
                queued_task = self._tasks[queued_uuid]
                if (task.priority.value < queued_task.priority.value or 
                    (task.priority.value == queued_task.priority.value and 
                     task.created_at < queued_task.created_at)):
                    self._execution_queue.insert(i, task_uuid)
                    inserted = True
                    break
            
            if not inserted:
                self._execution_queue.append(task_uuid)
            
            # Update status
            task.status = TaskStatus.QUEUED
            task.last_updated = datetime.now()
            self._update_task_in_database(task)
            
            self.logger(f"Queued task {task_uuid[:8]} (Order {task.order_number}) with priority {task.priority.name}")
            self._notify_status_change(task)
            
            # Try to start execution
            self._process_queue()
            
            return True
    
    def start_next_task(self) -> Optional[str]:
        """
        Start the next task in queue
        Returns: UUID of started task or None
        """
        with self._lock:
            # Check if already running a task
            if self._current_task_uuid:
                current_task = self._tasks.get(self._current_task_uuid)
                if current_task and current_task.status == TaskStatus.RUNNING:
                    return None  # Already running a task
            
            # Get next task from queue
            if not self._execution_queue:
                return None
            
            task_uuid = self._execution_queue.pop(0)
            task = self._tasks.get(task_uuid)
            
            if not task:
                # Task was deleted, try next
                return self.start_next_task()
            
            # Validate task can be started
            if not self._validate_task_for_execution(task):
                self.logger(f"Task {task_uuid[:8]} failed validation, skipping")
                return self.start_next_task()
            
            # Update task status
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            task.last_updated = datetime.now()
            self._current_task_uuid = task_uuid
            
            # Save to database
            self._update_task_in_database(task)
            
            self.logger(f"Starting task {task_uuid[:8]} (Order {task.order_number})")
            self._notify_status_change(task)
            
            return task_uuid
    
    def update_task_progress(self, task_uuid: str, progress: float, 
                           current_file: str = "", files_completed: int = 0,
                           total_files: int = 0, bytes_uploaded: int = 0,
                           total_bytes: int = 0):
        """Update task progress"""
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task:
                return
            
            task.progress = max(0, min(100, progress))
            task.current_file = current_file
            task.files_completed = files_completed
            task.total_files = total_files
            task.bytes_uploaded = bytes_uploaded
            task.total_bytes = total_bytes
            task.last_updated = datetime.now()
            
            # Notify progress callbacks
            for callback in self._progress_callbacks:
                try:
                    callback(task)
                except Exception as e:
                    self.logger(f"Progress callback error: {e}")
    
    def complete_task(self, task_uuid: str, success: bool = True, error_message: str = ""):
        """Mark task as completed or failed"""
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task:
                return
            
            # Update status
            if success:
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0
            else:
                task.status = TaskStatus.FAILED
                task.last_error = error_message
                task.retry_count += 1
            
            task.completed_at = datetime.now()
            task.last_updated = datetime.now()
            
            # Clear current task if this was it
            if self._current_task_uuid == task_uuid:
                self._current_task_uuid = None
            
            # Save to database
            self._update_task_in_database(task)
            
            self.logger(f"Task {task_uuid[:8]} {'completed' if success else 'failed'}")
            self._notify_status_change(task)
            
            # Handle retry for failed tasks
            if not success and self._auto_retry_failed and task.retry_count < task.max_retries:
                self.logger(f"Scheduling retry for task {task_uuid[:8]} (attempt {task.retry_count + 1})")
                task.status = TaskStatus.PENDING
                task.priority = TaskPriority.HIGH
                self.queue_task(task_uuid)
            else:
                # Process next task in queue
                self._process_queue()
    
    def pause_task(self, task_uuid: str, paused_by: str = "") -> bool:
        """Pause a running task"""
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task or task.status != TaskStatus.RUNNING:
                return False
            
            task.status = TaskStatus.PAUSED
            task.last_action_by = paused_by
            task.last_updated = datetime.now()
            
            # Clear current task
            if self._current_task_uuid == task_uuid:
                self._current_task_uuid = None
            
            self._update_task_in_database(task)
            self.logger(f"Paused task {task_uuid[:8]} by {paused_by}")
            self._notify_status_change(task)
            
            return True
    
    def resume_task(self, task_uuid: str, resumed_by: str = "") -> bool:
        """Resume a paused task"""
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task or task.status != TaskStatus.PAUSED:
                return False
            
            task.status = TaskStatus.PENDING
            task.priority = TaskPriority.HIGH  # High priority for resumed tasks
            task.last_action_by = resumed_by
            task.last_updated = datetime.now()
            
            self._update_task_in_database(task)
            self.logger(f"Resumed task {task_uuid[:8]} by {resumed_by}")
            
            # Queue with high priority
            return self.queue_task(task_uuid, TaskPriority.HIGH)
    
    def cancel_task(self, task_uuid: str, cancelled_by: str = "") -> bool:
        """Cancel a task"""
        with self._lock:
            task = self._tasks.get(task_uuid)
            if not task:
                return False
            
            # Remove from queue if present
            if task_uuid in self._execution_queue:
                self._execution_queue.remove(task_uuid)
            
            task.status = TaskStatus.CANCELLED
            task.last_action_by = cancelled_by
            task.completed_at = datetime.now()
            task.last_updated = datetime.now()
            
            # Clear current task if this was it
            if self._current_task_uuid == task_uuid:
                self._current_task_uuid = None
            
            self._update_task_in_database(task)
            self.logger(f"Cancelled task {task_uuid[:8]} by {cancelled_by}")
            self._notify_status_change(task)
            
            # Process next task
            self._process_queue()
            
            return True
    
    def get_task(self, task_uuid: str) -> Optional[TaskMetadata]:
        """Get task by UUID"""
        with self._lock:
            return self._tasks.get(task_uuid)
    
    def get_task_by_order(self, order_number: str) -> Optional[TaskMetadata]:
        """Get task by order number"""
        with self._lock:
            return self._find_task_by_order(order_number)
    
    def get_all_tasks(self, status_filter: Optional[List[TaskStatus]] = None) -> List[TaskMetadata]:
        """Get all tasks, optionally filtered by status"""
        with self._lock:
            tasks = list(self._tasks.values())
            if status_filter:
                tasks = [t for t in tasks if t.status in status_filter]
            
            # Sort by priority and creation time
            tasks.sort(key=lambda t: (t.priority.value, t.created_at))
            return tasks
    
    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        with self._lock:
            return {
                'queue_length': len(self._execution_queue),
                'current_task': self._current_task_uuid,
                'queue_order': self._execution_queue.copy()
            }
    
    def load_tasks_from_database(self, device_id: int) -> int:
        """Load tasks from database for a specific device"""
        with self._lock:
            try:
                # Query for incomplete and today's completed tasks
                cursor = self.db_manager.connection.cursor(dictionary=True)
                
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                
                query = """
                SELECT t.task_id, t.order_number, t.status, t.progress, 
                       t.created_at, t.completed_timestamp, t.folder_path, t.local_path,
                       t.main_photographer_id, t.assistant_photographer_id, t.video_photographer_id,
                       t.order_date, t.DeviceID, t.created_by, t.last_action_by
                FROM upload_tasks t
                WHERE t.DeviceID = %s 
                AND (
                    t.status IN ('pending', 'running', 'paused', 'interrupted') 
                    OR 
                    (t.status = 'completed' AND DATE(t.completed_timestamp) = %s)
                )
                ORDER BY 
                    CASE 
                        WHEN t.status = 'interrupted' THEN 1
                        WHEN t.status = 'paused' THEN 2
                        WHEN t.status = 'running' THEN 3
                        WHEN t.status = 'pending' THEN 4
                        WHEN t.status = 'completed' THEN 5
                        ELSE 6
                    END,
                    t.created_at ASC
                """
                
                cursor.execute(query, (device_id, today))
                results = cursor.fetchall()
                cursor.close()
                
                loaded_count = 0
                for db_task in results:
                    # Skip if already loaded
                    if self._find_task_by_order(db_task['order_number']):
                        continue
                    
                    # Create task metadata
                    task = TaskMetadata(
                        db_id=db_task['task_id'],
                        order_number=db_task['order_number'],
                        status=TaskStatus(db_task.get('status', 'pending')),
                        progress=db_task.get('progress', 0),
                        folder_path=db_task.get('folder_path', ''),
                        local_path=db_task.get('local_path', ''),
                        photographers={
                            'main': db_task.get('main_photographer_id'),
                            'assistant': db_task.get('assistant_photographer_id'),
                            'video': db_task.get('video_photographer_id')
                        },
                        order_date=db_task.get('order_date'),
                        device_id=db_task['DeviceID'],
                        created_by=db_task.get('created_by', ''),
                        last_action_by=db_task.get('last_action_by', '')
                    )
                    
                    # Set priority based on status
                    if task.status == TaskStatus.INTERRUPTED:
                        task.priority = TaskPriority.CRITICAL
                    elif task.status == TaskStatus.PAUSED:
                        task.priority = TaskPriority.HIGH
                    else:
                        task.priority = TaskPriority.NORMAL
                    
                    # Build full path
                    task.full_local_path = self._build_full_path(task)
                    
                    # Store task
                    self._tasks[task.uuid] = task
                    
                    # Queue incomplete tasks
                    if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, 
                                     TaskStatus.PAUSED, TaskStatus.INTERRUPTED]:
                        self.queue_task(task.uuid)
                    
                    loaded_count += 1
                
                self.logger(f"Loaded {loaded_count} tasks from database")
                return loaded_count
                
            except Exception as e:
                self.logger(f"Error loading tasks from database: {e}")
                return 0
    
    # Private methods
    def _process_queue(self):
        """Process the task queue"""
        if not self._current_task_uuid and self._execution_queue:
            self.start_next_task()
    
    def _find_task_by_order(self, order_number: str) -> Optional[TaskMetadata]:
        """Find task by order number"""
        for task in self._tasks.values():
            if task.order_number == order_number:
                return task
        return None
    
    def _validate_task_for_execution(self, task: TaskMetadata) -> bool:
        """Validate that a task can be executed"""
        import os
        
        # Check if local path exists
        if not os.path.exists(task.full_local_path):
            task.last_error = f"Local path does not exist: {task.full_local_path}"
            return False
        
        # Check if order number is valid
        if not task.order_number:
            task.last_error = "Order number is missing"
            return False
        
        return True
    
    def _build_full_path(self, task: TaskMetadata) -> str:
        """Build full local path for task"""
        # If local_path is already absolute, use it directly
        if task.local_path and os.path.isabs(task.local_path):
            return task.local_path
        
        # Try to get base storage path from database
        try:
            if hasattr(self.db_manager, 'get_device_storage_path'):
                # First try to get device info to get MAC address
                if hasattr(self.db_manager, 'connection') and self.db_manager.connection:
                    cursor = self.db_manager.connection.cursor(dictionary=True)
                    cursor.execute("SELECT Mac_Address FROM devices WHERE DeviceID = %s", (task.device_id,))
                    device_result = cursor.fetchone()
                    cursor.close()
                    
                    if device_result:
                        mac_address = device_result['Mac_Address']
                        base_path = self.db_manager.get_device_storage_path(mac_address)
                    else:
                        base_path = None
                else:
                    base_path = None
            else:
                base_path = None
        except Exception as e:
            self.logger(f"Error getting storage path: {e}")
            base_path = None
        
        # If we have both base path and local path, combine them
        if base_path and task.local_path:
            # Clean the local path to avoid duplication
            clean_local_path = task.local_path.lstrip('/')
            
            # Check if the local path already contains the base path
            if base_path in clean_local_path:
                return clean_local_path
            
            return os.path.join(base_path, clean_local_path)
        
        # Fallback to folder_path or local_path
        return task.folder_path or task.local_path or ""
    
    def _save_task_to_database(self, task: TaskMetadata) -> Optional[int]:
        """Save new task to database"""
        try:
            # Implementation depends on your database schema
            # This is a placeholder
            return None
        except Exception as e:
            self.logger(f"Error saving task to database: {e}")
            return None
    
    def _update_task_in_database(self, task: TaskMetadata):
        """Update existing task in database"""
        try:
            # Implementation depends on your database schema
            # This is a placeholder
            pass
        except Exception as e:
            self.logger(f"Error updating task in database: {e}")
    
    def _notify_status_change(self, task: TaskMetadata):
        """Notify all status change callbacks"""
        for callback in self._status_callbacks:
            try:
                callback(task)
            except Exception as e:
                self.logger(f"Status callback error: {e}") 