#!/bin/bash
# مشغل التطبيق من main.py مباشرة مع كل المميزات
# هذا السكريبت يضبط متغيرات البيئة لإصلاح تضارب مكتبات Qt مع تفعيل كل مهام التطبيق

echo "=================================================="
echo "    تشغيل تطبيق AWS Uploader بكامل المميزات"
echo "=================================================="
echo "جاري ضبط متغيرات البيئة لتجنب تضارب مكتبات Qt..."
echo "تم تفعيل استئناف المهام التلقائي وتحميل الحالة السابقة"
echo ""

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

# ملاحظة: تم إزالة متغيرات تعطيل المهام التلقائية:
# NO_AUTO_RESUME=1
# SKIP_STATE_LOAD=1

echo "تم ضبط مسار بلاجن Qt: $QT_PLUGIN_PATH"
echo "تم ضبط منصة Qt: cocoa"
echo "تحذير: تفعيل استئناف المهام التلقائي قد يؤدي إلى مشاكل في بعض الحالات"
echo ""
echo "جاري تشغيل التطبيق مباشرة من main.py مع كل المميزات..."
echo "=================================================="

# تشغيل التطبيق
python main.py

# إذا خرج التطبيق برمز خطأ، أبلغ المستخدم
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "=================================================="
    echo "خرج التطبيق برمز خطأ: $EXIT_CODE"
    echo "قد يكون السبب هو تفعيل استئناف المهام التلقائي."
    echo "للتشغيل بدون مشاكل، يرجى استخدام ./run_direct.sh بدلاً من ذلك."
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "تم إغلاق التطبيق بنجاح"
    echo "=================================================="
fi

exit $EXIT_CODE 