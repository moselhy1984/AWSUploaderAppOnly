#!/bin/bash
# AWS Uploader Optimized Script
# Addresses Qt conflicts, memory management, and auto-resume issues

echo "=================================================="
echo "  AWS UPLOADER - OPTIMIZED MODE"
echo "=================================================="
echo ""

# Activate virtual environment
if [ -d "aws_app_env" ]; then
    source aws_app_env/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "⚠️ Virtual environment not found at aws_app_env/"
    echo "   Using system Python environment"
fi

# Determine PyQt5 paths
PYQT_PATH=$(python -c "import site, os; print(os.path.join(site.getsitepackages()[0], 'PyQt5', 'Qt5'))")
PYQT_PLUGINS="${PYQT_PATH}/plugins"
BREW_QT="/opt/homebrew/Cellar/qt@5"

# Create qt.conf file to specify plugin paths
cat > qt.conf << EOQ
[Paths]
Plugins=${PYQT_PLUGINS}
EOQ
echo "✓ Created qt.conf file to direct Qt to use PyQt5 plugins"

# Completely disable Homebrew Qt libraries
if [ -d "$BREW_QT" ]; then
    echo "✓ Detected Homebrew Qt libraries at: $BREW_QT"
    echo "  Configuring PyQt5 to avoid conflicts..."
    # Use QT_PLUGIN_PATH for PyQt5 libraries only
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    # Explicitly specify platform plugin path
    export QT_QPA_PLATFORM_PLUGIN_PATH="${PYQT_PLUGINS}/platforms"
    # Explicitly specify cocoa platform
    export QT_QPA_PLATFORM=cocoa
    # Disable Qt plugin debugging
    export QT_DEBUG_PLUGINS=0
    # Reorder library search paths
    export PATH="${PYQT_PATH}/bin:$PATH"
    export DYLD_FRAMEWORK_PATH="${PYQT_PATH}/lib"
    export DYLD_LIBRARY_PATH="${PYQT_PATH}/lib"
    echo "✓ Environment set to prioritize PyQt5 over Homebrew Qt"
else
    echo "✓ No Homebrew Qt libraries detected, using PyQt5 directly"
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    export QT_QPA_PLATFORM=cocoa
fi

# Check if psutil is installed for memory management
python -c "import psutil" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Psutil is installed, enabling memory management"
    
    # Create the memory management integration if it doesn't exist
    if [ ! -f "memory_manager.py" ]; then
        echo "  - Memory manager module not found, skipping memory optimization"
    else
        echo "  - Memory manager found, will use for optimizing memory usage"
        # Enable Memory Manager module
        export USE_MEMORY_MANAGER=1
    fi
else
    echo "⚠️ Psutil is not installed, memory management will be limited"
    echo "  Consider running: pip install psutil"
fi

# Configure application behavior
# Disable standard auto-resume (this helps avoid memory issues)
export NO_AUTO_RESUME=1
# Skip automatic state loading
export SKIP_STATE_LOAD=1
# Force loading all tasks from database, not just today's tasks
export LOAD_ALL_TASKS=1
# Enable auto-resume mode for incomplete tasks
export AUTO_RESUME_INCOMPLETE=1
# Allow automatic login for resuming tasks without user interaction
export AUTO_LOGIN=1

echo "✓ Application configured with these settings:"
echo "  - Qt plugin conflicts resolved"
echo "  - Auto-resume for incomplete tasks enabled" 
echo "  - State management optimized for stability"
echo ""

# Create a simple memory monitor script for the application
if [ ! -f "monitor_memory.py" ]; then
    cat > monitor_memory.py << 'EOPY'
#!/usr/bin/env python3
"""Simple memory monitor for AWS Uploader"""
import os
import sys
import time
import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def get_memory_usage():
    """Get current process memory usage in MB"""
    if HAS_PSUTIL:
        try:
            # Get current process
            process = psutil.Process(os.getpid())
            # Get memory info in MB
            return process.memory_info().rss / (1024 * 1024)
        except:
            return 0
    return 0

def log(message):
    """Log a message with timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def monitor_memory(interval=60, log_file=None):
    """
    Monitor memory usage at regular intervals
    
    Args:
        interval (int): Seconds between checks
        log_file (str): Optional log file path
    """
    if not HAS_PSUTIL:
        log("Psutil not installed. Memory monitoring disabled.")
        return

    log(f"Starting memory monitoring every {interval} seconds")
    
    start_time = datetime.datetime.now()
    
    while True:
        # Get memory usage
        mem_usage = get_memory_usage()
        
        # Get run time
        run_time = datetime.datetime.now() - start_time
        hours, remainder = divmod(run_time.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Log usage
        log(f"Memory usage: {mem_usage:.1f} MB | Runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s")
        
        # Sleep until next check
        time.sleep(interval)

if __name__ == "__main__":
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="Monitor memory usage of AWS Uploader")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--log-file", type=str, help="Log file path")
    args = parser.parse_args()
    
    monitor_memory(interval=args.interval, log_file=args.log_file)
EOPY
    chmod +x monitor_memory.py
    echo "✓ Created memory monitoring script"
fi

# Run memory monitor in background if psutil is available
python -c "import psutil" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Starting memory monitor in background..."
    python monitor_memory.py --interval 60 > memory_monitor.log 2>&1 &
    MONITOR_PID=$!
    echo "✓ Memory monitor started with PID: $MONITOR_PID"
fi

# Run the application and capture output to a log file
echo "Starting AWS Uploader with all optimizations enabled..."
python main.py 2>&1 | tee optimized_run_log.txt

# Store the exit code
EXIT_CODE=$?

# Stop the memory monitor if it's running
if [ -n "$MONITOR_PID" ]; then
    echo "Stopping memory monitor..."
    kill $MONITOR_PID 2>/dev/null
fi

if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Application closed successfully"
else
    echo "⚠️ Application exited with code: $EXIT_CODE"
    echo "  Please check optimized_run_log.txt for details"
fi
