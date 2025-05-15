#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fix Qt conflicts for the AWS Uploader application.
This script creates a specialized launcher that prevents Qt library conflicts
by ensuring only one set of Qt libraries is loaded.
"""

import os
import sys
import subprocess
import glob
import platform
import shutil
import site

def create_launch_script():
    """Create a specialized launcher script to avoid Qt conflicts."""
    # Create a shell script that runs the application with conflict prevention
    with open('run_app.sh', 'w') as f:
        f.write("#!/bin/bash\n")
        f.write("# AWS Uploader conflict-free launcher\n\n")
        
        f.write("echo \"Starting AWS Uploader with conflict prevention...\"\n\n")
        
        # Activate the virtual environment
        f.write("source aws_app_env/bin/activate\n\n")
        
        # Set environment variables to prevent library conflicts
        f.write("# Prevent library conflicts\n")
        f.write("export PYTHONNOUSERSITE=1\n")  # Prevent loading user site packages
        f.write("export PYQT_NO_BUNDLED_LIBS=1\n")  # Prevent loading bundled libraries
        
        # Safe mode settings
        f.write("\n# Safe mode settings\n")
        f.write("export SKIP_STATE_LOAD=1\n")
        f.write("export NO_AUTO_RESUME=1\n")
        f.write("export SAFE_MODE=1\n")
        
        # Add a pre-launch Python script that will run before the main application
        f.write("\n# Run pre-launch script to clean environment\n")
        f.write("python - << 'EOF'\n")
        f.write("import os\n")
        f.write("import sys\n")
        f.write("import importlib\n")
        f.write("\n")
        f.write("# Force PyQt to use the system Qt libraries\n")
        f.write("os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = '/opt/homebrew/Cellar/qt@5/5.15.16_2/plugins/platforms'\n")
        f.write("os.environ['QT_PLUGIN_PATH'] = '/opt/homebrew/Cellar/qt@5/5.15.16_2/plugins'\n")
        f.write("os.environ['QT_QPA_PLATFORM'] = 'cocoa'\n")
        f.write("\n")
        f.write("print('Pre-launch environment setup complete')\n")
        f.write("EOF\n\n")
        
        # Run the application with a clean environment
        f.write("# Run application without library conflicts\n")
        f.write("DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/qt@5/5.15.16_2/lib DYLD_FRAMEWORK_PATH=/opt/homebrew/Cellar/qt@5/5.15.16_2/lib python main.py\n\n")
        
        # Handle exit code
        f.write("# If the application exited with an error code, inform the user\n")
        f.write("EXIT_CODE=$?\n")
        f.write("if [ $EXIT_CODE -ne 0 ]; then\n")
        f.write("    echo \"Application exited with error code: $EXIT_CODE\"\n")
        f.write("    echo \"Please check the logs for more information.\"\n")
        f.write("fi\n\n")
        
        f.write("exit $EXIT_CODE\n")
    
    # Make the script executable
    os.chmod('run_app.sh', 0o755)
    print("Created executable run_app.sh script.")
    
    # Backup the original run script
    if os.path.exists('run_simple.sh'):
        shutil.copy('run_simple.sh', 'run_simple.sh.bak')
        print("Backed up original run_simple.sh script.")
    
    return True

if __name__ == "__main__":
    print("Creating conflict-free launcher for AWS Uploader...")
    create_launch_script()
    print("Done! Now run ./run_app.sh to start the application without conflicts.") 