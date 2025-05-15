#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS Uploader with Qt platform plugin workaround.
This script starts the AWS Uploader application with a minimal
Qt configuration that should work regardless of Qt installation.
"""

import os
import sys
import subprocess
import site
import glob
import shutil

def main():
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Enable debug output to diagnose Qt issues
    os.environ['QT_DEBUG_PLUGINS'] = '1'
    
    # Disable auto resume to prevent memory errors
    os.environ['NO_AUTO_RESUME'] = '1'
    os.environ['SKIP_STATE_LOAD'] = '1'
    os.environ['SAFE_MODE'] = '1'
    
    # Try to use the minimal platform
    os.environ['QT_QPA_PLATFORM'] = 'minimal'
    
    # Find all Qt plugin paths from both Homebrew and PyQt
    potential_plugin_paths = []
    
    # Add PyQt plugin paths
    for site_dir in site.getsitepackages():
        qt5_plugins = os.path.join(site_dir, 'PyQt5', 'Qt5', 'plugins')
        if os.path.exists(qt5_plugins):
            potential_plugin_paths.append(qt5_plugins)
    
    # Add Homebrew plugin paths
    for brew_path in ['/opt/homebrew/Cellar/qt*/*/plugins', '/usr/local/opt/qt*/plugins']:
        for path in glob.glob(brew_path):
            if os.path.exists(path):
                potential_plugin_paths.append(path)
    
    # Set all potential plugin paths
    if potential_plugin_paths:
        os.environ['QT_PLUGIN_PATH'] = os.pathsep.join(potential_plugin_paths)
    
    # Create a qt.conf file to help Qt find plugins
    with open(os.path.join(current_dir, 'qt.conf'), 'w') as f:
        f.write("[Paths]\n")
        if potential_plugin_paths:
            f.write(f"Plugins = {potential_plugin_paths[0]}\n")
    
    print("Starting AWS Uploader with minimal Qt configuration...")
    print(f"QT_PLUGIN_PATH = {os.environ.get('QT_PLUGIN_PATH', 'not set')}")
    print(f"QT_QPA_PLATFORM = {os.environ.get('QT_QPA_PLATFORM', 'not set')}")
    print("Safe mode is enabled - auto-resume is disabled")
    
    # Launch the application
    try:
        # Run with subprocess to capture output
        result = subprocess.run([sys.executable, 'main.py'], 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True)
        
        # Check if the application failed to start
        if result.returncode != 0:
            print(f"Application exited with code {result.returncode}")
            print("Error output:")
            print(result.stderr)
            
            # If there was a Qt platform plugin error, try with offscreen platform
            if "Could not find the Qt platform plugin" in result.stderr:
                print("\nTrying with offscreen platform...")
                os.environ['QT_QPA_PLATFORM'] = 'offscreen'
                subprocess.run([sys.executable, 'main.py'])
        
    except Exception as e:
        print(f"Error running application: {e}")

if __name__ == "__main__":
    main() 