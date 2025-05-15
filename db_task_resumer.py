#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database Task Resumer for AWS Uploader

This module provides functions to find and resume tasks from both the database
and state files when the application starts. It handles database connection 
failures gracefully and provides fallback mechanisms.
"""

import os
import sys
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

def log(message):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [DB RESUMER] {message}")
    sys.stdout.flush()

class DatabaseTaskResumer:
    """Handles database connection and task resumption"""
    
    def __init__(self, app_window=None):
        """
        Initialize the database task resumer
        
        Args:
            app_window: Reference to the main application window (optional)
        """
        self.window = app_window
        self.db = None
        self.connection_success = False
        self.tasks = []
        self.state_files = []
        
    def setup_database(self):
        """Set up database connection"""
        try:
            log("Setting up database connection...")
            
            # Try to import database manager
            try:
                from database.db_manager import DatabaseManager
                log("Successfully imported DatabaseManager")
            except ImportError:
                log("Error: Could not import DatabaseManager")
                return False
                
            # Create database manager
            try:
                self.db = DatabaseManager()
                log(f"Created DatabaseManager: {self.db}")
            except Exception as e:
                log(f"Error creating DatabaseManager: {e}")
                return False
                
            # Connect to database
            try:
                log("Connecting to database...")
                self.connection_success = self.db.connect()
                log(f"Database connection result: {self.connection_success}")
                
                if not self.connection_success:
                    log("Database connection failed")
                    return False
            except Exception as e:
                log(f"Error connecting to database: {e}")
                return False
                
            return self.connection_success
            
        except Exception as e:
            log(f"Error setting up database: {e}")
            log(traceback.format_exc())
            return False
    
    def find_incomplete_database_tasks(self):
        """Find incomplete tasks in the database"""
        if not self.db or not self.connection_success:
            log("No active database connection, cannot find tasks")
            return []
            
        try:
            log("Looking for incomplete tasks in database...")
            
            # Get a cursor for database operations
            cursor = self.db.connection.cursor(dictionary=True)
            
            # Check which ID column to use
            cursor.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'upload_tasks' 
            AND COLUMN_NAME IN ('task_id', 'id')
            """, (self.db.rds_config['database'],))
            
            columns = cursor.fetchall()
            if not columns:
                log("Error: Could not find ID column in upload_tasks table")
                cursor.close()
                return []
                
            # Use the first ID column found (prioritize task_id if available)
            id_columns = [col['COLUMN_NAME'] for col in columns]
            id_column = 'task_id' if 'task_id' in id_columns else id_columns[0]
            log(f"Using '{id_column}' as task ID column")
            
            # Query for incomplete tasks
            query = f"""
            SELECT {id_column} as task_id, order_number, local_path, status, 
                   folder_path, created_at, modified_at
            FROM upload_tasks 
            WHERE status != 'completed' AND status != 'cancelled'
            """
            
            # Execute query
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            
            log(f"Found {len(results)} incomplete tasks in database")
            
            # Store tasks and return them
            self.tasks = results
            return results
            
        except Exception as e:
            log(f"Error finding incomplete tasks in database: {e}")
            log(traceback.format_exc())
            return []
    
    def find_state_files(self):
        """Find state files for tasks"""
        try:
            log("Looking for saved state files...")
            state_dir = Path.home() / '.aws_uploader'
            
            if not state_dir.exists():
                log(f"State directory {state_dir} does not exist")
                return []
                
            # Find all state files
            state_files = list(state_dir.glob("task_state_*.json"))
            log(f"Found {len(state_files)} state files in {state_dir}")
            
            self.state_files = state_files
            return state_files
            
        except Exception as e:
            log(f"Error finding state files: {e}")
            log(traceback.format_exc())
            return []
    
    def parse_state_file(self, state_file):
        """Parse a state file into a task object"""
        try:
            # Extract order number from filename
            filename = state_file.name
            order_match = filename.split("task_state_")[-1].split(".json")[0]
            order_number = order_match
            
            # Parse the JSON file
            with open(state_file, 'r') as f:
                state = json.load(f)
                
            # Create a task object from state file
            task = {
                'task_id': int(time.time()),  # Use timestamp as ID
                'order_number': order_number,
                'local_path': state.get('local_path', ''),
                'folder_path': state.get('folder_path', ''),
                'status': 'paused',  # Assume paused
                'from_state_file': True,
                'state_file': str(state_file),
                'created_at': state.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }
            
            # Extract progress information if available
            if 'current_file_index' in state and 'total_files' in state:
                task['progress'] = (state['current_file_index'] / max(state['total_files'], 1)) * 100
                task['uploaded_files'] = state['current_file_index']
                task['total_files'] = state['total_files']
            
            return task
            
        except Exception as e:
            log(f"Error parsing state file {state_file}: {e}")
            log(traceback.format_exc())
            return None
    
    def get_tasks_from_state_files(self):
        """Get tasks from state files"""
        if not self.state_files:
            self.find_state_files()
            
        if not self.state_files:
            return []
            
        log(f"Parsing {len(self.state_files)} state files...")
        tasks = []
        
        for state_file in self.state_files:
            task = self.parse_state_file(state_file)
            if task:
                tasks.append(task)
                
        log(f"Created {len(tasks)} tasks from state files")
        return tasks
    
    def get_all_incomplete_tasks(self):
        """Get all incomplete tasks from both database and state files"""
        # Try database first
        db_tasks = self.find_incomplete_database_tasks()
        
        # Also get tasks from state files
        state_tasks = self.get_tasks_from_state_files()
        
        # Combine tasks, avoiding duplicates
        all_tasks = list(db_tasks)
        
        # Only add state tasks if they don't match an order number in the database
        if db_tasks and state_tasks:
            db_order_numbers = [t['order_number'] for t in db_tasks]
            for task in state_tasks:
                if task['order_number'] not in db_order_numbers:
                    all_tasks.append(task)
                    log(f"Adding task from state file: Order {task['order_number']}")
        else:
            # If no database tasks, use all state file tasks
            all_tasks.extend(state_tasks)
        
        return all_tasks
    
    def resume_tasks_in_window(self):
        """Resume tasks in the application window"""
        if not self.window:
            log("No window reference provided, cannot resume tasks")
            return False
            
        # Get all incomplete tasks
        tasks = self.get_all_incomplete_tasks()
        
        if not tasks:
            log("No incomplete tasks found to resume")
            return False
            
        log(f"Found {len(tasks)} tasks to resume")
        
        # Make sure user is logged in
        if hasattr(self.window, 'ensure_user_logged_in'):
            try:
                log("Ensuring user is logged in...")
                self.window.ensure_user_logged_in()
            except Exception as e:
                log(f"Error during login: {e}")
                
        # Try to use auto_resume_all_tasks if available
        if hasattr(self.window, 'auto_resume_all_tasks'):
            log("Using auto_resume_all_tasks method")
            try:
                # Load tasks from database first to make sure they're in the UI
                if hasattr(self.window, 'load_tasks_from_database'):
                    self.window.load_tasks_from_database()
                    
                # Small delay to let UI update
                time.sleep(1)
                
                # Resume all tasks
                self.window.auto_resume_all_tasks()
                log("Successfully called auto_resume_all_tasks")
                return True
            except Exception as e:
                log(f"Error using auto_resume_all_tasks: {e}")
                log(traceback.format_exc())
                
        # Fall back to manual task resumption
        log("Falling back to individual task resumption")
        success_count = 0
        
        for task in tasks:
            try:
                task_id = task['task_id']
                order_number = task['order_number']
                local_path = task.get('local_path', '')
                folder_path = task.get('folder_path', local_path)
                
                log(f"Resuming task {task_id} for order {order_number}")
                
                # Try using start_upload method
                if hasattr(self.window, 'start_upload'):
                    try:
                        self.window.start_upload(order_number, local_path or folder_path)
                        success_count += 1
                        time.sleep(1)  # Small delay between tasks
                        continue
                    except Exception as e:
                        log(f"Error using start_upload: {e}")
                
                # Try using auto_resume_task method
                if hasattr(self.window, 'auto_resume_task'):
                    try:
                        self.window.auto_resume_task(task_id)
                        success_count += 1
                        time.sleep(1)  # Small delay between tasks
                        continue
                    except Exception as e:
                        log(f"Error using auto_resume_task: {e}")
                
                # As a last resort, try resume_task
                if hasattr(self.window, 'resume_task'):
                    try:
                        self.window.resume_task(task_id, order_number, local_path or folder_path)
                        success_count += 1
                        time.sleep(1)  # Small delay between tasks
                        continue
                    except Exception as e:
                        log(f"Error using resume_task: {e}")
            
            except Exception as e:
                log(f"Error resuming task: {e}")
                log(traceback.format_exc())
        
        log(f"Successfully resumed {success_count} out of {len(tasks)} tasks")
        return success_count > 0

