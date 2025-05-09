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

def main():
    """Main entry point for the application"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        if not db_manager.connect():
            QMessageBox.critical(
                None, 
                "Database Error", 
                "Failed to connect to the database. Check your internet connection and try again."
            )
            return
        
        # Initialize secure config manager
        config_manager = SecureConfigManager()
        
        # Check if config file exists
        if not config_manager.config_path.exists():
            QMessageBox.critical(
                None, 
                "Configuration Error", 
                "Configuration file not found!\n\nMake sure 'config.enc' is in the same directory as the application."
            )
            return
        
        # Check if encryption key file exists
        if not config_manager.key_path.exists():
            QMessageBox.critical(
                None, 
                "Key Error", 
                "Encryption key file not found!\n\nMake sure 'encryption_key.txt' is in the same directory as the application."
            )
            return
        
        try:
            # Decrypt configuration
            aws_config = config_manager.decrypt_config()
            
            # Login
            login_dialog = LoginDialog()
            if login_dialog.exec_() != QDialog.Accepted:
                return
                
            username, password = login_dialog.get_credentials()
            mac_address = getmac.get_mac_address()
            
            success, result = db_manager.verify_user(username, password, mac_address)
            if not success:
                QMessageBox.critical(None, "Login Error", result)
                return
                
            # Start main application
            window = S3UploaderGUI(aws_config, db_manager, result)
            window.show()
            window.log_message("Application started successfully")
            window.log_message(f"Connected to bucket: {aws_config['bucket']}")
            
            return app.exec_()
            
        except ValueError as e:
            QMessageBox.critical(None, "Configuration Error", str(e))
            return
            
    except Exception as e:
        QMessageBox.critical(None, "Application Error", f"An error occurred: {str(e)}")
        return

if __name__ == '__main__':
    main()