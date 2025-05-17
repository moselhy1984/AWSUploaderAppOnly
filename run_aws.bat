@echo off
echo Starting AWS Uploader application...
REM Configuración para cargar todas las tareas desde la base de datos
set LOAD_ALL_TASKS=1
set IGNORE_COMPLETED_TASKS=0
set LOAD_COMPLETED_TASKS=1
python main.py
pause
