@echo off
title AWS Uploader - EXE Builder
chcp 65001 >nul 2>&1
echo ========================================
echo 🏗️  AWS Uploader - EXE Builder
echo ========================================
echo Building standalone executable for Windows...
echo.

:: Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python first from python.org
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo ✅ Python found
python --version

:: Set environment for better encoding
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Check if virtual environment exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo 🔄 Activating virtual environment...
    call venv\Scripts\activate.bat
    if %errorlevel% neq 0 (
        echo ❌ Failed to activate virtual environment
        goto create_venv
    )
    echo ✅ Virtual environment activated
) else (
    :create_venv
    echo 🔄 Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ❌ ERROR: Failed to create virtual environment
        echo.
        echo Possible solutions:
        echo - Run as Administrator
        echo - Check if Python is properly installed
        echo - Make sure you have write permissions
        echo.
        pause
        exit /b 1
    )
    echo ✅ Virtual environment created
    call venv\Scripts\activate.bat
    echo ✅ Virtual environment activated
)

:: Upgrade pip and essential tools
echo 🔧 Upgrading pip and build tools...
python -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo ⚠️  Warning: Failed to upgrade pip, continuing anyway...
)

:: Check if requirements file exists
if not exist "requirements-exe-build.txt" (
    echo ❌ ERROR: requirements-exe-build.txt not found
    echo.
    echo This file is required for EXE building.
    echo Please make sure you have the complete project files.
    echo.
    pause
    exit /b 1
)

:: Install EXE build requirements
echo 📦 Installing EXE build dependencies...
echo This may take a few minutes...
python -m pip install -r requirements-exe-build.txt
if %errorlevel% neq 0 (
    echo ❌ ERROR: Failed to install some dependencies
    echo.
    echo Trying alternative installation methods...
    
    :: Try with --user flag
    echo 🔄 Trying installation with --user flag...
    python -m pip install -r requirements-exe-build.txt --user
    if %errorlevel% neq 0 (
        echo ❌ ERROR: Alternative installation also failed
        echo.
        echo Please check:
        echo - Internet connection
        echo - Firewall/antivirus settings
        echo - Python installation
        echo.
        echo You can try running this manually:
        echo pip install -r requirements-exe-build.txt
        echo.
        pause
        exit /b 1
    )
)

echo ✅ Dependencies installed successfully

:: Check essential files
echo 🔍 Checking essential files...
if not exist "main.py" (
    echo ❌ ERROR: main.py not found
    echo This is the main application file and is required for building.
    pause
    exit /b 1
)
echo ✅ main.py found

if not exist "config.enc" (
    echo ⚠️  WARNING: config.enc not found
    echo This file will be needed for the EXE to work properly.
)

if not exist "encryption_key.txt" (
    echo ⚠️  WARNING: encryption_key.txt not found  
    echo This file will be needed for the EXE to work properly.
)

if not exist "Uploadicon.ico" (
    echo ⚠️  WARNING: Uploadicon.ico not found
    echo EXE will be built without an icon.
)

:: Check essential directories
for %%d in (ui database utils) do (
    if not exist "%%d" (
        echo ❌ ERROR: %%d directory not found
        echo This directory is required for the application.
        pause
        exit /b 1
    )
    echo ✅ %%d directory found
)

:: Run the build script
echo.
echo 🚀 Starting EXE build process...
echo ==============================
echo.
echo This will take 5-15 minutes depending on your system.
echo Please be patient and do not close this window.
echo.

python build_exe.py
set BUILD_EXIT_CODE=%errorlevel%

:: Check build results
echo.
echo ========================================
if %BUILD_EXIT_CODE% equ 0 (
    echo ✅ BUILD COMPLETED SUCCESSFULLY!
    echo ========================================
    echo.
    
    if exist "dist\AWS_Uploader.exe" (
        echo 📦 EXE created: dist\AWS_Uploader.exe
        
        :: Get file size
        for %%F in ("dist\AWS_Uploader.exe") do (
            set /a "size_mb=%%~zF / 1024 / 1024"
        )
        echo 📊 EXE Size: !size_mb! MB (approximately)
    )
    
    if exist "AWS_Uploader_Portable" (
        echo 📁 Portable package: AWS_Uploader_Portable\
        echo.
        echo 💡 The portable package contains everything needed for distribution:
        echo    - AWS_Uploader.exe
        echo    - config.enc
        echo    - encryption_key.txt  
        echo    - Uploadicon.ico
        echo    - README.txt
    )
    
    echo.
    echo 🎯 Next Steps:
    echo 1. Test the EXE: dist\AWS_Uploader.exe
    echo 2. For distribution: Use AWS_Uploader_Portable folder
    echo 3. Make sure to include all files when distributing
    echo.
    
    :: Ask if user wants to test the EXE
    set /p test_exe="Do you want to test the EXE now? (y/n): "
    if /i "!test_exe!"=="y" (
        echo 🧪 Testing EXE...
        if exist "dist\AWS_Uploader.exe" (
            start "" "dist\AWS_Uploader.exe"
            echo ✅ EXE launched for testing
        ) else (
            echo ❌ EXE file not found for testing
        )
    )
    
    :: Ask if user wants to open the portable folder
    set /p open_folder="Do you want to open the portable package folder? (y/n): "
    if /i "!open_folder!"=="y" (
        if exist "AWS_Uploader_Portable" (
            explorer "AWS_Uploader_Portable"
            echo ✅ Opened portable package folder
        ) else (
            echo ❌ Portable package folder not found
        )
    )
    
) else (
    echo ❌ BUILD FAILED!
    echo ========================================
    echo.
    echo The build process encountered errors.
    echo Please check the output above for details.
    echo.
    echo Common solutions:
    echo - Make sure all required files are present
    echo - Check internet connection for downloading dependencies
    echo - Try running as Administrator
    echo - Check available disk space (need 2-5 GB free)
    echo - Temporarily disable antivirus software
    echo.
    echo If problems persist, check the documentation or contact support.
)

echo.
echo ========================================
echo Press any key to close this window...
pause >nul 