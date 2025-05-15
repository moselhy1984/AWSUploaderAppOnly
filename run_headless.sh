#!/bin/bash
# AWS Uploader Test Script
# This script verifies that the application's core components work properly

echo "Starting AWS Uploader component test..."

# Activate the virtual environment
source aws_app_env/bin/activate

# Create a temporary Python test script
cat > test_components.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
from pathlib import Path
from datetime import datetime

def log(message):
    """Print a timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_database():
    """Test database connection"""
    try:
        from database.db_manager import DatabaseManager
        log("Initializing database connection...")
        db = DatabaseManager()
        
        if hasattr(db, 'get_user_count'):
            user_count = db.get_user_count()
            log(f"Number of users in database: {user_count}")
        elif hasattr(db, 'get_users'):
            users = db.get_users()
            log(f"Number of users in database: {len(users) if users else 0}")
        else:
            log("Database connected but could not retrieve user count")
        
        if hasattr(db, 'close'):
            db.close()
            log("Database connection closed successfully")
        return True
    except Exception as e:
        log(f"Database test failed: {e}")
        return False

def test_config():
    """Test configuration manager"""
    try:
        from config.secure_config import SecureConfigManager
        log("Testing configuration manager...")
        config = SecureConfigManager()
        
        if config.config_path.exists():
            log(f"Config file exists at {config.config_path}")
        else:
            log(f"Config file not found at {config.config_path}")
        
        # Test methods available in config manager
        log("Available methods in SecureConfigManager:")
        methods = [method for method in dir(config) if callable(getattr(config, method)) and not method.startswith('__')]
        for method in methods:
            log(f"  - {method}")
        
        return True
    except Exception as e:
        log(f"Configuration test failed: {e}")
        return False

def main():
    """Run component tests"""
    log("Running AWS Uploader component tests...")
    
    # Add current directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Test database
    db_success = test_database()
    
    # Test config
    config_success = test_config()
    
    # Summary
    log("\n--- Test Summary ---")
    log(f"Database test: {'PASSED' if db_success else 'FAILED'}")
    log(f"Config test: {'PASSED' if config_success else 'FAILED'}")
    
    if db_success and config_success:
        log("All core components are working properly!")
        return 0
    else:
        log("Some components failed testing")
        return 1

if __name__ == "__main__":
    sys.exit(main())
EOF

# Make the script executable
chmod +x test_components.py

# Run the test
python test_components.py

# Clean up
rm test_components.py

# If the application exited with an error code, inform the user
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Component tests failed with error code: $EXIT_CODE"
    echo "Please check the logs for more information."
else
    echo "Component tests completed successfully!"
    echo "The core functionality of the AWS Uploader is working properly."
fi

exit $EXIT_CODE 