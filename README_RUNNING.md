# AWS Uploader Application - Running Guide

This guide provides instructions for running the AWS Uploader application in different modes to work around Qt platform plugin issues on macOS.

## Running Options

The application can be run in several different modes:

1. **Normal Mode** - Standard GUI mode (may have Qt platform plugin issues)
2. **Safe Mode** - GUI mode with memory safety features 
3. **Core Mode** - Headless mode with no GUI (avoids all Qt issues)
4. **Test Mode** - Component test only (verifies functionality)

## Prerequisites

- Make sure you have Python 3.x installed
- Ensure the virtual environment is set up (aws_app_env)
- AWS credentials should be configured if you want to use the AWS functionality

## Running in Normal Mode

To run the application in normal mode:

```bash
python main.py
```

**Note**: This may encounter Qt platform plugin issues on some macOS environments.

## Running in Safe Mode

The safe mode prevents memory errors that can occur in normal mode:

```bash
./run_safe.sh
```

This mode:
- Disables automatic task resumption
- Skips loading saved state
- Configures Qt platform plugin correctly
- Prevents memory issues

## Running in Core Mode (Headless)

If you encounter persistent Qt platform plugin issues, use the headless core mode:

```bash
./run_core.sh
```

This mode:
- Runs without any GUI components
- Avoids all Qt-related issues
- Provides access to core database and AWS functionality
- Is ideal for server environments or troubleshooting

## Testing Core Components

To verify that the core components are working correctly without running the full application:

```bash
./run_headless.sh
```

This performs tests on:
- Database connectivity
- Configuration management
- AWS environment detection

## Troubleshooting Qt Platform Plugin Issues

If you encounter Qt platform plugin errors:

1. Try the safe mode first: `./run_safe.sh`
2. If still experiencing issues, use core mode: `./run_core.sh`
3. Verify components work by running tests: `./run_headless.sh`

## Technical Details

The provided scripts handle several common issues:

1. **Memory Management Issues**:
   - Auto-resume feature causes memory problems
   - State loading can lead to double-free errors

2. **Qt Platform Plugin Issues**:
   - Conflicts between PyQt and system Qt libraries
   - Missing or incompatible platform plugins
   - Path resolution problems for plugins

3. **Environment Variables**:
   - SAFE_MODE=1 - Enables safe mode
   - SKIP_STATE_LOAD=1 - Disables loading saved state
   - NO_AUTO_RESUME=1 - Disables task resumption
   - QT_QPA_PLATFORM=cocoa - Specifies Qt platform
   - SKIP_GUI=1 - Run in headless mode

## Restoring Backup Files

If you need to restore from backups:

```bash
# If a main.py.bak file exists
cp main.py.bak main.py
```

## Contact

For further assistance or bug reports, please contact the application maintainer. 