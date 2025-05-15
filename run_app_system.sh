#!/bin/bash

# Use Homebrew Python instead of venv
PYTHON_PATH="/opt/homebrew/bin/python3"

# Make sure all required packages are installed for the system Python
$PYTHON_PATH -m pip install --user mysql-connector-python boto3 cryptography getmac

# Set the Qt environment variables 
export QT_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins/platforms
export PYTHONPATH=/opt/homebrew/lib/python3.13/site-packages:$PYTHONPATH

# Run the application
$PYTHON_PATH main.py 