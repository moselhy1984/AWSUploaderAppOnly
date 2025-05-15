#!/bin/bash
# Safe launcher for AWS Uploader application
# This script runs the application with safety precautions to prevent memory errors
# and Qt platform plugin issues.

echo "Starting AWS Uploader in safe mode..."
echo "- Auto-resume disabled"
echo "- State loading disabled"
echo "- Memory error prevention enabled"
echo "- Qt platform plugin configured"

# Activate the virtual environment
source aws_app_env/bin/activate

# Run the application using the safe runner script
python run_safe.py

# If the application exited with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Application exited with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
fi

exit $EXIT_CODE 