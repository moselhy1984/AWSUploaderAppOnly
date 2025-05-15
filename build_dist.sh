#!/bin/bash

# سكريبت بناء الإصدار النهائي من التطبيق للتوزيع

# استخدام بيئة Conda
eval "$(conda shell.bash hook)"
conda activate aws_app

# التحقق من وجود ملفات التشفير
if [[ ! -f "config.enc" ]]; then
    echo "Error: Required encryption file 'config.enc' is missing!"
    echo "The application cannot be built without this file."
    exit 1
fi

if [[ ! -f "encryption_key.txt" ]]; then
    echo "Error: Required encryption key file 'encryption_key.txt' is missing!"
    echo "The application cannot be built without this file."
    exit 1
fi

echo "Encryption files found. Proceeding with build..."

# تنظيف مجلدات البناء السابقة
echo "Cleaning previous build directories..."
rm -rf dist build

# بناء التطبيق باستخدام PyInstaller
echo "Building AWS Uploader distribution..."
pyinstaller aws_uploader.spec

# التحقق من نجاح البناء
if [[ $? -ne 0 ]]; then
    echo "Error: Build failed!"
    exit 1
fi

# انسخ ملفات التشفير إلى المجلد النهائي
echo "Copying encryption files to distribution folder..."
cp config.enc "dist/AWS Uploader/"
cp encryption_key.txt "dist/AWS Uploader/"

# إنشاء ملف للقراءة
echo "Creating README file..."
cat > "dist/AWS Uploader/README.txt" << EOF
AWS Uploader
=============

تطبيق تحميل الملفات إلى AWS S3

تم البناء: $(date)

تأكد من أن ملفات التشفير (config.enc و encryption_key.txt) موجودة في نفس مجلد التطبيق.
EOF

echo "Build completed successfully!"
echo "The application is available in: dist/AWS Uploader"
echo "For macOS, the application bundle is available at: dist/AWS Uploader.app" 