#!/bin/bash

# سكريبت بديل لتشغيل التطبيق باستخدام Qt من نظام Homebrew

# استخدام بيئة Conda
eval "$(conda shell.bash hook)"
conda activate aws_app

# تنظيف متغيرات البيئة
unset QT_PLUGIN_PATH
unset QT_QPA_PLATFORM_PLUGIN_PATH
unset DYLD_LIBRARY_PATH
unset DYLD_FRAMEWORK_PATH

# استخدام Qt المثبتة بواسطة Homebrew
export QT_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins/platforms
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/qt@5/lib:$DYLD_LIBRARY_PATH
export DYLD_FRAMEWORK_PATH=/opt/homebrew/opt/qt@5/lib:$DYLD_FRAMEWORK_PATH

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
echo "Starting AWS Uploader with system Qt..."
echo "QT_PLUGIN_PATH = $QT_PLUGIN_PATH"
echo "QT_QPA_PLATFORM_PLUGIN_PATH = $QT_QPA_PLATFORM_PLUGIN_PATH"

# تشغيل التطبيق
python main.py 