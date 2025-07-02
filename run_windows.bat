@echo off
echo ========================================
echo AWS Uploader for Windows
echo ========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

:: Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

:: Check if requirements are installed
pip show PyQt5 >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Windows-specific requirements...
    pip install -r requirements-windows.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install requirements
        echo Trying fallback installation...
        pip install --upgrade pip
        pip install PyQt5 boto3 mysql-connector-python psutil getmac pyperclip cryptography requests
        if %errorlevel% neq 0 (
            echo ERROR: Package installation failed completely
            pause
            exit /b 1
        )
    )
)

:: Check for configuration files
if not exist "config.enc" (
    echo WARNING: config.enc file not found
    echo Please ensure configuration files are present
)

if not exist "encryption_key.txt" (
    echo WARNING: encryption_key.txt file not found
    echo Please ensure configuration files are present
)

:: Set Windows-specific environment variables
set PYTHONIOENCODING=utf-8
set QT_SCALE_FACTOR=1.0
set QT_AUTO_SCREEN_SCALE_FACTOR=0

:: Run the application
echo.
echo Starting AWS Uploader...
echo Press Ctrl+C to stop the application
echo.
python main.py

:: Handle exit
if %errorlevel% neq 0 (
    echo.
    echo Application exited with error code: %errorlevel%
    echo Check the console output above for error details
)

echo.
echo Application closed.
pause 