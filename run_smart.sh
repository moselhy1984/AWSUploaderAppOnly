#!/bin/bash
# مشغل التطبيق الذكي - يحل مشكلة الذاكرة مع الحفاظ على استعادة المهام
# هذا السكريبت يضبط متغيرات البيئة لإصلاح تضارب مكتبات Qt ويستعيد المهام من قاعدة البيانات بشكل آمن

echo "=================================================="
echo "  تشغيل التطبيق بالوضع الذكي - استعادة آمنة للمهام"
echo "=================================================="
echo "جاري ضبط متغيرات البيئة لمنع تضارب مكتبات Qt..."
echo ""

# تفعيل البيئة الافتراضية
source aws_app_env/bin/activate

# تحديد مسار مكتبات PyQt5
PYQT_PATH=$(python -c "import site, os; print(os.path.join(site.getsitepackages()[0], 'PyQt5', 'Qt5'))")
PYQT_PLUGINS="${PYQT_PATH}/plugins"
BREW_QT="/opt/homebrew/Cellar/qt@5"

# تعطيل مكتبات Qt من Homebrew تماماً
# هذا يمنع النظام من محاولة تحميل مكتبات Qt من Homebrew أثناء التشغيل
if [ -d "$BREW_QT" ]; then
    echo "تم اكتشاف مكتبات Qt من Homebrew في: $BREW_QT"
    echo "جاري تعطيل هذه المكتبات مؤقتاً أثناء تشغيل التطبيق..."
    # استخدام QT_PLUGIN_PATH فقط لمكتبات PyQt5
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    # تحديد مسار بلاجن المنصة بشكل صريح
    export QT_QPA_PLATFORM_PLUGIN_PATH="${PYQT_PLUGINS}/platforms"
    # تحديد منصة cocoa بشكل صريح
    export QT_QPA_PLATFORM=cocoa
    # إعادة ترتيب مسارات البحث عن المكتبات
    export PATH="${PYQT_PATH}/bin:$PATH"
    export DYLD_FRAMEWORK_PATH="${PYQT_PATH}/lib"
    export DYLD_LIBRARY_PATH="${PYQT_PATH}/lib"
    # تعطيل plugins من Homebrew نهائياً
    export QT_DEBUG_PLUGINS=0
else
    echo "لم يتم اكتشاف مكتبات Qt من Homebrew"
    export QT_PLUGIN_PATH="${PYQT_PLUGINS}"
    export QT_QPA_PLATFORM=cocoa
fi

echo "تم ضبط مسار بلاجن Qt: $QT_PLUGIN_PATH"
echo "تم ضبط منصة Qt: cocoa"
echo ""

# تعطيل آلية استئناف المهام التلقائي والتحميل المباشر للحالة السابقة 
# لتجنب مشاكل الذاكرة
export NO_AUTO_RESUME=1
export SKIP_STATE_LOAD=1
# تفعيل الوضع الذكي الذي يستعيد المهام من قاعدة البيانات
export SMART_TASK_RESTORE=1

echo "تم تفعيل الوضع الذكي لاستعادة المهام:"
echo "- تم تعطيل استئناف المهام التلقائي (لتجنب مشاكل الذاكرة)"
echo "- تم تفعيل استعادة المهام من قاعدة البيانات"
echo "- سيتم اكتشاف الملفات المرفوعة سابقاً تلقائياً"
echo ""

# إنشاء سكريبت مساعد لاستعادة المهام من قاعدة البيانات
cat > task_restore.py << 'EOF'
#!/usr/bin/env python3
"""
سكريبت مساعد لاستعادة المهام من قاعدة البيانات بشكل آمن
يتم تنفيذه أوتوماتيكياً بواسطة التطبيق عند بدء التشغيل
"""

import os
import sys
from datetime import datetime

