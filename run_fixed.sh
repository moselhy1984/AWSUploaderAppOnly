#!/bin/bash
# Fixed launcher for AWS Uploader application

echo "Starting AWS Uploader with fixed Qt configuration..."

source aws_app_env/bin/activate

# Set environment variables for Qt
export QT_PLUGIN_PATH="/opt/homebrew/opt/qt@5/plugins"
export QT_QPA_PLATFORM=cocoa
export QT_DEBUG_PLUGINS=1

# Disable problematic features
export SKIP_STATE_LOAD=1
export NO_AUTO_RESUME=1
export SAFE_MODE=1

# Run the application
python main.py

# If the application exited with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Application exited with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
fi

exit $EXIT_CODE