def resume_tasks(app_window=None):
    """Main function to resume tasks"""
    # Check if this feature is enabled
    if os.environ.get('AUTO_RESUME_INCOMPLETE', '0') != '1':
        log("Auto-resume feature is disabled")
        return False
    
    log("Starting task resumption process")
    
    # Create resumer instance
    resumer = DatabaseTaskResumer(app_window)
    
    # Set up database connection
    db_setup_success = resumer.setup_database()
    log(f"Database setup success: {db_setup_success}")
    
    # If we have an app window, use Qt timer to delay task resumption
    if app_window:
        try:
            from PyQt5.QtCore import QTimer
            
            # Delay task resumption to allow UI to initialize
            log("Scheduling task resumption with 3-second delay...")
            QTimer.singleShot(3000, resumer.resume_tasks_in_window)
            return True
        except Exception as e:
            log(f"Error scheduling task resumption: {e}")
            # Fall back to immediate resumption
            return resumer.resume_tasks_in_window()
    else:
        # No app window, just process tasks
        return resumer.get_all_incomplete_tasks()

if __name__ == "__main__":
    # When run directly, just find tasks
    log("Running in standalone mode")
    resumer = DatabaseTaskResumer()
    resumer.setup_database()
    tasks = resumer.get_all_incomplete_tasks()
    
    if tasks:
        log(f"Found {len(tasks)} incomplete tasks:")
        for i, task in enumerate(tasks):
            log(f"Task {i+1}: Order {task['order_number']} - Status: {task['status']}")
    else:
        log("No incomplete tasks found") 