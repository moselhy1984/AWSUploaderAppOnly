#!/bin/bash
# مشغل التطبيق مع حل مشكلة تضارب مكتبات Qt
# هذا السكريبت يمنع تداخل مكتبات Qt من مصادر مختلفة

echo "=================================================="
echo "  تشغيل تطبيق AWS Uploader مع حل تضارب المكتبات"
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

# سؤال المستخدم عن طريقة التشغيل
echo "اختر طريقة تشغيل التطبيق:"
echo "1. الوضع الآمن (بدون استئناف المهام التلقائي)"
echo "2. الوضع الكامل (مع استئناف المهام التلقائي)"
read -p "اختيارك (1/2): " choice

if [ "$choice" = "1" ]; then
    echo ""
    echo "تم اختيار الوضع الآمن..."
    # تعطيل استئناف المهام التلقائي وتحميل الحالة السابقة
    export NO_AUTO_RESUME=1
    export SKIP_STATE_LOAD=1
    echo "تم تعطيل استئناف المهام التلقائي وتحميل الحالة السابقة"
else
    echo ""
    echo "تم اختيار الوضع الكامل..."
    echo "تحذير: استئناف المهام التلقائي قد يسبب مشاكل في الذاكرة في بعض الحالات"
fi

echo ""
echo "جاري تشغيل التطبيق..."
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
    if [ "$choice" = "2" ]; then
        echo "حاول تشغيل التطبيق في الوضع الآمن بدلاً من ذلك (الخيار 1)"
    else
        echo "حاول تشغيل التطبيق بدون واجهة رسومية باستخدام ./run_core.sh"
    fi
    echo "=================================================="
else
    echo ""
    echo "=================================================="
    echo "تم إغلاق التطبيق بنجاح"
    echo "=================================================="
fi

exit $EXIT_CODE 