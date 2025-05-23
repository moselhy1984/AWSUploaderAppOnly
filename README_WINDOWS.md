# تثبيت وتشغيل تطبيق رفع AWS على نظام ويندوز

## متطلبات النظام
- نظام ويندوز 10 أو 11
- Python 3.8 أو أحدث
- Git للويندوز

## خطوات التثبيت

### 1. تثبيت Python
1. قم بتحميل Python من الموقع الرسمي: https://www.python.org/downloads/windows/
2. تأكد من تفعيل خيار "Add Python to PATH" أثناء التثبيت
3. تحقق من التثبيت بفتح موجه الأوامر (CMD) وكتابة: `python --version`

### 2. تثبيت Git
1. قم بتحميل Git من: https://git-scm.com/download/win
2. ثبت Git باستخدام الخيارات الافتراضية
3. تحقق من التثبيت بفتح موجه الأوامر وكتابة: `git --version`

### 3. استنساخ المشروع
1. افتح موجه الأوامر (CMD) أو PowerShell
2. انتقل إلى المجلد حيث تريد حفظ المشروع باستخدام الأمر: `cd المسار\إلى\المجلد`
3. قم باستنساخ المشروع باستخدام:
   ```
   git clone https://github.com/moselhy1984/AWSUploaderAppOnly.git -b perfect_version
   cd AWSUploaderAppOnly
   ```

### 4. إنشاء بيئة افتراضية وتثبيت المكتبات
1. أنشئ بيئة افتراضية:
   ```
   python -m venv venv
   ```
2. قم بتفعيل البيئة الافتراضية:
   ```
   venv\Scripts\activate
   ```
3. قم بتثبيت المكتبات المطلوبة:
   ```
   pip install -r requirements.txt
   ```

## تشغيل التطبيق

### الطريقة 1: استخدام ملف الدفعة
1. قم بإنشاء ملف `run_aws.bat` في مجلد المشروع وأضف المحتوى التالي:
   ```batch
   @echo off
   echo Starting AWS Uploader application...
   
   if exist venv (
     call venv\Scripts\activate
   ) else (
     echo Creating virtual environment...
     python -m venv venv
     call venv\Scripts\activate
     pip install -r requirements.txt
   )
   
   python main.py
   ```
2. قم بتشغيل هذا الملف بالنقر المزدوج عليه

### الطريقة 2: التشغيل من سطر الأوامر
1. افتح موجه الأوامر (CMD) أو PowerShell
2. انتقل إلى مجلد المشروع:
   ```
   cd المسار\إلى\AWSUploaderAppOnly
   ```
3. قم بتفعيل البيئة الافتراضية:
   ```
   venv\Scripts\activate
   ```
4. قم بتشغيل التطبيق:
   ```
   python main.py
   ```

## المتغيرات البيئية والخيارات

يمكنك تعديل ملف التشغيل `run_aws.bat` لإضافة متغيرات بيئية للتحكم في سلوك التطبيق:

```batch
@echo off
echo Starting AWS Uploader application...

call venv\Scripts\activate

rem قم بإزالة التعليق عن أي من الخيارات التالية لتفعيلها
rem set SAFE_MODE=1
rem set SKIP_STATE_LOAD=1
rem set AUTO_RESUME=1
rem set LOAD_ALL_TASKS=1
rem set DISABLE_AUTO_LOGIN=1

python main.py
```

## استكشاف الأخطاء وإصلاحها

1. **مشكلة: "python غير معرّف كأمر داخلي"**  
   الحل: تأكد من إضافة Python إلى متغير PATH. يمكنك إعادة تثبيت Python مع تفعيل خيار "Add Python to PATH".

2. **مشكلة: خطأ عند تثبيت المكتبات**  
   الحل: قم بتحديث pip أولاً:
   ```
   python -m pip install --upgrade pip
   ```
   ثم حاول تثبيت المكتبات مرة أخرى.

3. **مشكلة: التطبيق لا يعمل**  
   الحل: تأكد من أن جميع ملفات المشروع موجودة. يمكنك محاولة تنظيف مجلد `__pycache__` وإعادة تشغيل التطبيق.

## ملاحظات هامة

- تأكد من وجود الإعدادات الصحيحة لـ AWS في ملف التكوين قبل محاولة الرفع الفعلية.
- إذا كنت تستخدم التطبيق في وضع آمن (SAFE_MODE=1)، فسيتم محاكاة عمليات الرفع دون إرسال أي ملفات فعلياً. 