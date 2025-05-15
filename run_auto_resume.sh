#!/bin/bash
# Auto-Resume Script - Fixes memory issues while maintaining task recovery functionality
# Automatically restores incomplete tasks from the database

echo "=================================================="
echo "  AWS UPLOADER WITH AUTO-RESUME FOR INCOMPLETE TASKS"
echo "=================================================="
echo "Setting up environment variables to prevent Qt conflicts..."
echo ""

# Activate virtual environment
source aws_app_env/bin/activate

# Determine PyQt5 paths
PYQT_PATH=$(python -c "import site, os; print(os.path.join(site.getsitepackages()[0], 'PyQt5', 'Qt5'))")
PYQT_PLUGINS="${PYQT_PATH}/plugins"
BREW_QT="/opt/homebrew/Cellar/qt@5"

# Completely disable Homebrew Qt libraries
# This prevents the system from trying to load Qt libraries from Homebrew during execution
if [ -d "$BREW_QT" ]; then
    echo "Detected Homebrew Qt libraries at: $BREW_QT"
    echo "Temporarily disabling these libraries during application execution..."
    # Use QT_PLUGIN_PATH for PyQt5 libraries only
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    # Explicitly specify platform plugin path
    export QT_QPA_PLATFORM_PLUGIN_PATH="${PYQT_PLUGINS}/platforms"
    # Explicitly specify cocoa platform
    export QT_QPA_PLATFORM=cocoa
    # Reorder library search paths
    export PATH="${PYQT_PATH}/bin:$PATH"
    export DYLD_FRAMEWORK_PATH="${PYQT_PATH}/lib"
    export DYLD_LIBRARY_PATH="${PYQT_PATH}/lib"
    # Disable Qt plugin debugging
    export QT_DEBUG_PLUGINS=0
else
    echo "No Homebrew Qt libraries detected"
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    export QT_QPA_PLATFORM=cocoa
fi

echo "Set Qt plugin path: $QT_PLUGIN_PATH"
echo "Set Qt platform: cocoa"
echo ""

# Configure application behavior
# Disable the automatic task resume mechanism that uses saved states 
# (this helps avoid memory issues)
export NO_AUTO_RESUME=1

# Allow the application to load tasks from the database but skip automatic state loading
export SKIP_STATE_LOAD=1

# Force loading all tasks from database, not just today's tasks
export LOAD_ALL_TASKS=1

# Enable auto-resume mode for incomplete tasks from the database
export AUTO_RESUME_INCOMPLETE=1

# Allow automatic login for resuming tasks without user interaction
export AUTO_LOGIN=1

echo "Enabled auto-resume for incomplete tasks with these settings:"
echo "- Disabled standard auto-resume mechanism (to avoid memory issues)"
echo "- Enabled loading of ALL tasks from database (not just today's)"
echo "- Enabled automatic recovery of incomplete tasks"
echo "- Enabled automatic login to resume tasks"
echo "- Will skip files already uploaded to Amazon S3"
echo ""

# Update the Python script if needed
if [ ! -f task_auto_resume.py ]; then
    echo "Auto-resume script not found. Creating it..."
    
    # Create the script
    cat > task_auto_resume.py << 'EOF'
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
    
    # Attempt explicit database connection if no connection is available
    if resumer.db is None:
        log("Starting new database connection")
        resumer.connect_db()
    
    # Retrieve incomplete tasks
    log("Retrieving incomplete tasks...")
    tasks = resumer.get_incomplete_tasks()
    
    if tasks:
        log(f"Found {len(tasks)} incomplete tasks")
        # Use a timer to allow window UI to fully initialize
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(3000, lambda: resumer.resume_tasks(window))
    else:
        log("No incomplete tasks to resume")

if __name__ == "__main__":
    auto_resume_incomplete_tasks()
EOF

    chmod +x task_auto_resume.py
    echo "Created task auto-resume script"
fi

# Add support for auto-resume to main.py if not already present
if ! grep -q "AUTO_RESUME_INCOMPLETE" main.py; then
    echo "Adding support for incomplete task auto-resume to the application..."
    
    # Check for a backup
    if [ ! -f main.py.bak ]; then
        cp main.py main.py.bak
        echo "Created backup of main.py"
    fi
    
    # Add the code to call the task auto-resume script at application startup
    # Find an appropriate place to add the code after the main window creation
    AUTO_RESUME_CODE="        # Auto Resume Incomplete Tasks\n        if os.environ.get('AUTO_RESUME_INCOMPLETE', '0') == '1':\n            print(\"[{}] Auto-resume for incomplete tasks is enabled\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")))\n            # Call task auto-resume script\n            try:\n                from task_auto_resume import auto_resume_incomplete_tasks\n                print(\"[{}] Searching for incomplete tasks...\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")))\n                # Pass window object for task resumption\n                auto_resume_incomplete_tasks(window)\n            except Exception as e:\n                print(\"[{}] Error while resuming incomplete tasks: {}\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\"), str(e)))\n"
    
    if grep -q "window.show()" main.py; then
        # Use sed to add the code after the window.show() line
        if [ "$(uname)" == "Darwin" ]; then
            # macOS
            sed -i '' -e "s/window.show()/window.show()\n$AUTO_RESUME_CODE/" main.py
        else
            # Linux
            sed -i "s/window.show()/window.show()\n$AUTO_RESUME_CODE/" main.py
        fi
        echo "Added support for incomplete task auto-resume to the application"
    else
        echo "Warning: Could not find an appropriate place to add auto-resume for incomplete tasks"
        echo "The application will run without this feature"
    fi
else
    echo "Support for incomplete task auto-resume already exists in the application"
fi

# Modify main.py to check for LOAD_ALL_TASKS environment variable if not already present
if ! grep -q "LOAD_ALL_TASKS" main.py; then
    echo "Adding support for loading all tasks from database..."
    
    # Check for a backup
    if [ ! -f main.py.bak ]; then
        cp main.py main.py.bak
        echo "Created backup of main.py"
    fi
    
    # Replace the window initialization line to include load_all_tasks parameter
    WINDOW_INIT_PATTERN="window = S3UploaderGUI(aws_config, db_manager, result, skip_state_load=skip_state_load, auto_resume=auto_resume, safe_mode=safe_mode)"
    WINDOW_INIT_REPLACEMENT="# Check if we should load all tasks, not just today's\n            load_all_tasks = os.environ.get('LOAD_ALL_TASKS', '0') == '1'\n            window = S3UploaderGUI(aws_config, db_manager, result, skip_state_load=skip_state_load, auto_resume=auto_resume, safe_mode=safe_mode, load_all_tasks=load_all_tasks)"
    
    if grep -q "$WINDOW_INIT_PATTERN" main.py; then
        if [ "$(uname)" == "Darwin" ]; then
            # macOS
            sed -i '' -e "s/$WINDOW_INIT_PATTERN/$WINDOW_INIT_REPLACEMENT/" main.py
        else
            # Linux
            sed -i "s/$WINDOW_INIT_PATTERN/$WINDOW_INIT_REPLACEMENT/" main.py
        fi
        echo "Added support for loading all tasks from database"
    else
        echo "Warning: Could not find window initialization to add load_all_tasks parameter"
        echo "The application will only load today's tasks by default"
    fi
fi

echo ""
echo "Starting application with auto-resume for ALL incomplete tasks..."
echo "=================================================="

# Run the application
python main.py 2>&1 | tee auto_resume_log.txt

# If the application exits with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "=================================================="
    echo "Application exited with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
    echo "To run without auto-resume, use ./run_direct.sh"
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "Application closed successfully"
    echo "=================================================="
fi

exit $EXIT_CODE 