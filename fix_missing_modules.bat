@echo off
title AWS Uploader - Fix Missing Modules
chcp 65001 >nul 2>&1
echo ========================================
echo 🔧 AWS Uploader - Module Fixer
echo ========================================
echo Fixing common module installation issues...
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found in PATH
    echo Please install Python and add it to PATH
    pause
    exit /b 1
)

echo ✅ Python found: 
python --version

:: Set encoding
set PYTHONIOENCODING=utf-8

:: Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo 🔄 Activating virtual environment...
    call venv\Scripts\activate.bat
)

echo.
echo 🔧 Method 1: Installing core modules individually...
echo ================================================

:: Install PyQt5 first (often problematic)
echo Installing PyQt5...
python -m pip install PyQt5==5.15.9 --no-cache-dir
if %errorlevel% neq 0 (
    echo ⚠️  PyQt5 installation failed, trying alternative...
    python -m pip install PyQt5 --user
)

:: Install other core modules
echo Installing getmac...
python -m pip install getmac==0.9.4 --no-cache-dir

echo Installing psutil...
python -m pip install psutil==5.9.8 --no-cache-dir

echo Installing mysql-connector-python...
python -m pip install mysql-connector-python==8.4.0 --no-cache-dir

echo Installing boto3...
python -m pip install boto3==1.34.144 --no-cache-dir

echo Installing cryptography...
python -m pip install cryptography==42.0.8 --no-cache-dir

echo Installing requests...
python -m pip install requests==2.32.3 --no-cache-dir

echo.
echo 🔧 Method 2: Installing from requirements...
echo ==========================================
if exist "requirements.txt" (
    python -m pip install -r requirements.txt --no-cache-dir
) else (
    echo ⚠️  requirements.txt not found
)

echo.
echo 🔧 Method 3: Installing build requirements...
echo ==========================================
if exist "requirements-exe-build.txt" (
    python -m pip install -r requirements-exe-build.txt --no-cache-dir
) else (
    echo ⚠️  requirements-exe-build.txt not found
)

echo.
echo 🔧 Method 4: Installing with pip upgrade...
echo =========================================
python -m pip install --upgrade pip setuptools wheel

echo.
echo 🧪 Testing installations...
echo =========================

:: Test PyQt5
python -c "import PyQt5; print('✅ PyQt5 OK')" 2>nul || echo "❌ PyQt5 failed"

:: Test getmac
python -c "import getmac; print('✅ getmac OK')" 2>nul || echo "❌ getmac failed"

:: Test mysql connector
python -c "import mysql.connector; print('✅ mysql.connector OK')" 2>nul || echo "❌ mysql.connector failed"

:: Test boto3
python -c "import boto3; print('✅ boto3 OK')" 2>nul || echo "❌ boto3 failed"

:: Test psutil
python -c "import psutil; print('✅ psutil OK')" 2>nul || echo "❌ psutil failed"

:: Test cryptography
python -c "import cryptography; print('✅ cryptography OK')" 2>nul || echo "❌ cryptography failed"

echo.
echo 📋 Installation Summary:
echo ======================
echo If you see ✅ for all modules above, you're ready to build!
echo If you see ❌ for any module, try running this script as Administrator.
echo.
echo 💡 Alternative solutions:
echo - Run as Administrator
echo - Check internet connection
echo - Temporarily disable antivirus
echo - Try: pip install --user [module_name]
echo.

pause 