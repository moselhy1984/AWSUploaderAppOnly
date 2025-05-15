#!/usr/bin/env python3
import re
import os
import sys

# Define Arabic to English translations
translations = {
    # In ui/uploader_gui.py
    "في الوضع الآمن، تعطيل بعض الميزات المتقدمة": "In safe mode, disable some advanced features",
    "تعطيل التشغيل التلقائي للمهام وتحميل الحالة": "Disable automatic task execution and state loading",
    "الحفاظ على إمكانية تحميل الحالة يدوياً": "Maintain the ability to load state manually",
    "خطأ أثناء تحميل سجل النشاطات": "Error loading activity log",
    "إجراء تنظيف للمعلّقة السابقة إذا وجدت": "Clean up previous thread if it exists",
    "ملف الحالة فارغ أو غير موجود": "State file is empty or does not exist",
    "ملف الحالة يفتقد إلى حقول مطلوبة": "State file is missing required fields",
    "تم إنشاء نسخة احتياطية": "Backup created",
    "إصلاح: قيمة total_files غير صالحة": "Fix: invalid total_files value",
    "إصلاح: قيمة current_file_index غير صالحة": "Fix: invalid current_file_index value",
    "إصلاح: current_file_index أكبر من total_files": "Fix: current_file_index is greater than total_files",
    "خطأ في تنسيق JSON للملف": "JSON format error in file",
    "محاولة الإصلاح": "Attempting to fix",
    "تم إصلاح ملف الحالة بإضافة قوس مفقود": "Fixed state file by adding missing bracket",
    "تم إصلاح ملف الحالة بإزالة فاصلة زائدة": "Fixed state file by removing extra comma",
    "فشل إصلاح ملف الحالة": "Failed to fix state file",
    "خطأ غير متوقع أثناء التحقق من ملف الحالة": "Unexpected error while checking state file",
    "تم نقل ملف الحالة المشكوك فيه": "Moved suspicious state file",
    "البحث عن ملفات الحالة في": "Searching for state files in",
    "تم العثور على": "Found",
    "من ملفات الحالة المحفوظة": "saved state files",
    "تجاهل ملف الحالة المشكوك فيه": "Ignoring suspicious state file",
    "تجاهل ملف الحالة التالف": "Ignoring corrupted state file",
    "رقم الطلب غير صالح في اسم الملف": "Invalid order number in filename",
    "جاري تحميل الحالة للمهمة رقم": "Loading state for order number",
    "خطأ في تحليل رقم الطلب من اسم الملف": "Error parsing order number from filename",
    "ملف الحالة ناقص للحقول الأساسية": "State file missing essential fields",
    "نوع رقم الطلب غير صحيح (مطلوب: نص)": "Order number type incorrect (required: text)",
    "غير معروف": "Unknown",
    "آخر تحديث للحالة": "Last state update",
    "تحذير: مسار الملفات غير موجود": "Warning: files path does not exist",
    "تم استعادة المهمة المتوقفة مؤقتًا للطلب": "Restored paused task for order",
    "من ملف الحالة": "from state file",
    "استئناف تلقائي للمهمة": "Auto-resuming task",
    "بعد إغلاق غير طبيعي": "after abnormal shutdown",
    "خطأ أثناء تحميل ملف الحالة": "Error loading state file",
    "لم يتم العثور على ملفات حالة محفوظة": "No saved state files found",
    "لم يFound ملفات حالة محفوظة": "No saved state files found",
    "مجلد حفظ الحالات غير موجود، جاري إنشاؤه": "State save directory doesn't exist, creating",
    "المتغير AUTO_RESUME مفعّل، جاري استئناف جميع المهام المتوقفة تلقائياً": "AUTO_RESUME is enabled, resuming all paused tasks automatically",
    "خطأ أثناء تحميل المهام": "Error loading tasks",
    "(بعد إعادة تشغيل التطبيق)": "(after application restart)",
    "إنشاء جدول upload_tasks جديد": "Creating new upload_tasks table",
    "تم إنشاء جدول upload_tasks بنجاح": "Successfully created upload_tasks table",
    "جدول المهام يستخدم عمود 'task_id' كمفتاح رئيسي": "Tasks table uses 'task_id' column as primary key",
    "جدول المهام يستخدم عمود 'id' كمفتاح رئيسي": "Tasks table uses 'id' column as primary key",
    "تحذير: لم يتم العثور على عمود المفتاح الرئيسي (id أو task_id) في الجدول": "Warning: Primary key column (id or task_id) not found in table",
    "تحذير: لم يFound عمود المفتاح الرئيسي (id أو task_id) في الجدول": "Warning: Primary key column (id or task_id) not found in table",
    "الأعمدة الموجودة": "Existing columns",
    "إضافة العمود الناقص": "Adding missing column",
    "خطأ أثناء إضافة العمود": "Error adding column",
    "إضافة الفهرس الناقص": "Adding missing index",
    "خطأ أثناء إضافة الفهرس": "Error adding index",
    "تم تهيئة جدول المهام بنجاح": "Tasks table initialized successfully",
    "خطأ أثناء تهيئة جدول المهام": "Error initializing tasks table",
    "تحذير: جدول الموظفين غير موجود": "Warning: Employees table doesn't exist",
    "تحذير: أعمدة اسم المستخدم/كلمة المرور غير موجودة بشكل كامل في جدول الموظفين": "Warning: Username/password columns not fully present in employees table",
    "عدد المستخدمين في قاعدة البيانات": "Number of users in database",
    "خطأ أثناء فحص بنية قاعدة البيانات": "Error checking database structure",
    "تأكد من استيراد QDate هنا": "Make sure to import QDate here",
    
    # In utils/background_uploader.py
    "متغير حالة الإيقاف المؤقت": "Pause state variable",
    "mutex للتزامن": "mutex for synchronization",
    "قائمة بالملفات التي تم تحميلها": "List of uploaded files",
    "مؤشر الملف الحالي للاستئناف": "Current file index for resuming",
    "استخدام QMutexLocker للتعامل الآمن مع المتغيرات المشتركة": "Using QMutexLocker for safe handling of shared variables",
    "خطأ: رقم الطلب مفقود، لا يمكن حفظ الحالة": "Error: Order number missing, cannot save state",
    "خطأ: مؤشر الملف غير صالح": "Error: Invalid file index",
    "خطأ أثناء تحويل الحالة إلى JSON": "Error converting state to JSON",
    "تحذير: فشل إنشاء نسخة احتياطية": "Warning: Failed to create backup",
    "تحذير: فشل حذف ملف الحالة القديم": "Warning: Failed to delete old state file",
    "تحذير: فشل استبدال ملف الحالة، استخدام النسخ كبديل": "Warning: Failed to replace state file, using copy as alternative",
    "خطأ أثناء النسخ البديل": "Error during alternative copy",
    "نجح: تم حفظ حالة التحميل للطلب": "Success: Upload state saved for order",
    "(المؤشر:": "(index:",
    "خطأ أثناء حفظ الحالة": "Error saving state",
    "لا يوجد ملف حالة محفوظ": "No saved state file exists",
    "ملف الحالة فارغ": "State file is empty",
    "خطأ في تنسيق ملف الحالة الأساسي": "Error in basic state file format",
    "محاولة استعادة الحالة من النسخة الاحتياطية": "Attempting to restore state from backup",
    "تم استعادة الحالة من النسخة الاحتياطية بنجاح": "State successfully restored from backup",
    "فشل استعادة الحالة من النسخة الاحتياطية": "Failed to restore state from backup",
    "محاولة استعادة الحالة من الملف المؤقت": "Attempting to restore state from temporary file",
    "تم استعادة الحالة من الملف المؤقت بنجاح": "State successfully restored from temporary file",
    "فشل استعادة الحالة من الملف المؤقت": "Failed to restore state from temporary file",
    "فشلت جميع محاولات استعادة الحالة": "All state restoration attempts failed",
    "ملف الحالة يفتقد حقول أساسية": "State file missing essential fields",
    "تحذير: خطأ أثناء تحميل تاريخ الطلب": "Warning: Error loading order date",
    "تحذير: لم يتم العثور على بيانات المصورين في ملف الحالة": "Warning: Photographer data not found in state file",
    "تحذير: لم يتم العثور على قائمة الملفات في ملف الحالة": "Warning: File list not found in state file",
    "تحذير: لم يFound بيانات المصورين في ملف الحالة": "Warning: Photographer data not found in state file",
    "تحذير: لم يFound قائمة الملفات في ملف الحالة": "Warning: File list not found in state file",
    "تم تحميل حالة التحميل للطلب": "Upload state loaded for order",
    "خطأ أثناء تحميل الحالة": "Error loading state",
    "بدء التحضير للتحميل": "Starting upload preparation",
    "استئناف من الحالة المحفوظة": "Resuming from saved state",
    "بدء عملية تحميل جديدة": "Starting new upload process",
    "بدء عملية تحميل جديدة بعد فشل تحميل الحالة": "Starting new upload process after state loading failure",
    "Starting new upload process بعد فشل Uploading الحالة": "Starting new upload process after state loading failure",
    "خطأ أثناء إنشاء اتصال AWS": "Error creating AWS connection",
    "خطأ أثناء إنشاء بنية المسار": "Error creating path structure",
    "استخدام بنية مسار بديلة": "Using alternative path structure",
    "تم الاتصال بالمستودع": "Connected to bucket",
    "خطأ: تم رفض الوصول. يرجى التحقق من أذونات AWS": "Error: Access denied. Please check AWS permissions",
    "خطأ: المستودع غير موجود. يرجى التحقق من اسم المستودع": "Error: Bucket does not exist. Please check bucket name",
    "خطأ AWS": "AWS error",
    "تنظيم الملفات حسب الامتداد قبل التحميل": "Organizing files by extension before upload",
    "خطأ أثناء تنظيم الملفات": "Error organizing files",
    "مسح المجلدات المحلية للحفاظ على البنية": "Scanning local folders to maintain structure",
    "مجلد الفئة": "Category folder",
    "غير موجود، تخطي": "doesn't exist, skipping",
    "معالجة مجلد": "Processing folder",
    "خطأ في الملف": "Error in file",
    "خطأ أثناء معالجة الفئة": "Error processing category",
    "ملف للمعالجة": "files to process",
    "ملف تم تحميله بالفعل في قاعدة البيانات": "files already uploaded in database",
    "خطأ أثناء استعلام قاعدة البيانات": "Error querying database",
    "استئناف التحميل مع": "Resuming upload with",
    "ملف، بدءًا من الملف": "files, starting from file",
    "لتخزين معلومات الملفات التي تم تحميلها للاحتفاظ بها في قاعدة البيانات": "to store uploaded files information to keep in the database",
    "تحذير: مؤشر الملف الحالي": "Warning: Current file index",
    "خارج النطاق، إعادة تعيين إلى 0": "out of range, resetting to 0",
    "تم إلغاء التحميل أثناء الإيقاف المؤقت": "Upload cancelled during pause",
    "تم إلغاء التحميل": "Upload cancelled",
    "تخطي الملف الذي تم تحميله مسبقًا": "Skipping previously uploaded file",
    "تحذير: الملف غير موجود، تخطي": "Warning: File doesn't exist, skipping",
    "تحذير: الملف doesn't exist, skipping": "Warning: File doesn't exist, skipping",
    "جاري تحميل": "Uploading",
    "إلى": "to",
    "تحميل": "Uploading",
    "بايت": "bytes",
    "تم تحميل": "Uploaded",
    "تم Uploading": "Uploaded",
    "خطأ أثناء تحميل": "Error uploading",
    "خطأ أثناء Uploading": "Error uploading",
    "خطأ في معالجة الملف في الفهرس": "Error processing file at index",
    "بدء تحميل للطلب": "Starting upload for order",
    "بدء تحميل جديد": "Starting new upload"
}

