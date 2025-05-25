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
        else:
            if not config_enc_exists:
                print("Warning: config.enc file not found")
            if not key_file_exists:
                print("Warning: encryption_key.txt file not found")
            QMessageBox.critical(None, "Configuration Error", 
                               "Required configuration files are missing.\n\n"
                               "Please ensure both config.enc and encryption_key.txt exist in the application directory.")
            return 1
        
        # Initialize database manager
        print("Initializing database manager...")
        db_manager = DatabaseManager()
        if not db_manager.connect():
            print("Database connection failed - continuing without database")
            # Still continue without database
        
        # Check for auto-resume flags
        auto_resume = os.environ.get('NO_AUTO_RESUME', '0') != '1' and os.environ.get('AUTO_RESUME', '1') == '1'
        skip_state_load = os.environ.get('SKIP_STATE_LOAD', '0') == '1'
        
        # Check if we should load all tasks, not just today's
        load_all_tasks = os.environ.get('LOAD_ALL_TASKS', '0') == '1'
        
        # تعطيل تسجيل الدخول التلقائي
        no_auto_login = os.environ.get('NO_AUTO_LOGIN', '0') == '1'
        
        print(f"Application configuration:")
        print(f"- Auto-resume: {auto_resume}")
        print(f"- Skip state load: {skip_state_load}")
        print(f"- Load all tasks: {load_all_tasks}")
        print(f"- Disable auto-login: {no_auto_login}")
        
        print("Loading secure configuration...")
        # Load AWS config
        try:
            config_manager = SecureConfigManager()
            aws_config = config_manager.decrypt_config()
        except ValueError as e:
            print(f"Error loading configuration: {str(e)}")
            QMessageBox.critical(None, "Configuration Error", 
                               f"Failed to load AWS configuration:\n\n{str(e)}\n\n"
                               "Please ensure your configuration files are valid and contain the required AWS credentials.")
            return 1
        
        # Create default user info
        result = {
            'Emp_FullName': 'Guest',
            'is_logged_in': False,
            'username': 'guest'
        }
        
        # Initialize the main window
        print("Initializing main application window...")
        window = S3UploaderGUI(aws_config, db_manager, result, skip_state_load=skip_state_load, 
                              auto_resume=auto_resume, safe_mode=False, 
                              load_all_tasks=load_all_tasks, no_auto_login=no_auto_login)
        window.show()
        
        # Enable memory manager if available
        if os.environ.get('USE_MEMORY_MANAGER', '0') == '1':
            try:
                print("Initializing memory manager...")
                # from memory_manager import setup_memory_management
                # memory_manager = setup_memory_management(app)
                # print("Memory manager initialized")
                pass
            except ImportError:
                print("Memory manager module not found, continuing without memory optimization")
            except Exception as mem_err:
                print(f"Error initializing memory manager: {str(mem_err)}")
        
        return app.exec_()
        
    except Exception as e:
        print(f"Error starting application: {str(e)}")
        import traceback
        print(traceback.format_exc())
        QMessageBox.critical(None, "Application Error", 
                           f"An unexpected error occurred:\n\n{str(e)}\n\n"
                           "Please check the application logs for more details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())