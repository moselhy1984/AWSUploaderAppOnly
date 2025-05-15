#!/usr/bin/env python3
"""
Incomplete Task Auto-Resume Script
Retrieves incomplete tasks from the database and automatically restarts them.
"""

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

def log(message):
    """Log timestamped message to console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

class TaskAutoResumer:
    """Handles retrieval and resumption of incomplete tasks"""
    
    def __init__(self):
        """Initialize task resumer"""
        self.tasks = []
        self.db = None
        
    def connect_db(self):
        """Connect to the database"""
        try:
            log("Attempting to import database manager...")
            from database.db_manager import DatabaseManager
            
            log("Creating new DatabaseManager instance...")
            self.db = DatabaseManager()
            
            log(f"DatabaseManager instance: {self.db}")
            log(f"Has connection attribute? {hasattr(self.db, 'connection')}")
            if hasattr(self.db, 'connection'):
                log(f"Connection value: {self.db.connection}")
            
            # Explicitly connect to the database
            log("Attempting database connection...")
            connect_success = self.db.connect()
            
            log(f"Connection result: {connect_success}")
            log(f"Connection value after attempt: {self.db.connection}")
            
            if connect_success:
                log(f"Has connection attribute? {hasattr(self.db, 'connection')} with value: {self.db.connection}")
                log("Successfully connected to database")
                return True
            else:
                log("Failed to connect to database")
                return False
        except Exception as e:
            log(f"Error connecting to database: {e}")
            log(f"Error details: {traceback.format_exc()}")
            return False
    
    def get_incomplete_tasks(self):
        """Retrieve incomplete tasks from the database"""
        try:
            if not self.db:
                log("No database object, attempting to connect...")
                if not self.connect_db():
                    return []
            
            # Verify connection exists and is active
            log(f"Checking database connection...")
            log(f"Does db have connection attribute? {hasattr(self.db, 'connection')}")
            if hasattr(self.db, 'connection'):
                log(f"db.connection value: {self.db.connection}")
                
            if not hasattr(self.db, 'connection') or self.db.connection is None:
                log("No connection, attempting to reconnect...")
                if not self.connect_db():
                    log("Failed to connect to database")
                    return []
            
            log("Verifying connection is valid...")
            # Quick check to ensure connection is active
            try:
                db_conn = self.db.connection
                log(f"Database connection: {db_conn}")
                
                # Check if connection is working
                if hasattr(db_conn, 'is_connected'):
                    is_connected = db_conn.is_connected()
                    log(f"Is connection active? {is_connected}")
                    if not is_connected:
                        log("Reconnecting to database...")
                        self.db.connect()
            except Exception as conn_error:
                log(f"Error verifying connection status: {conn_error}")
                return []
                
            # First check if the table exists
            log("Checking if upload_tasks table exists...")
            try:
                cursor = self.db.connection.cursor(dictionary=True)
                
                cursor.execute("""
                SELECT COUNT(*) as table_exists
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_name = 'upload_tasks'
                """, (self.db.rds_config['database'],))
                
                result = cursor.fetchone()
                if not result or result['table_exists'] == 0:
                    log("Error: upload_tasks table does not exist!")
                    cursor.close()
                    return []
                    
                # Check if we have the correct ID column
                cursor.execute("""
                SELECT COLUMN_NAME 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'upload_tasks' 
                AND COLUMN_NAME IN ('task_id', 'id')
                """, (self.db.rds_config['database'],))
                
                id_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
                
                if not id_columns:
                    log("Error: Could not find ID column in upload_tasks table")
                    cursor.close()
                    return []
                
                # Use the first ID column found (prioritize task_id if both exist)
                id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
                log(f"Using database column '{id_column}' for task identification")
                
                # Query the database for incomplete tasks
                log("Creating database query...")
                query = f"""
                SELECT {id_column} as task_id, order_number, local_path, status, folder_path, created_at 
                FROM upload_tasks 
                WHERE status != 'completed' AND status != 'cancelled'
                """
                
                # Execute the query
                log("Executing database query...")
                cursor.execute(query)
                
                log("Fetching query results...")
                results = cursor.fetchall()
                
                log("Closing cursor...")
                cursor.close()
                
                log(f"Found {len(results)} incomplete tasks")
                self.tasks = results
                return results
                
            except Exception as query_error:
                log(f"Error querying database: {query_error}")
                log(f"Error details: {traceback.format_exc()}")
                return []
                
        except Exception as e:
            log(f"Error retrieving incomplete tasks: {e}")
            log(f"Error details: {traceback.format_exc()}")
            return []
    
    def resume_tasks(self, window=None):
        """Restart incomplete tasks"""
        if not self.tasks:
            log("No tasks in list, attempting to retrieve them...")
            self.get_incomplete_tasks()
            
        if not self.tasks:
            log("No incomplete tasks to resume")
            return
            
        log(f"Resuming {len(self.tasks)} incomplete tasks...")
        
        # First try loading all tasks from database into UI
        if window and hasattr(window, 'load_tasks_from_database'):
            log("Loading all tasks from database into UI")
            try:
                window.load_tasks_from_database()
                
                # Wait a moment to allow tasks to load
                time.sleep(2)
                
                # Now try to resume all tasks in the UI
                if hasattr(window, 'auto_resume_all_tasks'):
                    log("Calling auto_resume_all_tasks to resume all loaded tasks")
                    window.auto_resume_all_tasks()
                    return
            except Exception as e:
                log(f"Error loading tasks from database: {e}")
                log(f"Error details: {traceback.format_exc()}")
                log("Falling back to individual task resumption")
        
        # If the above approach fails, try with individual tasks
        # First try auto login if needed
        if window and hasattr(window, 'ensure_user_logged_in'):
            try:
                log("Ensuring user is logged in")
                window.ensure_user_logged_in()
            except Exception as e:
                log(f"Error during login: {e}")
        
        # Load state files if possible
        state_dir = Path.home() / '.aws_uploader'
        if state_dir.exists():
            log(f"Found state directory: {state_dir}")
        
        # Fallback to individual task resumption
        for task in self.tasks:
            try:
                # Access data using dictionary keys
                task_id = task['task_id']
                order_number = task['order_number']
                local_path = task['local_path']
                folder_path = task.get('folder_path', local_path)
                status = task['status']
                
                log(f"Resuming task {task_id} for order {order_number}")
                log(f"  - Local path: {local_path}")
                log(f"  - Status: {status}")
                
                # Try using direct start_upload method first for most reliable resumption
                if window and hasattr(window, 'start_upload'):
                    log(f"Starting upload for order {order_number} from {local_path}")
                    try:
                        window.start_upload(order_number, local_path or folder_path)
                        time.sleep(1)  # Small delay between tasks
                        continue
                    except Exception as start_error:
                        log(f"Error starting upload: {start_error}")
                
                # Try auto_resume_task method as fallback
                if window and hasattr(window, 'auto_resume_task'):
                    log(f"Using auto_resume_task for task {task_id}")
                    try:
                        window.auto_resume_task(task_id)
                        time.sleep(1)  # Small delay between tasks
                        continue
                    except Exception as resume_error:
                        log(f"Error auto-resuming task: {resume_error}")
                
                # Last resort - try resume_task if available
                if window and hasattr(window, 'resume_task'):
                    log(f"Using resume_task for task {task_id}")
                    try:
                        window.resume_task(task_id, order_number, local_path)
                        time.sleep(1)  # Small delay between tasks
                    except Exception as resume_error:
                        log(f"Error resuming task: {resume_error}")
                        
            except Exception as e:
                log(f"Error handling task {task_id if 'task_id' in locals() else '?'}: {e}")
                log(f"Error details: {traceback.format_exc()}")

def auto_resume_incomplete_tasks(window=None):
    """Main function to automatically retrieve and restart incomplete tasks"""
    # Check if auto-resume for incomplete tasks is enabled
    if os.environ.get('AUTO_RESUME_INCOMPLETE', '0') != '1':
        return
        
    log("Auto-resume for incomplete tasks is enabled")
    
    # Create task resumer instance
    resumer = TaskAutoResumer()
    
    # Track if database connection succeeded
    db_connection_success = False
    
    # Use database manager from window if available
    if window and hasattr(window, 'db_manager') and window.db_manager:
        log("Using database connection from main window")
        log(f"Window's db_manager: {window.db_manager}")
        log(f"Has connection attribute? {hasattr(window.db_manager, 'connection')}")
        if hasattr(window.db_manager, 'connection'):
            log(f"Connection value: {window.db_manager.connection}")
            
        resumer.db = window.db_manager
        
        # Ensure database connection is active
        if not hasattr(resumer.db, 'connection') or resumer.db.connection is None:
            log("Reconnecting to database")
            connect_success = resumer.db.connect()
            log(f"Connection attempt result: {connect_success}")
            if connect_success:
                db_connection_success = True
    
    # Attempt explicit database connection if no connection is available
    if resumer.db is None:
        log("Starting new database connection")
        if resumer.connect_db():
            db_connection_success = True
    
    tasks = []
    
    # Retrieve incomplete tasks from database if connection succeeded
    if db_connection_success:
        log("Retrieving incomplete tasks from database...")
        tasks = resumer.get_incomplete_tasks()
    else:
        log("Database connection failed, will look for saved state files instead")
        # Check for state files as fallback
        state_dir = Path.home() / '.aws_uploader'
        if state_dir.exists():
            log(f"Checking for state files in: {state_dir}")
            state_files = list(state_dir.glob("task_state_*.json"))
            if state_files:
                log(f"Found {len(state_files)} state files")
    
    if tasks:
        log(f"Found {len(tasks)} incomplete tasks")
        # Use a timer to allow window UI to fully initialize
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(3000, lambda: resumer.resume_tasks(window))
    else:
        log("No incomplete tasks to resume")
        
        # If no tasks were found and window is available, 
        # force the window to look for state files directly
        if window and hasattr(window, 'load_tasks_from_database'):
            log("Asking window to load tasks directly...")
            try:
                # Use a timer to allow window UI to fully initialize
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(3000, window.load_tasks_from_database)
                
                # Schedule auto-resume after loading
                if hasattr(window, 'auto_resume_all_tasks'):
                    QTimer.singleShot(6000, window.auto_resume_all_tasks)
            except Exception as e:
                log(f"Error asking window to load tasks: {e}")
                log(f"Error details: {traceback.format_exc()}")

if __name__ == "__main__":
    auto_resume_incomplete_tasks()
