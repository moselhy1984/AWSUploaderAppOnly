# AWS Uploader Stability Improvements

This document describes the comprehensive stability improvements implemented to address the following issues in the AWS Uploader application:

1. Qt plugin conflicts between PyQt5 and Homebrew
2. Memory management problems causing crashes
3. Auto-resume functionality for incomplete upload tasks

## Quick Start

To run the application with all stability improvements enabled:

```bash
./run_optimized.sh
```

This script automatically configures the optimal environment settings to prevent crashes and ensure proper task resumption.

## Issues Addressed

### 1. Qt Plugin Conflicts

The application was experiencing conflicts between the Qt libraries provided by PyQt5 and those installed via Homebrew. This caused unpredictable behavior and crashes with errors like:

```
This application failed to start because it could not find or load the Qt platform plugin "cocoa"
```

**Solution:**
- Set environment variables to explicitly use PyQt5's Qt plugins
- Create a `qt.conf` file to direct Qt to the correct plugin path
- Prioritize PyQt5 libraries in the search path

### 2. Memory Management

The application had memory management issues leading to crashes during long uploads:

**Solution:**
- Created a `memory_manager.py` module for monitoring and optimizing memory usage
- Added automatic garbage collection at regular intervals
- Implemented large object detection and cleanup
- Created a standalone memory monitor for debugging memory issues
- Configured Python's garbage collector based on available system memory

### 3. Auto-Resume Functionality

The application was unable to reliably resume incomplete tasks after restart:

**Solution:**
- Enhanced `task_auto_resume.py` to handle database failures gracefully
- Created `db_task_resumer.py` with more robust fallback mechanisms
- Added ability to find and resume tasks from both database and state files
- Improved task resumption logic with multiple attempt methods
- Implemented automatic user login for task resumption

## New Files Created

1. **run_optimized.sh** - Main launcher that configures environment and runs the application
2. **memory_manager.py** - Memory monitoring and optimization module
3. **db_task_resumer.py** - Enhanced database task resumption with fallbacks
4. **monitor_memory.py** - Simple memory monitoring script (created by run_optimized.sh)

## Modified Files

1. **main.py** - Added support for memory management and enhanced task resumption
2. **ui/uploader_gui.py** - Added auto_resume_task method for task resumption

## Environment Variables

The following environment variables control application behavior:

| Variable | Description | Default |
|----------|-------------|---------|
| `USE_MEMORY_MANAGER` | Enable memory management | 0 (disabled) |
| `SAFE_MODE` | Run with reduced functionality | 0 (disabled) |
| `NO_AUTO_RESUME` | Disable standard auto-resume | 0 (auto-resume enabled) |
| `SKIP_STATE_LOAD` | Skip loading saved states | 0 (load states) |
| `LOAD_ALL_TASKS` | Load all tasks regardless of date | 0 (today's only) |
| `AUTO_RESUME_INCOMPLETE` | Auto-resume incomplete tasks | 0 (disabled) |
| `AUTO_LOGIN` | Enable automatic login | 0 (disabled) |

## Fallback Mechanisms

The solution implements multiple fallback mechanisms to ensure reliability:

1. If the database connection fails, the app will look for state files
2. If auto_resume_all_tasks fails, it will try individual task resumption
3. If PyQt5 plugins can't be found, it will try using system Qt
4. If memory manager is unavailable, it will run without it

## Monitoring and Diagnostics

The solution includes monitoring and diagnostic tools:

1. Memory usage tracking (if psutil is installed)
2. Detailed logging of task resumption process
3. Logs saved to `optimized_run_log.txt` and `memory_monitor.log`

## Future Improvements

Consider implementing the following future improvements:

1. Database connection pooling to prevent connection timeouts
2. Add automated tests for task resumption
3. Implement a more sophisticated caching mechanism
4. Add user settings for memory management thresholds
5. Implement progressive loading of large image files

## Troubleshooting

If you encounter issues:

1. Check log files in the application directory
2. Verify PyQt5 and Qt installations
3. Try running in safe mode: `export SAFE_MODE=1 && ./run_optimized.sh`
4. Install psutil for better memory management: `pip install psutil` 