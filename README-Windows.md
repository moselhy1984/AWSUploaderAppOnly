# 🖥️ AWS Uploader - دليل Windows

## 🎯 المشاكل الشائعة وحلولها

### ❌ **مشكلة: المهام لا تُحدث حالتها في قاعدة البيانات**

#### السبب الرئيسي:
المشكلة الأكثر شيوعاً على Windows هي **مشاكل اتصال SSL مع قاعدة البيانات MySQL**.

#### ✅ **الحلول المطبقة في التطبيق:**

1. **تعطيل SSL تلقائياً على Windows**:
   ```python
   'ssl_disabled': True  # يتم تلقائياً على Windows
   ```

2. **إعدادات خاصة بـ Windows**:
   ```python
   'use_pure': True,  # استخدام Python pure implementation
   'auth_plugin': 'mysql_native_password',
   'connection_timeout': 30  # وقت انتظار أطول
   ```

3. **إعادة المحاولة التلقائية**: 3 محاولات لكل اتصال

#### 🔍 **كيفية التشخيص:**

قم بتشغيل التطبيق ولاحظ الرسائل التالية:
```
🖥️ Database manager initialized for Windows
🔌 Attempting database connection on Windows...
✅ Connected to database with SSL disabled
```

إذا رأيت:
```
❌ SSL disabled connection failed
⚠️ SSL disabled connection failed: [خطأ SSL]
```

فهذا يعني أن المشكلة في إعدادات الشبكة أو Firewall.

---

## 🚀 **تشغيل التطبيق على Windows**

### الطريقة الأولى: ملف Batch (الأسهل)
```batch
double-click: run_windows.bat
```

### الطريقة الثانية: Command Prompt
```cmd
# تفعيل البيئة الافتراضية
venv\Scripts\activate

# تثبيت المتطلبات
pip install -r requirements-windows.txt

# تشغيل التطبيق
python main.py
```

---

## 🔧 **إعداد البيئة على Windows**

### 1. **تثبيت Python**
- تحميل Python 3.8+ من [python.org](https://python.org)
- ✅ تأكد من تفعيل "Add Python to PATH"

### 2. **تثبيت Visual C++ Build Tools** (للمكتبات التي تحتاج compilation)
```cmd
# إذا واجهت مشاكل في التثبيت
pip install --upgrade setuptools wheel
```

### 3. **إعداد Firewall**
تأكد من السماح للـ Python بالوصول للإنترنت:
- Windows Defender Firewall → Allow an app
- أضف `python.exe` من مجلد التثبيت

---

## 🐛 **استكشاف الأخطاء**

### **Error: SSL Connection Failed**
```
⚠️ SSL disabled connection failed: SSL connection error
```

**الحل:**
1. تحقق من إعدادات Firewall
2. تأكد من اتصال الإنترنت
3. جرب تشغيل Command Prompt كـ Administrator

### **Error: Module not found**
```
ModuleNotFoundError: No module named 'PyQt5'
```

**الحل:**
```cmd
pip install --upgrade pip
pip install -r requirements-windows.txt
```

### **Error: Database connection timeout**
```
❌ Database connection error on Windows: Connection timeout
```

**الحل:**
1. تحقق من إعدادات proxy إذا كنت في شركة
2. جرب استخدام VPN
3. تأكد من عدم حجب port 3306

---

## 📊 **رسائل التشخيص المفيدة**

عند تشغيل التطبيق، ابحث عن هذه الرسائل:

### ✅ **اتصال ناجح:**
```
🖥️ Database manager initialized for Windows
🔌 Attempting database connection on Windows...
✅ Connected to database with SSL disabled
🎯 TASK_FINISHED CALLED: Task ID 123
💾 About to save completion status to database...
📊 Query executed, affected rows: 1
```

### ❌ **مشكلة في الاتصال:**
```
❌ Database connection error on Windows: [خطأ]
🔧 Hint: SSL connection issue detected. This is common on Windows.
❌ CRITICAL: No database connection available after all retry attempts
```

### ⚠️ **تحذيرات مهمة:**
```
⚠️ Warning: Task [رقم] has no database ID, cannot update completion status
⚠️ Warning: No rows were updated. Task DB_ID may not exist in database
```

---

## 🔄 **التشغيل التلقائي عند بدء Windows**

التطبيق يدعم التشغيل التلقائي:

```python
from utils.windows_startup import WindowsStartup

startup = WindowsStartup()
startup.add_to_startup()  # إضافة للتشغيل التلقائي
startup.remove_from_startup()  # إزالة من التشغيل التلقائي
```

---

## 🎯 **نصائح للأداء الأفضل على Windows**

1. **تشغيل كـ Administrator** إذا واجهت مشاكل في الصلاحيات
2. **إغلاق Antivirus مؤقتاً** أثناء التثبيت الأول
3. **استخدام SSD** لتحسين سرعة قراءة الملفات
4. **تحديث Windows** للحصول على أحدث إصدارات .NET Framework

---

## 📞 **الحصول على المساعدة**

إذا استمرت المشاكل:

1. **قم بتشغيل التطبيق من Command Prompt** لرؤية جميع رسائل الخطأ
2. **احفظ log file** وشاركه مع فريق الدعم
3. **تحقق من إصدار Windows** - يفضل Windows 10/11
4. **جرب تشغيل** `run_windows.bat` **كـ Administrator**

### معلومات النظام المطلوبة للدعم:
```cmd
# تشغيل هذه الأوامر وإرسال النتائج
python --version
pip list | findstr PyQt5
pip list | findstr mysql
systeminfo | findstr "OS Name"
```

---

## ✅ **قائمة التحقق السريعة**

- [ ] Python 3.8+ مثبت
- [ ] pip يعمل بشكل صحيح
- [ ] requirements-windows.txt مثبت
- [ ] config.enc و encryption_key.txt موجودان  
- [ ] Firewall يسمح للـ Python
- [ ] اتصال إنترنت مستقر
- [ ] لا توجد برامج Antivirus تحجب التطبيق

**إذا كانت جميع النقاط ✅، التطبيق يجب أن يعمل بشكل مثالي على Windows!** 