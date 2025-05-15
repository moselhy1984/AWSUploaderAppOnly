#!/bin/bash

# Activate the virtual environment
source aws_app_env/bin/activate

# Install all required packages
pip install mysql-connector-python boto3 cryptography getmac

# Install PyQt5 from Homebrew through pip
PYTHONPATH=/opt/homebrew/lib/python3.13/site-packages pip install --no-deps PyQt5

# Set the necessary environment variables for Qt
export QT_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins/platforms
export PYTHONPATH=/opt/homebrew/lib/python3.13/site-packages:$PYTHONPATH

# Run the application
python main.py

# Deactivate the virtual environment when done
deactivate 