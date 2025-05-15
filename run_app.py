#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess

# Set essential Qt environment variables
os.environ['QT_PLUGIN_PATH'] = '/opt/homebrew/opt/qt@5/plugins'
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = '/opt/homebrew/opt/qt@5/plugins/platforms'

# Run the main application
try:
    print("Starting AWS Uploader application...")
    subprocess.run([sys.executable, 'main.py'], check=True)
except subprocess.CalledProcessError as e:
    print(f"Error running application: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    print("Application interrupted by user")
    sys.exit(0) 