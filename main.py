#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import getmac
from PyQt5.QtWidgets import QApplication, QMessageBox, QDialog
from config.secure_config import SecureConfigManager
from database.db_manager import DatabaseManager
from ui.login_dialog import LoginDialog
from ui.uploader_gui import S3UploaderGUI
from pathlib import Path
from datetime import datetime

def main():
    """Main entry point for the application"""
    print("Starting AWS Uploader application...")
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    try:
        # Check if encryption files exist
        config_enc_exists = Path("config.enc").exists()
        key_file_exists = Path("encryption_key.txt").exists()
        
        if config_enc_exists and key_file_exists:
            print("Encryption files found: config.enc and encryption_key.txt")
            # Force safe mode when encryption files are present
            os.environ['SAFE_MODE'] = '1'
            print("Safe mode automatically enabled due to encryption files")
        else:
            if not config_enc_exists:
                print("Warning: config.enc file not found")
            if not key_file_exists:
                print("Warning: encryption_key.txt file not found")
        
        # Check if we're in safe mode
        safe_mode = os.environ.get('SAFE_MODE', '0') == '1'
        if safe_mode:
            print("Running in safe mode: some advanced features will be disabled")
        
        # Initialize database manager
        print("Initializing database manager...")
        db_manager = DatabaseManager()
        if not db_manager.connect():
            print("Database connection failed - continuing without database")
            # Still continue without database
        
        # Check for auto-resume flags
        auto_resume = os.environ.get('NO_AUTO_RESUME', '0') != '1'
        skip_state_load = os.environ.get('SKIP_STATE_LOAD', '0') == '1'
        
        # Check if we should load all tasks, not just today's
        load_all_tasks = os.environ.get('LOAD_ALL_TASKS', '0') == '1'
        
        print(f"Application configuration:")
        print(f"- Auto-resume: {auto_resume}")
        print(f"- Skip state load: {skip_state_load}")
        print(f"- Safe mode: {safe_mode}")
        print(f"- Load all tasks: {load_all_tasks}")
        
        print("Loading secure configuration...")
        # Load AWS config
        config_manager = SecureConfigManager()
        aws_config = config_manager.decrypt_config()
        
        # Create default user info
        result = {
            'Emp_FullName': 'Guest',
            'is_logged_in': False,
            'username': 'guest'
        }
        
        # Initialize the main window
        print("Initializing main application window...")
        window = S3UploaderGUI(aws_config, db_manager, result, skip_state_load=skip_state_load, auto_resume=auto_resume, safe_mode=safe_mode, load_all_tasks=load_all_tasks)
        window.show()
        
        # Enable memory manager if available
        if os.environ.get('USE_MEMORY_MANAGER', '0') == '1':
            try:
                print("Initializing memory manager...")
                from memory_manager import setup_memory_management
                memory_manager = setup_memory_management(app)
                print("Memory manager initialized")
            except ImportError:
                print("Memory manager module not found, continuing without memory optimization")
            except Exception as mem_err:
                print(f"Error initializing memory manager: {str(mem_err)}")
        
        # Auto Resume Incomplete Tasks
        if os.environ.get('AUTO_RESUME_INCOMPLETE', '0') == '1':
            print("[{}] Auto-resume for incomplete tasks is enabled".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            # Call enhanced database task resumer
            try:
                # First try the enhanced resumer with better fallback mechanisms
                from db_task_resumer import resume_tasks
                print("[{}] Using enhanced database task resumption...".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                resume_tasks(window)
            except ImportError:
                # Fall back to original implementation if available
                try:
                    from task_auto_resume import auto_resume_incomplete_tasks
                    print("[{}] Using original task auto-resume implementation...".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    auto_resume_incomplete_tasks(window)
                except ImportError:
                    print("[{}] No task resumption module found".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            except Exception as e:
                print("[{}] Error while resuming incomplete tasks: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(e)))
                # Print the traceback for debugging
                import traceback
                print(traceback.format_exc())
        
        print("[{}] Application started successfully".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return app.exec_()
    except Exception as e:
        print(f"Error in main application: {e}")
        # Print the traceback for debugging
        import traceback
        print(traceback.format_exc())
        
        # Show error dialog
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("Application Error")
        error_dialog.setText("An unexpected error occurred while starting the application.")
        error_dialog.setDetailedText(f"Error details: {str(e)}\n\n{traceback.format_exc()}")
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec_()
        return 1

if __name__ == '__main__':
    main()