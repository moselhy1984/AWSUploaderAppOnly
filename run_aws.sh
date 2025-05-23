#!/bin/bash

# إعداد متغيرات البيئة الخاصة بـ Qt
export QT_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins/platforms
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/qt@5/lib:$DYLD_LIBRARY_PATH
export PYTHONPATH=/opt/homebrew/lib/python3.13/site-packages:$PYTHONPATH

# تفعيل البيئة الافتراضية إذا كانت موجودة
if [ -d ".venv" ]; then
source .venv/bin/activate
fi

# تشغيل التطبيق
python main.py