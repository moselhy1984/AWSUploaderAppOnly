#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Safe runner for the AWS Uploader application.
This script sets environment variables to run the app in a safer mode
that avoids memory errors caused by task resumption.
"""

import os
import sys
import subprocess
import site
import glob
import platform

def find_qt_plugin_path():
    """Find the Qt plugin path in the site-packages directory."""
    # Try all potential site-packages locations
    potential_paths = []
    
    # Add site-packages from our current environment
    for site_dir in site.getsitepackages():
        potential_paths.append(os.path.join(site_dir, 'PyQt5', 'Qt5', 'plugins'))
        potential_paths.append(os.path.join(site_dir, 'PyQt5', 'Qt', 'plugins'))
        potential_paths.append(os.path.join(site_dir, 'PyQt5', 'plugins'))
    
    # Add the venv path if available
    if hasattr(sys, 'prefix'):
        potential_paths.append(os.path.join(sys.prefix, 'lib', 'python*', 'site-packages', 'PyQt5', 'Qt5', 'plugins'))
        potential_paths.append(os.path.join(sys.prefix, 'lib', 'python*', 'site-packages', 'PyQt5', 'Qt', 'plugins'))
    
    # Special case for macOS homebrew
    if platform.system() == 'Darwin':
        potential_paths.append('/usr/local/opt/qt5/plugins')
        potential_paths.append('/usr/local/Cellar/qt*/*/plugins')
        potential_paths.append('/opt/homebrew/opt/qt*/plugins')
    
    # Resolve glob patterns and check if directories exist
    existing_paths = []
    for path_pattern in potential_paths:
        if '*' in path_pattern:
            # Expand glob pattern
            expanded_paths = glob.glob(path_pattern)
            existing_paths.extend([p for p in expanded_paths if os.path.isdir(p)])
        elif os.path.isdir(path_pattern):
            existing_paths.append(path_pattern)
    
    return existing_paths

def main():
    # Set environment variables to disable problematic features
    os.environ['SKIP_STATE_LOAD'] = '1'  # Skip loading saved state
    os.environ['NO_AUTO_RESUME'] = '1'   # Disable automatic resumption
    os.environ['SAFE_MODE'] = '1'        # Enable safe mode
    
    # Fix Qt platform plugin issue
    if platform.system() == 'Darwin':
        # macOS specific settings
        os.environ['QT_QPA_PLATFORM'] = 'cocoa'
        os.environ['QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM'] = '1'
    elif platform.system() == 'Windows':
        os.environ['QT_QPA_PLATFORM'] = 'windows'
    else:  # Linux
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
    
    # Find Qt plugin paths
    qt_plugin_paths = find_qt_plugin_path()
    if qt_plugin_paths:
        os.environ['QT_PLUGIN_PATH'] = os.pathsep.join(qt_plugin_paths)
        
        # Also set the QT_QPA_PLATFORM_PLUGIN_PATH on macOS
        if platform.system() == 'Darwin':
            for path in qt_plugin_paths:
                platforms_dir = os.path.join(path, 'platforms')
                if os.path.isdir(platforms_dir):
                    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = platforms_dir
                    break
    
    # Set QT debug settings
    os.environ['QT_DEBUG_PLUGINS'] = '1'  # Enable plugin debugging
    
    # Disable Qt debug messages for normal operation
    os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.plugin=true'
    
    # Ensure proper encoding
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Enable garbage collection debugging
    os.environ['PYTHONMALLOCSTATS'] = '1'
    
    print("Starting AWS Uploader in safe mode...")
    print("- Auto-resume is disabled")
    print("- State loading is disabled")
    print("- Safe mode is enabled")
    print(f"- Qt platform set to '{os.environ.get('QT_QPA_PLATFORM', 'not set')}'")
    print(f"- Qt plugin path: {os.environ.get('QT_PLUGIN_PATH', 'not set')}")
    
    # Execute the main application
    if sys.platform == 'win32':
        # Windows: Use python command
        subprocess.run([sys.executable, 'main.py'])
    else:
        # macOS/Linux: Execute as script
        subprocess.run(['python', 'main.py'])

if __name__ == "__main__":
    main() 