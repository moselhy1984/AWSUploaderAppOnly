@echo off
echo Setting up AWS Uploader development environment for Windows

:: تحقق إذا كان Miniconda مثبت
where conda >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Miniconda is not installed.
    echo Please download and install Miniconda from:
    echo https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)

:: التحقق من وجود ملفات التشفير
echo Checking for encryption files...
if not exist "config.enc" (
    echo ERROR: Required encryption file 'config.enc' is missing!
    echo The application cannot be configured without this file.
    exit /b 1
)
if not exist "encryption_key.txt" (
    echo ERROR: Required encryption key file 'encryption_key.txt' is missing!
    echo The application cannot be configured without this file.
    exit /b 1
)
echo Encryption files found. Proceeding with setup...

:: إنشاء بيئة Conda
echo Creating AWS Uploader conda environment...
call conda create -n aws_app python=3.9 -y
if %ERRORLEVEL% neq 0 (
    echo Failed to create conda environment.
    exit /b 1
)

:: تنشيط البيئة وتثبيت الحزم المطلوبة
echo Installing required packages...
call conda activate aws_app
call conda install -c conda-forge pyqt=5 boto3 cryptography -y
call pip install mysql-connector-python getmac pyinstaller

:: إنشاء سكريبت تشغيل dev_run.bat
echo Creating dev_run.bat script...
(
    echo @echo off
    echo :: تنشيط بيئة conda
    echo call conda activate aws_app
    echo.
    echo :: تنظيف متغيرات البيئة
    echo set QT_PLUGIN_PATH=
    echo set QT_QPA_PLATFORM_PLUGIN_PATH=
    echo.
    echo :: ضبط مسار Qt
    echo FOR /F "tokens=*" %%a in ('conda info --base'^) do set CONDA_DIR=%%a
    echo set QT_PLUGIN_PATH=%%CONDA_DIR%%\envs\aws_app\Lib\site-packages\PyQt5\Qt5\plugins
    echo set QT_QPA_PLATFORM_PLUGIN_PATH=%%CONDA_DIR%%\envs\aws_app\Lib\site-packages\PyQt5\Qt5\plugins\platforms
    echo.
    echo :: التحقق من ملفات التشفير
    echo if not exist "config.enc" ^(
    echo     echo ERROR: Required encryption file 'config.enc' is missing!
    echo     echo The application cannot function without this file.
    echo     exit /b 1
    echo ^)
    echo if not exist "encryption_key.txt" ^(
    echo     echo ERROR: Required encryption key file 'encryption_key.txt' is missing!
    echo     echo The application cannot function without this file.
    echo     exit /b 1
    echo ^)
    echo echo Encryption files found. Starting application...
    echo.
    echo echo Starting AWS Uploader with Conda environment...
    echo python main.py
    echo.
    echo pause
) > dev_run.bat

echo Setup completed successfully!
echo To start the application in development mode, run: dev_run.bat

pause 