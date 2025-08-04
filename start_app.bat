@echo off
title AWS Uploader
cd /d "D:\AWSAPPS\AWSUploaderAppOnly\"
call venv\Scripts\activate.bat
python main.py
pause
