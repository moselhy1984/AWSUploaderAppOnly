#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Uploader Core Application
This script runs the core AWS Uploader functionality without the GUI,
avoiding all Qt-related issues while maintaining the essential functionality.
"""

import os
import sys
import time
import signal
import json
from pathlib import Path
from datetime import datetime

def log(message):
    """Print a timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def signal_handler(sig, frame):
    log("Shutting down due to user interrupt (Ctrl+C)...")
    sys.exit(0)

class AWSCoreApp:
    """AWS Uploader Core Application without GUI"""
    
    def __init__(self):
        """Initialize core components"""
        # Add current directory to path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Initialize database
        self.db = None
        self.config = None
        self.is_initialized = False
        
    def initialize(self):
        """Initialize core components"""
        try:
            # Import database manager
            from database.db_manager import DatabaseManager
            log("Initializing database...")
            self.db = DatabaseManager()
            log("Database connection established")
            
            # Import configuration manager
            from config.secure_config import SecureConfigManager
            log("Loading configuration...")
            self.config = SecureConfigManager()
            
            if self.config.config_path.exists():
                log(f"Configuration file found at {self.config.config_path}")
            else:
                log("Warning: Configuration file not found")
                
            # Check for AWS environment
            self.check_aws_environment()
            
            self.is_initialized = True
            return True
        except Exception as e:
            log(f"Initialization error: {e}")
            return False
    
    def check_aws_environment(self):
        """Check AWS credentials and environment"""
        aws_profile = os.environ.get('AWS_PROFILE', 'default')
        aws_region = os.environ.get('AWS_REGION', 'unknown')
        log(f"AWS Profile: {aws_profile}")
        log(f"AWS Region: {aws_region}")
        
        # Check for AWS credentials
        aws_creds_file = Path.home() / '.aws' / 'credentials'
        if aws_creds_file.exists():
            log("AWS credentials file found")
        else:
            log("AWS credentials file not found")
    
    def print_status(self):
        """Print application status"""
        log("\n=== AWS Uploader Core Status ===")
        log(f"Core initialized: {self.is_initialized}")
        log(f"Database connected: {self.db is not None}")
        log(f"Configuration loaded: {self.config is not None}")
        
        # Print database information if available
        if self.db:
            try:
                users = hasattr(self.db, 'get_users') and self.db.get_users() or []
                log(f"User count: {len(users) if users else 'unknown'}")
            except:
                log("Could not retrieve user information")
                
        log("===========================\n")
    
    def run(self):
        """Run the core application loop"""
        if not self.initialize():
            log("Failed to initialize core components")
            return 1
            
        self.print_status()
        log("AWS Uploader Core is running (headless mode)")
        log("Press Ctrl+C to exit")
        
        # Main application loop
        try:
            counter = 0
            while True:
                counter += 1
                if counter % 60 == 0:  # Status update every minute
                    log("AWS Uploader Core is still running")
                time.sleep(1)
        except KeyboardInterrupt:
            log("Received keyboard interrupt")
        
        # Clean shutdown
        log("Shutting down AWS Uploader Core...")
        if self.db and hasattr(self.db, 'close'):
            self.db.close()
            log("Database connection closed")
        
        log("AWS Uploader Core shutdown complete")
        return 0

def main():
    """Main entry point"""
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run core application
    app = AWSCoreApp()
    return app.run()

if __name__ == "__main__":
    sys.exit(main()) 