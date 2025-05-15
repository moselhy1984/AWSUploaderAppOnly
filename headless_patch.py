#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Headless Mode Patch for AWS Uploader
This script patches the main.py file to support headless mode operation.
"""

import os
import sys
import shutil
import re

def backup_main_file():
    """Create a backup of the main.py file"""
    if os.path.exists('main.py'):
        shutil.copy('main.py', 'main.py.bak')
        print("Created backup of main.py as main.py.bak")
        return True
    return False

def restore_main_file():
    """Restore the main.py file from backup"""
    if os.path.exists('main.py.bak'):
        shutil.copy('main.py.bak', 'main.py')
        print("Restored main.py from backup")
        return True
    return False

def patch_for_headless():
    """Patch the main.py file to run in headless mode"""
    if not os.path.exists('main.py'):
        print("Error: main.py not found")
        return False
    
    # Create backup if it doesn't exist
    if not os.path.exists('main.py.bak'):
        backup_main_file()
    
    with open('main.py', 'r') as f:
        content = f.read()
    
    # Add headless mode support at the top
    headless_imports = """
# Headless mode imports
import os
import time
import threading
from datetime import datetime
"""
    
    # Replace the main function with a headless-compatible version
    main_pattern = r"def main\(\):[^}]*?app = QApplication\(sys\.argv\)[^}]*?app\.exec_\(\)"
    headless_main = """
def main():
    \"\"\"Main entry point for the application\"\"\"
    # Check for headless mode
    headless_mode = os.environ.get('HEADLESS_MODE', '0') == '1'
    no_gui = os.environ.get('NO_GUI', '0') == '1'
    
    if headless_mode or no_gui:
        print("[{}] Running in headless mode (no GUI)".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        # Check if we're in safe mode
        safe_mode = os.environ.get('SAFE_MODE', '0') == '1'
        if safe_mode:
            print("[{}] Running in safe mode: some advanced features are disabled".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
        # Skip loading previous state if requested
        skip_state_load = os.environ.get('SKIP_STATE_LOAD', '0') == '1'
        if skip_state_load:
            print("[{}] Running application with skip state load enabled".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
        # Initialize core components without GUI
        try:
            from utils.background_uploader import BackgroundUploader
            from utils.database_manager import DatabaseManager
            
            print("[{}] Initializing core components...".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db = DatabaseManager()
            uploader = BackgroundUploader()
            
            print("[{}] Application initialized in headless mode".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            print("[{}] Connected to bucket: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                                                    uploader.bucket_name))
            
            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("[{}] Shutting down...".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            print("[{}] Application stopped".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            return 0
            
        except Exception as e:
            print("[{}] Error in headless mode: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(e)))
            return 1
    else:
        # Regular GUI mode
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        
        try:
            # Check if we're in safe mode
            safe_mode = os.environ.get('SAFE_MODE', '0') == '1'
            if safe_mode:
                print("Running in safe mode: some advanced features will be disabled")
                
                # Create a warning dialog to inform the user
                dialog = QMessageBox()
                dialog.setIcon(QMessageBox.Warning)
                dialog.setText("The application is running in safe mode due to repeated crashes.")
                dialog.setInformativeText("Some advanced features are disabled, including automatic task resumption.\\nYou can run tasks manually and performance will be more closely monitored.")
                dialog.setWindowTitle("Safe Mode Enabled")
                dialog.setStandardButtons(QMessageBox.Ok)
                dialog.exec_()
                
            # Skip auto-resume if requested
            no_auto_resume = os.environ.get('NO_AUTO_RESUME', '0') == '1'
            if no_auto_resume:
                print("Auto-resume disabled in safe mode")
                
            # Skip loading previous state if requested
            skip_state_load = os.environ.get('SKIP_STATE_LOAD', '0') == '1'
            if skip_state_load:
                print("Skipping previous shutdown check due to state loading being disabled")
                        
            window = MainWindow(safe_mode=safe_mode, skip_state_load=skip_state_load, 
                                no_auto_resume=no_auto_resume)
            window.show()
            return app.exec_()
            
        except Exception as e:
            print("Error:", str(e))
            # Show error dialog
            error_dialog = QMessageBox()
            error_dialog.setIcon(QMessageBox.Critical)
            error_dialog.setText("Application Error")
            error_dialog.setInformativeText(str(e))
            error_dialog.setWindowTitle("Error")
            error_dialog.setStandardButtons(QMessageBox.Ok)
            error_dialog.exec_()
            return 1
"""
    
    # Apply the patches
    # Add imports at the top
    if "# Headless mode imports" not in content:
        import_pos = content.find("import sys")
        if import_pos != -1:
            content = content[:import_pos] + headless_imports + content[import_pos:]
    
    # Replace main function
    main_modified = re.sub(main_pattern, headless_main, content, flags=re.DOTALL)
    
    if main_modified != content:
        with open('main.py', 'w') as f:
            f.write(main_modified)
        print("Successfully patched main.py for headless mode")
        return True
    else:
        print("Failed to patch main.py. Regex pattern did not match.")
        return False

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_main_file()
    else:
        patch_for_headless()

if __name__ == "__main__":
    main() 