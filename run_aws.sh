#!/bin/bash

# إعداد المتغيرات البيئية اللازمة لـ Qt
export QT_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/homebrew/opt/qt@5/plugins/platforms
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/qt@5/lib:$DYLD_LIBRARY_PATH
export PYTHONPATH=/opt/homebrew/lib/python3.13/site-packages:$PYTHONPATH

# تنشيط البيئة الافتراضية الموجودة
source .venv/bin/activate

# تأكد من تثبيت كل الحزم المطلوبة
pip install --quiet mysql-connector-python boto3 cryptography getmac

# تثبيت PyQt5 مع التأكد من الإعدادات الصحيحة
pip install --quiet PyQt5 --no-deps

# تحقق من وجود مشاكل في التشغيل السابق
CRASH_COUNT_FILE="$HOME/.aws_uploader/crash_count.txt"
CRASH_TIME_FILE="$HOME/.aws_uploader/last_crash.txt"
mkdir -p "$HOME/.aws_uploader"

# تحقق من عدد الانهيارات المتتالية
if [ -f "$CRASH_COUNT_FILE" ]; then
    CRASH_COUNT=$(cat "$CRASH_COUNT_FILE")
else
    CRASH_COUNT=0
fi

# وقت آخر انهيار
CURRENT_TIME=$(date +%s)
if [ -f "$CRASH_TIME_FILE" ]; then
    LAST_CRASH=$(cat "$CRASH_TIME_FILE")
    # إذا كان آخر انهيار منذ أكثر من ساعة، إعادة ضبط العداد
    TIME_DIFF=$((CURRENT_TIME - LAST_CRASH))
    if [ $TIME_DIFF -gt 3600 ]; then
        CRASH_COUNT=0
    fi
fi

# تعطيل استئناف المهام تلقائياً وتسجيل الدخول التلقائي
export AUTO_RESUME=0
export NO_AUTO_LOGIN=1

# حفظ وقت التشغيل الحالي
echo "$CURRENT_TIME" > "$HOME/.aws_uploader/last_run.txt"

# تشغيل التطبيق
python main.py

# التحقق من مخرجات التطبيق
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    # زيادة عداد الانهيارات
    CRASH_COUNT=$((CRASH_COUNT + 1))
    echo $CRASH_COUNT > "$CRASH_COUNT_FILE"
    echo "$CURRENT_TIME" > "$CRASH_TIME_FILE"
    echo "انهيار التطبيق برمز الخروج: $EXIT_CODE"
else
    # إعادة ضبط عداد الانهيارات في حالة الخروج الطبيعي
    echo "0" > "$CRASH_COUNT_FILE"
    echo "تم إغلاق التطبيق بشكل طبيعي."
fi 