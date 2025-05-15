#!/bin/bash
# AWS Uploader Core Launcher
# This script runs the core AWS functionality without the GUI

echo "============================================"
echo "  AWS Uploader Core Application Launcher"
echo "============================================"
echo "This will run the AWS Uploader without the GUI"
echo "to avoid Qt platform plugin issues."
echo "Core database and AWS functionality is enabled."
echo ""

# Activate the virtual environment
source aws_app_env/bin/activate

# Set environment variables 
export SKIP_GUI=1
export SKIP_STATE_LOAD=1
export NO_AUTO_RESUME=1
export SAFE_MODE=1

# Run the core application
echo "Starting AWS Uploader Core Application..."
echo "Press Ctrl+C to exit when finished."
echo "============================================"
echo ""

# Execute the core application
python aws_core.py

# If the application exited with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "============================================"
    echo "Application exited with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
    echo "============================================"
else
    echo ""
    echo "============================================"
    echo "AWS Uploader Core exited successfully"
    echo "============================================"
fi

exit $EXIT_CODE 