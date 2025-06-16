#!/usr/bin/env python3
"""
Apply Enhanced Task Manager
Script to integrate the enhanced task manager with the existing application
"""

import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def apply_enhanced_task_manager():
    """
    Apply the enhanced task manager to the existing GUI
    This should be called after the GUI is initialized but before loading tasks
    """
    
    # Import the integration module
    try:
        from task_manager_integration import integrate_enhanced_task_manager
        print("✅ Enhanced task manager integration module loaded successfully")
    except ImportError as e:
        print(f"❌ Failed to import enhanced task manager: {e}")
        return None
    
    # This function should be called from main.py after GUI initialization
    # Example usage:
    """
    # In main.py, after creating the GUI instance:
    
    from apply_enhanced_task_manager import apply_enhanced_task_manager
    
    # Create GUI instance
    gui = S3UploaderGUI(aws_config, db_manager, user_info, ...)
    
    # Apply enhanced task manager
    task_manager_adapter = apply_enhanced_task_manager(gui)
    
    if task_manager_adapter:
        print("Enhanced task manager applied successfully")
        
        # Load tasks using enhanced manager instead of original method
        if gui.device_id:
            task_manager_adapter.load_tasks_from_database(gui.device_id)
    else:
        print("Failed to apply enhanced task manager, using original system")
        # Fallback to original task loading
        gui.load_tasks_from_database()
    """
    
    print("Enhanced task manager integration ready")
    return integrate_enhanced_task_manager

def patch_main_application():
    """
    Patch the main application to use enhanced task manager
    """
    
    # Read the current main.py
    try:
        with open('main.py', 'r') as f:
            main_content = f.read()
    except FileNotFoundError:
        print("❌ main.py not found")
        return False
    
    # Check if already patched
    if 'apply_enhanced_task_manager' in main_content:
        print("✅ main.py already patched for enhanced task manager")
        return True
    
    # Find the GUI initialization section
    gui_init_pattern = "gui = S3UploaderGUI("
    if gui_init_pattern not in main_content:
        print("❌ Could not find GUI initialization in main.py")
        return False
    
    # Create the patch
    patch_import = """
# Enhanced Task Manager Integration
from apply_enhanced_task_manager import apply_enhanced_task_manager
"""
    
    patch_application = """
        # Apply enhanced task manager for better task ordering and execution
        try:
            integrate_func = apply_enhanced_task_manager()
            task_manager_adapter = integrate_func(gui)
            
            if task_manager_adapter:
                print("✅ Enhanced task manager applied successfully")
                
                # Load tasks using enhanced manager
                if gui.device_id:
                    loaded_count = task_manager_adapter.load_tasks_from_database(gui.device_id)
                    print(f"📋 Loaded {loaded_count} tasks with enhanced ordering")
                else:
                    print("⚠️  No device ID available for task loading")
            else:
                print("⚠️  Failed to apply enhanced task manager, using original system")
                # Fallback to original task loading
                if not gui.skip_state_load:
                    gui.load_tasks_from_database()
                    
        except Exception as e:
            print(f"⚠️  Error applying enhanced task manager: {e}")
            print("📋 Falling back to original task management system")
            # Fallback to original task loading
            if not gui.skip_state_load:
                gui.load_tasks_from_database()
"""
    
    # Apply patches
    lines = main_content.split('\n')
    new_lines = []
    
    # Add import at the top (after other imports)
    import_added = False
    gui_patched = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Add import after existing imports
        if not import_added and line.startswith('from ui.') and 'import' in line:
            new_lines.append(patch_import)
            import_added = True
        
        # Patch after GUI initialization
        if not gui_patched and gui_init_pattern in line:
            # Look for the end of GUI initialization and task loading
            j = i + 1
            while j < len(lines) and ('load_tasks_from_database' not in lines[j] or lines[j].strip().startswith('#')):
                j += 1
            
            if j < len(lines):
                # Found task loading, replace it
                new_lines.extend(patch_application.split('\n'))
                gui_patched = True
                # Skip the original load_tasks_from_database call
                while j < len(lines) and 'load_tasks_from_database' in lines[j]:
                    j += 1
                # Continue from after the original call
                lines = lines[:i+1] + lines[j:]
                break
    
    if not gui_patched:
        print("⚠️  Could not find task loading section to patch")
        return False
    
    # Write the patched file
    try:
        # Create backup
        with open('main.py.backup', 'w') as f:
            f.write(main_content)
        
        # Write patched version
        with open('main.py', 'w') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ main.py patched successfully")
        print("📁 Backup saved as main.py.backup")
        return True
        
    except Exception as e:
        print(f"❌ Error writing patched main.py: {e}")
        return False

