#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from pathlib import Path
from utils.smart_file_copier import SmartFileCopier, FileCopyManager

class SmartCopierTestDialog(QDialog):
    """واجهة اختبار نظام النقل الذكي"""
    
    def __init__(self):
        super().__init__()
        self.copy_manager = FileCopyManager()
        self.active_copier = None
        self.setup_ui()
        
    def setup_ui(self):
        """إعداد واجهة الاختبار"""
        self.setWindowTitle("🚀 Smart File Copier Test")
        self.setModal(True)
        self.resize(900, 700)
        
        layout = QVBoxLayout()
        
        # شريط العنوان
        header = QLabel("🚀 Smart File Copier System Test")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 20px; background: #f0f0f0;")
        layout.addWidget(header)
        
        # قسم إعدادات النقل
        settings_group = QGroupBox("📁 Copy Settings")
        settings_layout = QGridLayout()
        
        # مسار المصدر
        settings_layout.addWidget(QLabel("Source Path:"), 0, 0)
        self.source_path_edit = QLineEdit()
        self.source_browse_btn = QPushButton("📁 Browse")
        self.source_browse_btn.clicked.connect(self.browse_source)
        
        source_layout = QHBoxLayout()
        source_layout.addWidget(self.source_path_edit)
        source_layout.addWidget(self.source_browse_btn)
        settings_layout.addLayout(source_layout, 0, 1)
        
        # مسار الوجهة
        settings_layout.addWidget(QLabel("Destination Path:"), 1, 0)
        self.dest_path_edit = QLineEdit()
        self.dest_browse_btn = QPushButton("📁 Browse")
        self.dest_browse_btn.clicked.connect(self.browse_destination)
        
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(self.dest_path_edit)
        dest_layout.addWidget(self.dest_browse_btn)
        settings_layout.addLayout(dest_layout, 1, 1)
        
        # خيارات النقل
        options_layout = QHBoxLayout()
        
        self.verify_check = QCheckBox("Verify files")
        self.verify_check.setChecked(True)
        
        self.delete_source_check = QCheckBox("Delete source after copy")
        self.delete_source_check.setChecked(False)
        
        self.overwrite_check = QCheckBox("Overwrite existing")
        self.overwrite_check.setChecked(False)
        
        options_layout.addWidget(self.verify_check)
        options_layout.addWidget(self.delete_source_check)
        options_layout.addWidget(self.overwrite_check)
        options_layout.addStretch()
        
        settings_layout.addLayout(options_layout, 2, 0, 1, 2)
        
        # فلاتر الملفات
        settings_layout.addWidget(QLabel("File Filters:"), 3, 0)
        self.filters_edit = QLineEdit(".jpg,.jpeg,.cr2,.cr3,.mp4,.mov")
        self.filters_edit.setPlaceholderText("e.g., .jpg,.cr2,.mp4 (leave empty for all files)")
        settings_layout.addWidget(self.filters_edit, 3, 1)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # أزرار التحكم
        control_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("🚀 Start Copy")
        self.start_btn.clicked.connect(self.start_copy)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.clicked.connect(self.pause_copy)
        self.pause_btn.setEnabled(False)
        
        self.resume_btn = QPushButton("▶️ Resume")
        self.resume_btn.clicked.connect(self.resume_copy)
        self.resume_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton("⏹️ Cancel")
        self.cancel_btn.clicked.connect(self.cancel_copy)
        self.cancel_btn.setEnabled(False)
        
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.resume_btn)
        control_layout.addWidget(self.cancel_btn)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # شريط التقدم العام
        progress_group = QGroupBox("📊 Copy Progress")
        progress_layout = QVBoxLayout()
        
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(True)
        
        self.status_label = QLabel("Ready to copy...")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        progress_layout.addWidget(self.overall_progress)
        progress_layout.addWidget(self.status_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # منطقة اللوج
        log_group = QGroupBox("📝 Copy Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(200)
        self.log_area.setReadOnly(True)
        
        # أزرار اللوج
        log_buttons = QHBoxLayout()
        
        self.clear_log_btn = QPushButton("🗑️ Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        
        self.save_log_btn = QPushButton("💾 Save Log")
        self.save_log_btn.clicked.connect(self.save_log)
        
        log_buttons.addWidget(self.clear_log_btn)
        log_buttons.addWidget(self.save_log_btn)
        log_buttons.addStretch()
        
        log_layout.addWidget(self.log_area)
        log_layout.addLayout(log_buttons)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # إحصائيات النقل
        stats_group = QGroupBox("📈 Copy Statistics")
        stats_layout = QGridLayout()
        
        self.stats_labels = {
            'total_files': QLabel("0"),
            'copied_files': QLabel("0"),
            'skipped_files': QLabel("0"),
            'failed_files': QLabel("0"),
            'total_size': QLabel("0 B"),
            'copied_size': QLabel("0 B"),
            'speed': QLabel("0 MB/s"),
            'eta': QLabel("--:--")
        }
        
        stats_layout.addWidget(QLabel("Total Files:"), 0, 0)
        stats_layout.addWidget(self.stats_labels['total_files'], 0, 1)
        stats_layout.addWidget(QLabel("Copied:"), 0, 2)
        stats_layout.addWidget(self.stats_labels['copied_files'], 0, 3)
        
        stats_layout.addWidget(QLabel("Skipped:"), 1, 0)
        stats_layout.addWidget(self.stats_labels['skipped_files'], 1, 1)
        stats_layout.addWidget(QLabel("Failed:"), 1, 2)
        stats_layout.addWidget(self.stats_labels['failed_files'], 1, 3)
        
        stats_layout.addWidget(QLabel("Total Size:"), 2, 0)
        stats_layout.addWidget(self.stats_labels['total_size'], 2, 1)
        stats_layout.addWidget(QLabel("Copied Size:"), 2, 2)
        stats_layout.addWidget(self.stats_labels['copied_size'], 2, 3)
        
        stats_layout.addWidget(QLabel("Speed:"), 3, 0)
        stats_layout.addWidget(self.stats_labels['speed'], 3, 1)
        stats_layout.addWidget(QLabel("ETA:"), 3, 2)
        stats_layout.addWidget(self.stats_labels['eta'], 3, 3)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # زر الإغلاق
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        
        # متغيرات الإحصائيات
        self.start_time = None
        self.copied_bytes = 0
        
    def browse_source(self):
        """اختيار مجلد المصدر"""
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_path_edit.setText(folder)
            
    def browse_destination(self):
        """اختيار مجلد الوجهة"""
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.dest_path_edit.setText(folder)
            
    def start_copy(self):
        """بدء عملية النقل"""
        
        # التحقق من المدخلات
        source = self.source_path_edit.text().strip()
        destination = self.dest_path_edit.text().strip()
        
        if not source:
            QMessageBox.warning(self, "Error", "Please select source folder")
            return
            
        if not destination:
            QMessageBox.warning(self, "Error", "Please select destination folder")
            return
            
        source_path = Path(source)
        if not source_path.exists():
            QMessageBox.warning(self, "Error", "Source folder does not exist")
            return
            
        # إعداد فلاتر الملفات
        filters_text = self.filters_edit.text().strip()
        file_filters = []
        if filters_text:
            file_filters = [ext.strip().lower() for ext in filters_text.split(',') if ext.strip()]
            
        try:
            # إنشاء المُنسخ
            self.active_copier = SmartFileCopier(source, destination, file_filters)
            
            # تطبيق الإعدادات
            self.active_copier.set_verification(self.verify_check.isChecked())
            self.active_copier.set_delete_source(self.delete_source_check.isChecked())
            self.active_copier.set_overwrite_existing(self.overwrite_check.isChecked())
            
            # ربط الإشارات
            self.active_copier.progress_updated.connect(self.on_progress_updated)
            self.active_copier.file_copied.connect(self.on_file_copied)
            self.active_copier.file_skipped.connect(self.on_file_skipped)
            self.active_copier.file_failed.connect(self.on_file_failed)
            self.active_copier.copy_completed.connect(self.on_copy_completed)
            
            # بدء النقل
            self.active_copier.start()
            
            # تحديث حالة الأزرار
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            
            # تسجيل وقت البداية
            from datetime import datetime
            self.start_time = datetime.now()
            self.copied_bytes = 0
            
            self.log_message("🚀 Copy operation started")
            self.status_label.setText("Copy in progress...")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start copy: {str(e)}")
            
    def pause_copy(self):
        """إيقاف مؤقت للنقل"""
        if self.active_copier:
            self.active_copier.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.log_message("⏸️ Copy paused")
            self.status_label.setText("Copy paused")
            
    def resume_copy(self):
        """استكمال النقل"""
        if self.active_copier:
            self.active_copier.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.log_message("▶️ Copy resumed")
            self.status_label.setText("Copy in progress...")
            
    def cancel_copy(self):
        """إلغاء النقل"""
        if self.active_copier:
            self.active_copier.cancel()
            self.active_copier.wait()  # انتظار انتهاء الـ thread
            self.active_copier = None
            
            # إعادة تعيين الأزرار
            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            
            self.log_message("⏹️ Copy cancelled")
            self.status_label.setText("Copy cancelled")
            
    def on_progress_updated(self, progress, message):
        """تحديث شريط التقدم"""
        self.overall_progress.setValue(progress)
        self.status_label.setText(message)
        
    def on_file_copied(self, source, destination, size):
        """عند نسخ ملف بنجاح"""
        self.copied_bytes += size
        
        # تحديث الإحصائيات
        current_copied = int(self.stats_labels['copied_files'].text()) + 1
        self.stats_labels['copied_files'].setText(str(current_copied))
        self.stats_labels['copied_size'].setText(self.format_size(self.copied_bytes))
        
        # حساب السرعة والوقت المتبقي
        if self.start_time:
            from datetime import datetime
            elapsed = (datetime.now() - self.start_time).total_seconds()
            if elapsed > 0:
                speed = self.copied_bytes / elapsed / (1024 * 1024)  # MB/s
                self.stats_labels['speed'].setText(f"{speed:.1f} MB/s")
                
        file_name = Path(source).name
        self.log_message(f"✅ Copied: {file_name} ({self.format_size(size)})")
        
    def on_file_skipped(self, file_path, reason):
        """عند تجاهل ملف"""
        current_skipped = int(self.stats_labels['skipped_files'].text()) + 1
        self.stats_labels['skipped_files'].setText(str(current_skipped))
        
        file_name = Path(file_path).name
        self.log_message(f"⏭️ Skipped: {file_name} - {reason}")
        
    def on_file_failed(self, file_path, error):
        """عند فشل نسخ ملف"""
        current_failed = int(self.stats_labels['failed_files'].text()) + 1
        self.stats_labels['failed_files'].setText(str(current_failed))
        
        file_name = Path(file_path).name
        self.log_message(f"❌ Failed: {file_name} - {error}")
        
    def on_copy_completed(self, stats):
        """عند انتهاء النقل"""
        
        # تحديث الأزرار
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        # تحديث الإحصائيات النهائية
        self.stats_labels['total_files'].setText(str(stats['total_files']))
        self.stats_labels['copied_files'].setText(str(stats['copied_files']))
        self.stats_labels['skipped_files'].setText(str(stats['skipped_files']))
        self.stats_labels['failed_files'].setText(str(stats['failed_files']))
        self.stats_labels['total_size'].setText(self.format_size(stats['total_size']))
        self.stats_labels['copied_size'].setText(self.format_size(stats['copied_size']))
        
        # حساب الوقت الإجمالي
        if stats['start_time'] and stats['end_time']:
            duration = stats['end_time'] - stats['start_time']
            duration_str = str(duration).split('.')[0]  # إزالة الميكروثواني
        else:
            duration_str = "Unknown"
            
        self.overall_progress.setValue(100)
        self.status_label.setText("Copy completed!")
        
        # رسالة إنهاء مفصلة
        completion_msg = f"""
🎉 Copy operation completed!

📊 Final Statistics:
• Total Files: {stats['total_files']}
• Copied: {stats['copied_files']} files ({self.format_size(stats['copied_size'])})
• Skipped: {stats['skipped_files']} files
• Failed: {stats['failed_files']} files
• Duration: {duration_str}
"""
        
        self.log_message(completion_msg)
        
        # إظهار نافذة النتائج
        QMessageBox.information(self, "Copy Completed", completion_msg)
        
        self.active_copier = None
        
    def log_message(self, message):
        """إضافة رسالة للوج"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")
        
        # التمرير للأسفل
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def clear_log(self):
        """مسح اللوج"""
        self.log_area.clear()
        
    def save_log(self):
        """حفظ اللوج"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "copy_log.txt", "Text Files (*.txt)")
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_area.toPlainText())
                QMessageBox.information(self, "Success", f"Log saved to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save log: {str(e)}")
                
    def format_size(self, size_bytes):
        """تنسيق حجم الملف"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def main():
    """الدالة الرئيسية"""
    app = QApplication(sys.argv)
    
    # تطبيق الثيم
    app.setStyle('Fusion')
    
    dialog = SmartCopierTestDialog()
    dialog.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 