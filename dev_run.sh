#!/bin/bash

# استخدام بيئة Conda
eval "$(conda shell.bash hook)"
conda activate aws_app

# تنظيف متغيرات البيئة المتعلقة بـ Qt لمنع التعارض
unset QT_PLUGIN_PATH
unset QT_QPA_PLATFORM_PLUGIN_PATH
unset DYLD_LIBRARY_PATH
unset DYLD_FRAMEWORK_PATH

# ضبط مسار Qt plugins وتحديد منصة cocoa
export QT_PLUGIN_PATH=$(conda info --base)/envs/aws_app/lib/python3.9/site-packages/PyQt5/Qt5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=$(conda info --base)/envs/aws_app/lib/python3.9/site-packages/PyQt5/Qt5/plugins/platforms
export QT_QPA_PLATFORM=cocoa

# التأكد من وجود ملفات التشفير - إيقاف البرنامج إذا كانت غير موجودة
if [[ ! -f "config.enc" ]]; then
    echo "Error: Required encryption file 'config.enc' is missing!"
    echo "The application cannot function without this file."
    exit 1
fi

if [[ ! -f "encryption_key.txt" ]]; then
    echo "Error: Required encryption key file 'encryption_key.txt' is missing!"
    echo "The application cannot function without this file."
    exit 1
fi

echo "Encryption files found: config.enc and encryption_key.txt"

# طباعة رسالة تأكيد
echo "Starting AWS Uploader with Conda environment..."
echo "QT_PLUGIN_PATH = $QT_PLUGIN_PATH"
echo "QT_QPA_PLATFORM_PLUGIN_PATH = $QT_QPA_PLATFORM_PLUGIN_PATH"
echo "QT_QPA_PLATFORM = $QT_QPA_PLATFORM"

# تشغيل التطبيق
python main.py 