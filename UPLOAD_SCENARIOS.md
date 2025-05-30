# سيناريوهات رفع الملفات - AWS Uploader

## نظرة عامة
يدعم التطبيق الآن سيناريوهات متعددة لرفع الملفات مع تنظيم تلقائي وتقارير مفصلة.

## إنشاء هيكل المجلدات التلقائي

### عند اختيار Order جديد
عند اختيار Order من قاعدة البيانات أو إدخال رقم Order جديد، يقوم التطبيق تلقائياً بإنشاء هيكل المجلدات التالي:

```
📁 Order_123456/
├── 📷 CR2/          (للصور الخام)
├── 🖼️ JPG/          (للصور المعدلة)
├── 🎬 Reels/Videos/ (للفيديوهات)
├── 📄 OTHER/        (للملفات الأخرى)
└── 🗃️ Archive/      (للملفات المتجاهلة) ✨ جديد!
```

**المزايا**:
- ✅ **إنشاء تلقائي**: لا حاجة لإنشاء المجلدات يدوياً
- ✅ **هيكل موحد**: نفس التنظيم لجميع الطلبات
- ✅ **مجلد Archive جاهز**: متوفر فوراً لحفظ الملفات غير المرغوب برفعها

## السيناريوهات المدعومة

### 1. الملفات المنظمة مسبقاً
```
📁 Order_123456/
├── 📷 CR2/
│   ├── IMG_001.cr2
│   └── IMG_002.cr3
├── 🖼️ JPG/
│   ├── IMG_001.jpg
│   └── IMG_002.png
├── 🎬 Reels/Videos/
│   ├── video1.mp4
│   └── video2.mov
└── 📄 OTHER/
    └── document.pdf
```
**النتيجة**: يتم رفع جميع الملفات مع الحفاظ على التنظيم الموجود.

### 2. الملفات غير المنظمة (Loose Files)
```
📁 Order_123456/
├── IMG_001.cr2
├── IMG_002.jpg
├── video1.mp4
├── document.pdf
└── photo.png
```
**العملية**:
1. **التنظيم التلقائي**: يتم إنشاء المجلدات وتوزيع الملفات
2. **النتيجة**:
```
📁 Order_123456/
├── 📷 CR2/
│   └── IMG_001.cr2
├── 🖼️ JPG/
│   ├── IMG_002.jpg
│   └── photo.png
├── 🎬 Reels/Videos/
│   └── video1.mp4
├── 📄 OTHER/
│   └── document.pdf
└── 🗃️ Archive/  (جاهز للاستخدام)
```

### 3. الملفات المختلطة
```
📁 Order_123456/
├── 📷 CR2/
│   └── IMG_001.cr2  (منظم مسبقاً)
├── IMG_002.jpg      (غير منظم)
├── video1.mp4       (غير منظم)
└── 🗃️ Archive/
    └── old_file.jpg (يتم تجاهله)
```
**العملية**:
1. **تنظيم الملفات غير المنظمة فقط**
2. **الحفاظ على الملفات المنظمة مسبقاً**
3. **تجاهل مجلد Archive**

## قواعد التنظيم

### امتدادات الملفات المدعومة

#### 📷 CR2 (Raw Images)
- `.cr2`, `.cr3`, `.nef`, `.arw`, `.raw`, `.dng`

#### 🖼️ JPG (Processed Images)  
- `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`, `.gif`, `.heic`, `.webp`

#### 🎬 Reels/Videos
- `.mp4`, `.mov`, `.avi`, `.wmv`, `.flv`, `.m4v`, `.mkv`, `.webm`, `.3gp`

#### 📄 OTHER
- جميع الامتدادات الأخرى

### الملفات المتجاهلة

#### 🗃️ مجلد Archive
- **جميع الملفات داخل مجلد Archive يتم تجاهلها**
- يمكن استخدامه لحفظ الملفات القديمة أو غير المرغوب برفعها

#### 🔧 ملفات النظام
- `.DS_Store` (macOS)
- `Thumbs.db` (Windows)
- `desktop.ini` (Windows)
- أي ملف يبدأ بنقطة (.)

## تقارير التنظيم والرفع

