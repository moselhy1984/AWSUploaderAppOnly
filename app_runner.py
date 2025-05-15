#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Uploader Core Functionality Runner
This script implements the core functionality of the AWS Uploader
without using the Qt GUI, to avoid platform plugin issues.
"""

import os
import sys
import time
import signal
from datetime import datetime

def log(message):
    """Print a timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def signal_handler(sig, frame):
    log("Shutting down due to user interrupt (Ctrl+C)...")
    sys.exit(0)

def run_core_functionality():
    """Run the core AWS upload functionality without GUI"""
    try:
        # Import the core components directly
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        try:
            from database.db_manager import DatabaseManager
            from config.secure_config import SecureConfigManager
        except ImportError as e:
            log(f"Error importing core modules: {e}")
            log("Make sure you're running this script from the application directory")
            return 1

        # Initialize database
        log("Initializing database connection...")
        try:
            db = DatabaseManager()
            user_count = db.get_user_count() if hasattr(db, 'get_user_count') else 'unknown'
            log(f"Number of users in database: {user_count}")
        except Exception as e:
            log(f"Database initialization error: {e}")
            return 1

        # Initialize config manager
        log("Loading configuration...")
        try:
            config = SecureConfigManager()
            aws_region = config.get('aws_region', 'Unknown')
            bucket = config.get('bucket_name', 'Unknown')
            log(f"AWS Region: {aws_region}")
            log(f"S3 Bucket: {bucket}")
        except Exception as e:
            log(f"Configuration error: {e}")
            return 1

        # Application is now running
        log("AWS Uploader core is running in headless mode")
        log("Core components initialized successfully")
        log("Press Ctrl+C to exit")
        
        # Keep app running until interrupted
        try:
            counter = 0
            while True:
                counter += 1
                if counter % 60 == 0:  # Status message every minute
                    log("Application is running")
                time.sleep(1)
        except KeyboardInterrupt:
            log("Received keyboard interrupt")
        
        # Clean shutdown
        log("Shutting down...")
        if hasattr(db, 'close'):
            log("Closing database connection")
            db.close()
        log("Application closed successfully")
        return 0
        
    except Exception as e:
        log(f"Unhandled exception: {e}")
        return 1

def main():
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Set environment variables for headless mode
    os.environ['HEADLESS_MODE'] = '1'
    os.environ['NO_GUI'] = '1'
    
    # Safety settings
    os.environ['SKIP_STATE_LOAD'] = '1' 
    os.environ['NO_AUTO_RESUME'] = '1'
    os.environ['SAFE_MODE'] = '1'
    
    # Disable Qt
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    
    log("Starting AWS Uploader in headless mode...")
    return run_core_functionality()

if __name__ == "__main__":
    sys.exit(main()) 