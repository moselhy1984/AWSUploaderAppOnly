#!/bin/bash
# مشغل التطبيق من main.py مباشرة
# هذا السكريبت يضبط متغيرات البيئة لإصلاح تضارب مكتبات Qt

echo "=================================================="
echo "    تشغيل تطبيق AWS Uploader من main.py مباشرة"
echo "=================================================="
echo "جاري ضبط متغيرات البيئة لتجنب تضارب مكتبات Qt..."

# تفعيل البيئة الافتراضية
source aws_app_env/bin/activate

# تحديد متغيرات بيئة Qt بشكل صريح
# استخدام مكتبات PyQt5 فقط وتجاهل مكتبات Homebrew Qt
PYQT_PATH=$(python -c "import site, os; print(os.path.join(site.getsitepackages()[0], 'PyQt5', 'Qt5'))")

# ضبط مسارات بلاجن Qt ليستخدم فقط من PyQt5
export QT_PLUGIN_PATH="${PYQT_PATH}/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="${PYQT_PATH}/plugins/platforms"

# ضبط مسارات المكتبات لاستخدام PyQt5 فقط
export LD_LIBRARY_PATH="${PYQT_PATH}/lib:$LD_LIBRARY_PATH"
export DYLD_LIBRARY_PATH="${PYQT_PATH}/lib:$DYLD_LIBRARY_PATH"

# ضبط منصة qt
export QT_QPA_PLATFORM=cocoa

# إعدادات الأمان لتجنب مشاكل الذاكرة
export NO_AUTO_RESUME=1
export SKIP_STATE_LOAD=1

echo "تم ضبط مسار بلاجن Qt: $QT_PLUGIN_PATH"
echo "تم ضبط منصة Qt: cocoa"
echo ""
echo "جاري تشغيل التطبيق مباشرة من main.py..."
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
    echo "يمكنك تجربة تشغيل التطبيق باستخدام ./run_safe.sh كبديل."
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "تم إغلاق التطبيق بنجاح"
    echo "=================================================="
fi

exit $EXIT_CODE 