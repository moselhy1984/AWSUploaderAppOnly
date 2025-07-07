@echo off
cls
chcp 65001 >nul 2>&1
title AWS Uploader - One-Click EXE Builder
echo ========================================
echo          AWS Uploader EXE Builder
echo             One-Click Solution
echo ========================================
echo.
echo 🚀 This will create a single EXE file from your Python app
echo ⏱️  Expected time: 5-15 minutes
echo 📦 Final size: ~50-70 MB
echo.
echo Prerequisites:
echo ✅ Python 3.8+ installed
echo ✅ All project files present
echo ✅ Internet connection for downloading dependencies
echo.
echo Press any key to start building...
pause >nul

echo.
echo 🔧 Step 1: Installing PyInstaller...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ❌ Failed to install PyInstaller
    echo Trying alternative method...
    python -m pip install pyinstaller --user --quiet
    if %errorlevel% neq 0 (
        echo ❌ PyInstaller installation failed completely
        echo Please check your internet connection and Python installation
        pause
        exit /b 1
    )
)
echo ✅ PyInstaller installed

echo.
echo 🏗️  Step 2: Building EXE file...
echo This will take several minutes, please wait...

:: Create a simple spec for one-file build
pyinstaller --onefile --windowed --icon=Uploadicon.ico --name="AWS_Uploader" main.py >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Build failed with onefile method
    echo Trying alternative build method...
    
    :: Try without onefile option
    pyinstaller --windowed --icon=Uploadicon.ico --name="AWS_Uploader" main.py >nul 2>&1
    if %errorlevel% neq 0 (
        echo ❌ Build failed completely
        echo.
        echo Common issues:
        echo - Missing dependencies
        echo - Insufficient disk space
        echo - Antivirus interference
        echo.
        echo Try running build_exe.bat for detailed error information
        pause
        exit /b 1
    )
)

echo ✅ Build completed

echo.
echo 🔍 Step 3: Checking results...
if exist "dist\AWS_Uploader.exe" (
    echo ✅ SUCCESS! EXE file created at: dist\AWS_Uploader.exe
    
    :: Get file size
    for %%F in ("dist\AWS_Uploader.exe") do (
        set /a "size_mb=%%~zF / 1024 / 1024"
        echo 📊 File size: !size_mb! MB
    )
    
    echo.
    echo 📁 IMPORTANT: Don't forget to include these files with your EXE:
    echo    ✅ config.enc (configuration file)
    echo    ✅ encryption_key.txt (encryption key)
    echo    ✅ Uploadicon.ico (application icon)
    echo.
    echo 💡 For easy distribution, copy these files to the dist folder:
    if exist "config.enc" (
        copy "config.enc" "dist\" >nul 2>&1
        echo    ✅ Copied config.enc to dist\
    ) else (
        echo    ⚠️  config.enc not found - copy manually
    )
    
    if exist "encryption_key.txt" (
        copy "encryption_key.txt" "dist\" >nul 2>&1
        echo    ✅ Copied encryption_key.txt to dist\
    ) else (
        echo    ⚠️  encryption_key.txt not found - copy manually
    )
    
    if exist "Uploadicon.ico" (
        copy "Uploadicon.ico" "dist\" >nul 2>&1
        echo    ✅ Copied Uploadicon.ico to dist\
    ) else (
        echo    ⚠️  Uploadicon.ico not found - copy manually
    )
    
    echo.
    echo 🎯 Your EXE is ready! Location: dist\AWS_Uploader.exe
    echo.
    
    set /p open_folder="Open dist folder to see your EXE? (y/n): "
    if /i "!open_folder!"=="y" (
        explorer dist
        echo ✅ Opened dist folder
    )
    
    echo.
    set /p test_exe="Test the EXE now? (y/n): "
    if /i "!test_exe!"=="y" (
        echo 🧪 Testing EXE...
        start "" "dist\AWS_Uploader.exe"
        echo ✅ EXE launched for testing
    )
    
) else (
    echo ❌ FAILED! EXE file was not created
    echo.
    echo The build process completed but no EXE was found.
    echo This usually means there were errors during compilation.
    echo.
    echo 💡 Troubleshooting steps:
    echo 1. Check if all Python modules are installed
    echo 2. Try running: fix_missing_modules.bat
    echo 3. Try the advanced builder: build_exe.bat
    echo 4. Run as Administrator
    echo.
    echo For detailed error information, run build_exe.bat instead
)

echo.
echo ========================================
echo 📋 Build Summary:
echo ========================================
if exist "dist\AWS_Uploader.exe" (
    echo Status: ✅ SUCCESS
    echo Location: dist\AWS_Uploader.exe
    echo Ready for distribution: YES
) else (
    echo Status: ❌ FAILED
    echo Location: Not created
    echo Ready for distribution: NO
)

echo.
echo 💡 Next steps:
echo 1. Test your EXE thoroughly
echo 2. Copy all required files together
echo 3. Test on another computer
echo 4. Distribute to users
echo.

echo Press any key to exit...
pause >nul 