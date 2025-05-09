### خطوات إعداد وتشغيل البرنامج بعد تقسيمه

1. **إنشاء هيكل المجلدات**:
   قم بإنشاء هيكل المجلدات كما هو موضح أدناه:

   ```
   project/
   ├── main.py
   ├── config/
   │   ├── __init__.py
   │   └── secure_config.py
   ├── database/
   │   ├── __init__.py
   │   └── db_manager.py
   ├── ui/
   │   ├── __init__.py
   │   ├── login_dialog.py
   │   ├── uploader_gui.py
   │   ├── photographers_dialog.py
   │   ├── order_selector_dialog.py
   │   └── image_preview_dialog.py
   └── utils/
       ├── __init__.py
       └── background_uploader.py
   ```

2. **إنشاء ملفات __init__.py**:
   قم بإنشاء ملف `__init__.py` فارغ في كل مجلد فرعي:
   - `config/__init__.py`
   - `database/__init__.py`
   - `ui/__init__.py`
   - `utils/__init__.py`

3. **نقل الملفات**:
   قم بنقل الملفات المقسمة إلى المجلدات المناسبة كما هو موضح في الهيكل.

4. **تأكد من وجود ملفات التكوين**:
   تأكد من وجود ملفات التكوين `config.enc` و `encryption_key.txt` في المجلد الرئيسي للمشروع.

5. **تثبيت المكتبات المطلوبة**:
   قم بتثبيت المكتبات المطلوبة باستخدام pip:
   ```bash
   pip install PyQt5 boto3 mysql-connector-python cryptography getmac
   ```

6. **تشغيل البرنامج**:
   قم بتشغيل البرنامج من المجلد الرئيسي للمشروع:
   ```bash
   python main.py
   ```

### ملاحظات مهمة:

1. **ملف `ui/uploader_gui.py`**:
   لم يتم إكمال واجهة المستخدم الرئيسية، يجب استكمالها من الملف الأصلي.

2. **ملف الأيقونة**:
   تأكد من وجود ملف `icon.png` في المجلد الرئيسي للمشروع.

3. **الملفات المشفرة**:
   - `config.enc`: ملف التكوين المشفر
   - `encryption_key.txt`: مفتاح التشفير
   
   تأكد من أن هذه الملفات موجودة في نفس المجلد مع `main.py`.

4. **حقوق الوصول**:
   قد تحتاج إلى تغيير صلاحيات `main.py` ليصبح قابل للتنفيذ (في نظامي Linux و macOS):
   ```bash
   chmod +x main.py
   ```
