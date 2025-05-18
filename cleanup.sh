#!/bin/bash

# سكريبت لتنظيف المشروع وإزالة الملفات غير الضرورية
echo "بدء تنظيف المشروع..."

# حذف مجلدات الكاش
echo "حذف مجلدات الكاش..."
find . -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete
find . -name "*.pyd" -delete

# حذف ملفات السجلات
echo "حذف ملفات السجلات..."
rm -f optimized_run_log.txt
rm -f auto_resume_log.txt
rm -f app_log.txt

# حذف ملفات النسخ الاحتياطية
echo "حذف ملفات النسخ الاحتياطية..."
rm -f *.bak
rm -f main.py.bak
rm -f run_simple.sh.bak

# سكريبتات التشغيل غير المستخدمة (نحتفظ بـ run_aws.sh)
echo "حذف سكريبتات التشغيل غير المستخدمة..."
rm -f dev_run.sh
rm -f setup_windows.bat
rm -f build_dist.sh
rm -f alt_run.sh
rm -f run_optimized.sh
rm -f run_auto_resume.sh
rm -f run_smart.sh
rm -f run_both_qt.sh
rm -f run_full.sh
rm -f run_direct.sh
rm -f run_core.sh
rm -f run_headless.sh
rm -f run_app.sh
rm -f run_fixed.sh
rm -f run_safe.sh
rm -f run_simple.sh
rm -f setup_and_run.sh
rm -f run_app_system.sh

# حذف ملفات بايثون المساعدة غير المستخدمة (الإبقاء على الملفات الأساسية)
echo "حذف ملفات بايثون المساعدة غير المستخدمة..."
rm -f monitor_memory.py
rm -f db_task_resumer.py
rm -f create_optimized_script.py
rm -f memory_manager.py
rm -f task_auto_resume.py
rm -f task_restore.py
rm -f aws_core.py
rm -f app_runner.py
rm -f headless_patch.py
rm -f run_noqt.py
rm -f fix_conflicts.py
rm -f fixqt.py
rm -f run_safe.py
rm -f translate_arabic.py
rm -f monitor_employee_actions.py
rm -f check_activity.py
rm -f run_app.py

# حذف ملفات المستندات غير الأساسية (الاحتفاظ بـ README.md الرئيسي)
echo "حذف ملفات المستندات غير الأساسية..."
rm -f aws_uploader.spec
rm -f README_STABILITY.md
rm -f README_RUNNING.md
rm -f setup-and-run.md
rm -f هيكل\ الملفات\ المقترح.pdf
rm -f Readme.txt

# حذف ملفات وسائط كبيرة
echo "حذف ملفات الوسائط الكبيرة..."
rm -f miniconda.sh

# حذف ملفات .DS_Store (خاصة بنظام macOS)
echo "حذف ملفات .DS_Store..."
find . -name ".DS_Store" -delete

# ملفات هامة لا يجب حذفها:
# - main.py (الملف الرئيسي للتطبيق)
# - run_aws.sh (سكريبت تشغيل التطبيق)
# - requirements.txt (الاعتمادات)
# - qt.conf (إعدادات Qt)
# - encryption_key.txt و config.enc (ملفات التشفير والإعدادات)
# - icon.ico (أيقونة التطبيق)
# - المجلدات: .venv, ui, utils, config, database

echo "تم الانتهاء من تنظيف المشروع بنجاح!"
echo "الملفات والمجلدات المتبقية هي الضرورية لتشغيل التطبيق." 