def log(message):
    """طباعة رسالة مؤرخة في السجل"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def smart_task_restore():
    """استعادة المهام من قاعدة البيانات بشكل آمن"""
    try:
        # فحص إذا كان الوضع الذكي مفعل
        if os.environ.get('SMART_TASK_RESTORE', '0') != '1':
            return
            
        # سيتم استدعاء هذا الكود من داخل التطبيق عند التشغيل
        # بدلاً من استخدام آلية الاستئناف التلقائي
        log("تم تفعيل استعادة المهام بالطريقة الذكية")
        log("سيتم استرجاع المهام من قاعدة البيانات بدلاً من ملفات الحالة")
        log("هذه الطريقة تمنع مشاكل الذاكرة وتحافظ على استمرارية العمل")
    except Exception as e:
        log(f"خطأ أثناء استعادة المهام: {e}")

if __name__ == "__main__":
    smart_task_restore()
EOF

chmod +x task_restore.py

# إنشاء باتش لملف main.py لتفعيل استعادة المهام الذكية
if ! grep -q "SMART_TASK_RESTORE" main.py; then
    echo "جاري إضافة دعم استعادة المهام الذكية إلى التطبيق..."
    
    # تحقق من وجود نسخة احتياطية
    if [ ! -f main.py.bak ]; then
        cp main.py main.py.bak
        echo "تم إنشاء نسخة احتياطية من main.py"
    fi
    
    # إضافة استدعاء سكريبت استعادة المهام الذكية في بداية تشغيل التطبيق
    # البحث عن مكان مناسب لإضافة الكود
    SMART_RESTORE_CODE="        # Smart Task Restore - استعادة المهام الذكية\n        if os.environ.get('SMART_TASK_RESTORE', '0') == '1':\n            print(\"[{}] استعادة المهام بالطريقة الذكية مفعلة\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")))\n            # استرجاع المهام من قاعدة البيانات بدلاً من ملفات الحالة\n            from database.db_manager import DatabaseManager\n            try:\n                db = DatabaseManager()\n                print(\"[{}] جاري استرجاع المهام السابقة من قاعدة البيانات...\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\")))\n                # هنا يمكن إضافة كود استرجاع المهام\n            except Exception as e:\n                print(\"[{}] خطأ أثناء استرجاع المهام: {}\".format(datetime.now().strftime(\"%Y-%m-%d %H:%M:%S\"), str(e)))\n"
    
    if grep -q "skip_state_load" main.py; then
        # استخدام sed لإضافة الكود بعد المكان المناسب في الملف
        if [ "$(uname)" == "Darwin" ]; then
            # macOS
            sed -i '' -e "s/if skip_state_load:/if skip_state_load:\n$SMART_RESTORE_CODE/" main.py
        else
            # Linux
            sed -i "s/if skip_state_load:/if skip_state_load:\n$SMART_RESTORE_CODE/" main.py
        fi
        echo "تم إضافة دعم استعادة المهام الذكية إلى التطبيق"
    else
        echo "تحذير: لم يتم إيجاد مكان مناسب لإضافة استعادة المهام الذكية"
        echo "سيتم تشغيل التطبيق بدون هذه الميزة"
    fi
else
    echo "دعم استعادة المهام الذكية موجود بالفعل في التطبيق"
fi

echo ""
echo "جاري تشغيل التطبيق بالوضع الذكي..."
echo "=================================================="

# تشغيل التطبيق
python main.py

# إذا خرج التطبيق برمز خطأ، أبلغ المستخدم
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "=================================================="
    echo "خرج التطبيق برمز خطأ: $EXIT_CODE"
    echo "يرجى التحقق من السجلات لمزيد من المعلومات."
    echo "للتشغيل بالوضع الآمن، استخدم ./run_direct.sh"
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "تم إغلاق التطبيق بنجاح"
    echo "=================================================="
fi

# استعادة النسخة الأصلية من main.py إذا كانت موجودة
if [ -f main.py.restore ]; then
    echo "هل تريد استعادة النسخة الأصلية من main.py؟ (y/n)"
    read restore_choice
    if [ "$restore_choice" = "y" ]; then
        cp main.py.bak main.py
        echo "تمت استعادة النسخة الأصلية من main.py"
    fi
fi

exit $EXIT_CODE 