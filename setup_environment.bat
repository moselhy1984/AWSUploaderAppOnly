@echo off
title AWS Uploader - Environment Setup
chcp 65001 >nul 2>&1
echo ========================================
echo ⚙️  AWS Uploader - Environment Setup
echo ========================================
echo Setting up complete development environment...
echo.

:: Check Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  Notice: Not running as Administrator
    echo Some operations may require elevated privileges
    echo.
)

:: Check Python installation
echo 🔍 Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from python.org
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    echo After installing Python, run this script again.
    pause
    exit /b 1
)

echo ✅ Python found:
python --version

:: Check Python version
for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python version: %PYTHON_VERSION%

:: Set environment variables
echo 🔧 Setting environment variables...
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set QT_SCALE_FACTOR=1.0
set QT_AUTO_SCREEN_SCALE_FACTOR=0
echo ✅ Environment variables set

:: Create or activate virtual environment
echo 🏗️  Setting up virtual environment...
if exist "venv" (
    echo Virtual environment already exists
    echo 🔄 Activating existing environment...
    call venv\Scripts\activate.bat
    if %errorlevel% neq 0 (
        echo ❌ Failed to activate existing environment
        echo 🗑️  Removing corrupted environment...
        rmdir /s /q venv
        goto create_new_venv
    )
    echo ✅ Virtual environment activated
) else (
    :create_new_venv
    echo 🔄 Creating new virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ Failed to create virtual environment
        echo.
        echo Possible solutions:
        echo - Run as Administrator
        echo - Check Python installation
        echo - Ensure you have write permissions in this directory
        echo.
        pause
        exit /b 1
    )
    echo ✅ Virtual environment created
    call venv\Scripts\activate.bat
    echo ✅ Virtual environment activated
)

:: Upgrade pip and essential tools
echo 📦 Upgrading pip and essential tools...
python -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo ⚠️  Warning: Failed to upgrade pip
)

python -m pip install --upgrade setuptools wheel
if %errorlevel% neq 0 (
    echo ⚠️  Warning: Failed to upgrade setuptools/wheel
)

echo ✅ Build tools updated

:: Install main requirements
echo 📋 Installing main requirements...
if exist "requirements.txt" (
    echo Installing from requirements.txt...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ⚠️  Some packages failed to install from requirements.txt
        echo Trying individual installation...
        
        :: Try installing core packages individually
        echo Installing core packages...
        python -m pip install PyQt5==5.15.9
        python -m pip install boto3==1.34.144
        python -m pip install mysql-connector-python==8.4.0
        python -m pip install getmac==0.9.4
        python -m pip install psutil==5.9.8
        python -m pip install cryptography==42.0.8
    )
    echo ✅ Main requirements installed
) else (
    echo ⚠️  requirements.txt not found, skipping main requirements
)

:: Install EXE build requirements
echo 🏗️  Installing EXE build requirements...
if exist "requirements-exe-build.txt" (
    echo Installing from requirements-exe-build.txt...
    python -m pip install -r requirements-exe-build.txt
    if %errorlevel% neq 0 (
        echo ⚠️  Some build packages failed to install
        echo Installing critical build tools...
        python -m pip install pyinstaller==6.3.0
        python -m pip install pyinstaller-hooks-contrib==2024.9
    )
    echo ✅ Build requirements installed
) else (
    echo ⚠️  requirements-exe-build.txt not found
    echo Installing PyInstaller manually...
    python -m pip install pyinstaller
)

:: Test installation
echo 🧪 Testing critical modules...
python -c "import PyQt5; print('✅ PyQt5: OK')" 2>nul || echo "❌ PyQt5: Failed"
python -c "import boto3; print('✅ boto3: OK')" 2>nul || echo "❌ boto3: Failed"
python -c "import mysql.connector; print('✅ mysql.connector: OK')" 2>nul || echo "❌ mysql.connector: Failed"
python -c "import getmac; print('✅ getmac: OK')" 2>nul || echo "❌ getmac: Failed"
python -c "import psutil; print('✅ psutil: OK')" 2>nul || echo "❌ psutil: Failed"
python -c "import PyInstaller; print('✅ PyInstaller: OK')" 2>nul || echo "❌ PyInstaller: Failed"

:: Check project files
echo 📁 Checking project files...
if exist "main.py" (
    echo ✅ main.py found
) else (
    echo ❌ main.py not found
)

if exist "config.enc" (
    echo ✅ config.enc found
) else (
    echo ⚠️  config.enc not found - needed for EXE to work
)

if exist "encryption_key.txt" (
    echo ✅ encryption_key.txt found
) else (
    echo ⚠️  encryption_key.txt not found - needed for EXE to work
)

for %%d in (ui database utils) do (
    if exist "%%d" (
        echo ✅ %%d directory found
    ) else (
        echo ❌ %%d directory not found
    )
)

:: Create startup script
echo 📝 Creating startup script...
(
echo @echo off
echo title AWS Uploader
echo cd /d "%~dp0"
echo call venv\Scripts\activate.bat
echo python main.py
echo pause
) > start_app.bat
echo ✅ Created start_app.bat

:: Summary
echo.
echo ========================================
echo 🎉 ENVIRONMENT SETUP COMPLETED!
echo ========================================
echo.
echo ✅ Virtual environment: Ready
echo ✅ Dependencies: Installed  
echo ✅ Build tools: Ready
echo.
echo 🚀 Next Steps:
echo 1. To run the app: start_app.bat
echo 2. To build EXE: build_exe.bat
echo 3. To fix issues: fix_missing_modules.bat
echo.
echo 💡 Tips:
echo - Keep this command window open to stay in the virtual environment
echo - If you close this window, use 'venv\Scripts\activate.bat' to reactivate
echo - All dependencies are installed in the virtual environment
echo.

echo Press any key to continue...
pause >nul 