### تقرير المسح والتنظيم
```
==================================================
📊 SCAN AND ORGANIZATION REPORT
==================================================
📁 Total files scanned: 25
✅ Files ready for upload: 20
🗃️ Files skipped (Archive): 3
🔧 System files skipped: 2

📋 FILES BY CATEGORY:
  📂 CR2: 8 files (120.5 MB)
     └─ 5 already organized, 3 from loose files
     └─ Extensions: .cr2, .cr3
  📂 JPG: 10 files (45.2 MB)
     └─ 7 already organized, 3 from loose files
     └─ Extensions: .jpg, .png
  📂 Reels/Videos: 2 files (89.1 MB)
     └─ 2 organized from loose files
     └─ Extensions: .mp4

💾 Total upload size: 254.8 MB

🚀 UPLOAD STRATEGY:
  • All files will be uploaded to S3 with organized folder structure
  • Archive folder contents are ignored
  • System files (.DS_Store, etc.) are skipped
  • Progress will be tracked per file and by data volume
==================================================
```

### تقرير الرفع المفصل
```
📄 جارٍ رفع IMG_001.jpg (15/20)
   🖼️ النوع: JPG | الامتداد: .jpg | المصدر: organized
   📊 التقدم: 75.0% ملفات، 68.5% بيانات

IMG_001.jpg: 25.0% uploaded
IMG_001.jpg: 50.0% uploaded
IMG_001.jpg: 75.0% uploaded
IMG_001.jpg: 100.0% uploaded

✅ تم رفع IMG_001.jpg بنجاح!
   📈 التقدم الإجمالي: 75.0% ملفات، 70.2% بيانات (15/20)
```

### تقرير الانتهاء
```
==================================================
🎉 UPLOAD COMPLETED SUCCESSFULLY!
==================================================
📊 FINAL STATISTICS:
   ✅ Files uploaded: 18
   ⏭️ Files skipped: 2
   📁 Total processed: 20
   📈 Upload rate: 90.0%
   💾 Data uploaded: 245.3 MB

📂 UPLOAD BREAKDOWN BY CATEGORY:
   📷 CR2: 8 files (120.5 MB)
   🖼️ JPG: 8 files (35.7 MB)
   🎬 Reels/Videos: 2 files (89.1 MB)
==================================================
```

## مزايا النظام الجديد

### 🚀 **المرونة**
- يتعامل مع أي تنظيم للملفات
- ينظم الملفات غير المنظمة تلقائياً
- يحافظ على التنظيم الموجود

### 📊 **الشفافية**
- تقارير مفصلة لكل مرحلة
- معلومات واضحة عن كل ملف
- إحصائيات شاملة

### 🛡️ **الأمان**
- تجاهل مجلد Archive
- تخطي ملفات النظام
- معالجة الأخطاء المحسنة

### ⚡ **الأداء**
- تتبع دقيق للتقدم
- رفع محسن بالتوازي
- استئناف ذكي للمهام

## أمثلة عملية

### مثال 1: مجلد فوضوي
**قبل**:
```
📁 Wedding_Photos/
├── DSC_001.cr2
├── DSC_002.cr2
├── edited_001.jpg
├── edited_002.jpg
├── highlight_video.mp4
├── contract.pdf
└── .DS_Store
```

**بعد التنظيم**:
```
📁 Wedding_Photos/
├── 📷 CR2/
│   ├── DSC_001.cr2
│   └── DSC_002.cr2
├── 🖼️ JPG/
│   ├── edited_001.jpg
│   └── edited_002.jpg
├── 🎬 Reels/Videos/
│   └── highlight_video.mp4
├── 📄 OTHER/
│   └── contract.pdf
└── 🗃️ Archive/
```

### مثال 2: مجلد منظم جزئياً
**قبل**:
```
📁 Event_Photos/
├── 📷 CR2/
│   └── IMG_001.cr2
├── loose_photo.jpg
├── behind_scenes.mp4
└── 🗃️ Archive/
    └── old_version.jpg
```

**النتيجة**:
- `IMG_001.cr2` يبقى في مكانه
- `loose_photo.jpg` ينتقل إلى `JPG/`
- `behind_scenes.mp4` ينتقل إلى `Reels/Videos/`
- `old_version.jpg` يتم تجاهله (في Archive)

## الخلاصة
النظام الجديد يوفر مرونة كاملة في التعامل مع أي تنظيم للملفات، مع ضمان رفع جميع الملفات المطلوبة وتجاهل ما لا يجب رفعه، مع تقارير مفصلة وشفافية كاملة في العملية. 