def create_migration_guide():
    """Create a migration guide for the enhanced task manager"""
    
    guide_content = """
# Enhanced Task Manager Migration Guide

## Overview
The enhanced task manager provides:
- ✅ Stable task ordering based on priority and creation time
- ✅ Thread-safe task state management
- ✅ Proper sequential execution (one task at a time)
- ✅ Automatic retry for failed tasks
- ✅ UUID-based task identification (no more changing IDs)
- ✅ Comprehensive task status tracking

## Key Improvements

### 1. Task Ordering Priority
```
1. CRITICAL - Interrupted tasks (highest priority)
2. HIGH     - Paused/resumed tasks  
3. NORMAL   - Regular pending tasks
4. LOW      - New tasks (lowest priority)
```

### 2. Stable Task Identification
- Tasks now use UUIDs instead of incrementing integers
- No more task ID conflicts when tasks are deleted
- Backward compatibility maintained for existing code

### 3. Enhanced Status Management
```
PENDING     -> Task created, waiting to be queued
QUEUED      -> Task in execution queue
RUNNING     -> Task currently executing
PAUSED      -> Task paused by user
COMPLETED   -> Task finished successfully
FAILED      -> Task failed (will retry if configured)
CANCELLED   -> Task cancelled by user
INTERRUPTED -> Task was running but app was closed
```

### 4. Thread-Safe Operations
- All task operations are protected by locks
- No race conditions between UI and background threads
- Atomic status updates

## Usage Examples

### Creating a New Task
```python
# Old way (in GUI)
task_id = len(self.upload_tasks) + 1
task = {...}
self.upload_tasks.append(task)

# New way (with adapter)
task_uuid = adapter.create_new_task(
    order_number="135658",
    folder_path="/path/to/folder",
    local_path="/local/path",
    photographers={"main": 1, "assistant": 2},
    order_date=datetime.now(),
    device_id=1,
    created_by="User Name"
)
```

### Checking Task Status
```python
# Old way
task = next((t for t in self.upload_tasks if t['id'] == task_id), None)
if task and task['status'] == 'running':
    # do something

# New way
task = adapter.get_task_by_uuid(task_uuid)
if task and task.status == TaskStatus.RUNNING:
    # do something
```

### Queue Management
```python
# Get queue status
status = adapter.get_queue_status()
print(f"Queue length: {status['queue_length']}")
print(f"Current task: {status['current_task']}")

# Get all tasks with filter
pending_tasks = adapter.get_all_tasks([TaskStatus.PENDING, TaskStatus.QUEUED])
completed_tasks = adapter.get_all_tasks([TaskStatus.COMPLETED])
```

## Migration Steps

1. **Backup your current application**
   ```bash
   cp -r AWSUploaderAppOnly AWSUploaderAppOnly_backup
   ```

2. **Add the enhanced task manager files**
   - `enhanced_task_manager.py`
   - `task_manager_integration.py`
   - `apply_enhanced_task_manager.py`

3. **Apply the integration**
   ```python
   python apply_enhanced_task_manager.py
   ```

4. **Test the application**
   - Start the application
   - Create a new task
   - Verify task ordering
   - Test pause/resume functionality

## Troubleshooting

### If tasks don't appear in correct order:
- Check the database query in `load_tasks_from_database()`
- Verify task priorities are set correctly
- Check the queue processing logic

### If task IDs seem inconsistent:
- The system now uses UUIDs internally
- Legacy IDs are maintained for display purposes only
- Use `adapter.get_task_by_uuid()` for reliable task access

### If tasks get stuck:
- Check the queue status: `adapter.get_queue_status()`
- Verify only one task is running at a time
- Check for thread deadlocks in the logs

## Benefits

1. **No More Task ID Conflicts**: UUIDs ensure unique identification
2. **Proper Ordering**: Tasks execute in priority order, then creation time
3. **State Consistency**: Thread-safe operations prevent race conditions
4. **Better Recovery**: Interrupted tasks are automatically prioritized
5. **Improved Monitoring**: Comprehensive status tracking and callbacks

## Backward Compatibility

The integration adapter maintains backward compatibility:
- Existing GUI code continues to work
- Legacy task IDs are mapped to UUIDs
- Original method signatures are preserved
- Database schema remains unchanged

## Performance Impact

- Minimal overhead from UUID generation
- Thread-safe operations add slight latency
- Better overall performance due to proper ordering
- Reduced database queries through caching

## Future Enhancements

1. **Concurrent Execution**: Easy to modify for multiple simultaneous tasks
2. **Task Dependencies**: Can add task dependency management
3. **Advanced Scheduling**: Time-based task scheduling
4. **Load Balancing**: Distribute tasks across multiple devices
"""

    try:
        with open('ENHANCED_TASK_MANAGER_GUIDE.md', 'w') as f:
            f.write(guide_content)
        print("📖 Migration guide created: ENHANCED_TASK_MANAGER_GUIDE.md")
        return True
    except Exception as e:
        print(f"❌ Error creating migration guide: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Enhanced Task Manager Integration")
    print("=" * 50)
    
    # Create migration guide
    create_migration_guide()
    
    # Check if we should patch main.py
    if len(sys.argv) > 1 and sys.argv[1] == "--patch":
        print("\n📝 Patching main.py...")
        if patch_main_application():
            print("✅ Application patched successfully!")
            print("\n🎯 Next steps:")
            print("1. Review the changes in main.py")
            print("2. Test the application: python main.py")
            print("3. Check the migration guide: ENHANCED_TASK_MANAGER_GUIDE.md")
        else:
            print("❌ Failed to patch application")
    else:
        print("\n📋 Integration module ready")
        print("💡 To automatically patch main.py, run:")
        print("   python apply_enhanced_task_manager.py --patch")
        print("\n📖 See ENHANCED_TASK_MANAGER_GUIDE.md for manual integration steps") 