#!/bin/bash
# AWS Uploader conflict-free launcher

echo "Starting AWS Uploader with conflict prevention..."

source aws_app_env/bin/activate

# Prevent library conflicts
export PYTHONNOUSERSITE=1
export PYQT_NO_BUNDLED_LIBS=1

# Safe mode settings
export SKIP_STATE_LOAD=1
export NO_AUTO_RESUME=1
export SAFE_MODE=1

# Run pre-launch script to clean environment
python - << 'EOF'
import os
import sys
import importlib

# Force PyQt to use the system Qt libraries
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = '/opt/homebrew/Cellar/qt@5/5.15.16_2/plugins/platforms'
os.environ['QT_PLUGIN_PATH'] = '/opt/homebrew/Cellar/qt@5/5.15.16_2/plugins'
os.environ['QT_QPA_PLATFORM'] = 'cocoa'

print('Pre-launch environment setup complete')
EOF

# Run application without library conflicts
DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/qt@5/5.15.16_2/lib DYLD_FRAMEWORK_PATH=/opt/homebrew/Cellar/qt@5/5.15.16_2/lib python main.py

# If the application exited with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Application exited with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
fi

exit $EXIT_CODE