def process_file(file_path):
    """
    Process a file by replacing Arabic strings with English translations
    
    Args:
        file_path (str): Path to the file to process
        
    Returns:
        bool: True if changes were made, False otherwise
    """
    try:
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace Arabic strings with English
        modified_content = content
        for arabic, english in translations.items():
            modified_content = modified_content.replace(arabic, english)
        
        # Write back to file if changes were made
        if modified_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            return True
        
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False

def process_dir(dir_path):
    """
    Process all Python files in a directory recursively
    
    Args:
        dir_path (str): Path to the directory to process
        
    Returns:
        tuple: (files_count, changes_count) - number of files processed and number of files changed
    """
    changes_count = 0
    files_count = 0
    
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                files_count += 1
                if process_file(file_path):
                    changes_count += 1
                    print(f"✅ Translated Arabic text in: {file_path}")
                else:
                    print(f"No changes in: {file_path}")
    
    return files_count, changes_count

if __name__ == "__main__":
    dirs_to_process = ['ui', 'utils']
    total_files = 0
    total_changes = 0
    
    print("🌍 Starting Arabic to English translation process...")
    
    for dir_path in dirs_to_process:
        if os.path.exists(dir_path):
            print(f"\n📁 Processing directory: {dir_path}")
            files, changes = process_dir(dir_path)
            total_files += files
            total_changes += changes
        else:
            print(f"⚠️ Directory not found: {dir_path}")
    
    print(f"\n✨ Translation completed!")
    print(f"📊 Processed {total_files} Python files")
    print(f"📝 Made changes to {total_changes} files") 