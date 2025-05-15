#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fix Qt on macOS for the AWS Uploader application.
This script fixes the Qt plugin issues on macOS by ensuring the correct
paths are set and the necessary symbolic links are created.
"""

import os
import sys
import subprocess
import glob
import platform
import shutil
import site

def run_command(command):
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error: {e.stderr}")
        return None

def fix_qt_on_macos():
    """Fix Qt plugin issues on macOS."""
    if platform.system() != 'Darwin':
        print("This script is only for macOS.")
        return False
    
    # Get the site-packages directory
    site_packages = site.getsitepackages()[0]
    pyqt_dir = os.path.join(site_packages, 'PyQt5')
    
    print(f"PyQt5 directory: {pyqt_dir}")
    
    # Find Qt plugin directories
    homebrew_qt_plugins = None
    for path in [
        '/opt/homebrew/opt/qt@5/plugins',
        '/opt/homebrew/Cellar/qt@5/*/plugins',
        '/usr/local/opt/qt@5/plugins',
        '/usr/local/Cellar/qt@5/*/plugins'
    ]:
        if '*' in path:
            matches = glob.glob(path)
            if matches:
                homebrew_qt_plugins = matches[0]
                break
        elif os.path.isdir(path):
            homebrew_qt_plugins = path
            break
    
    if not homebrew_qt_plugins:
        print("Could not find Qt plugins directory from Homebrew.")
        return False
    
    print(f"Found Homebrew Qt plugins: {homebrew_qt_plugins}")
    
    # Create a qt.conf file in the application directory
    with open('qt.conf', 'w') as f:
        f.write("[Paths]\n")
        f.write(f"Plugins = {homebrew_qt_plugins}\n")
        f.write("Translations = PyQt5/Qt5/translations\n")
        f.write("Data = PyQt5/Qt5\n")
    
    print("Created qt.conf in the application directory.")
    
    # Create a shell script to run the application with the correct environment
    with open('run_fixed.sh', 'w') as f:
        f.write("#!/bin/bash\n")
        f.write("# Fixed launcher for AWS Uploader application\n\n")
        
        f.write("echo \"Starting AWS Uploader with fixed Qt configuration...\"\n\n")
        
        # Activate the virtual environment
        f.write("source aws_app_env/bin/activate\n\n")
        
        # Set important environment variables
        f.write("# Set environment variables for Qt\n")
        f.write(f"export QT_PLUGIN_PATH=\"{homebrew_qt_plugins}\"\n")
        f.write("export QT_QPA_PLATFORM=cocoa\n")
        f.write("export QT_DEBUG_PLUGINS=1\n\n")
        
        # Disable problematic features
        f.write("# Disable problematic features\n")
        f.write("export SKIP_STATE_LOAD=1\n")
        f.write("export NO_AUTO_RESUME=1\n")
        f.write("export SAFE_MODE=1\n\n")
        
        # Run the application
        f.write("# Run the application\n")
        f.write("python main.py\n\n")
        
        # Handle exit code
        f.write("# If the application exited with an error code, inform the user\n")
        f.write("EXIT_CODE=$?\n")
        f.write("if [ $EXIT_CODE -ne 0 ]; then\n")
        f.write("    echo \"Application exited with error code: $EXIT_CODE\"\n")
        f.write("    echo \"Please check the logs for more information.\"\n")
        f.write("fi\n\n")
        
        f.write("exit $EXIT_CODE\n")
    
    # Make the script executable
    os.chmod('run_fixed.sh', 0o755)
    print("Created executable run_fixed.sh script.")
    
    return True

if __name__ == "__main__":
    print("Fixing Qt on macOS...")
    if fix_qt_on_macos():
        print("Done! Now run ./run_fixed.sh to start the application.")
    else:
        print("Failed to fix Qt on macOS.") 