#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import hashlib
import time
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
import threading

class SmartFileCopier(QThread):
    """نظام نقل الملفات الذكي مع التحقق والمراقبة"""
    
    # إشارات للتواصل مع الواجهة
    progress_updated = pyqtSignal(int, str)  # نسبة الإنجاز، رسالة
    file_copied = pyqtSignal(str, str, int)  # مصدر، وجهة، حجم
    file_skipped = pyqtSignal(str, str)  # ملف، سبب
    file_failed = pyqtSignal(str, str)  # ملف، خطأ
    copy_completed = pyqtSignal(dict)  # إحصائيات النقل
    validation_progress = pyqtSignal(int, str)  # تقدم التحقق
    
    def __init__(self, source_path, destination_path, file_filters=None):
        super().__init__()
        
        self.source_path = Path(source_path)
        self.destination_path = Path(destination_path)
        self.file_filters = file_filters or []
        
        # إعدادات النقل
        self.chunk_size = 1024 * 1024  # 1MB chunks
        self.verification_enabled = True
        self.delete_source_after_copy = False
        self.overwrite_existing = False
        
        # إحصائيات النقل
        self.stats = {
            'total_files': 0,
            'total_size': 0,
            'copied_files': 0,
            'copied_size': 0,
            'skipped_files': 0,
            'failed_files': 0,
            'start_time': None,
            'end_time': None,
            'failed_list': [],
            'skipped_list': []
        }
        
        # حالة التحكم
        self.is_paused = False
        self.is_cancelled = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # نبدأ غير مُتوقف
        
    def set_verification(self, enabled):
        """تفعيل/إلغاء التحقق من الملفات"""
        self.verification_enabled = enabled
        
    def set_delete_source(self, enabled):
        """تفعيل/إلغاء حذف المصدر بعد النقل"""
        self.delete_source_after_copy = enabled
        
    def set_overwrite_existing(self, enabled):
        """تفعيل/إلغاء استبدال الملفات الموجودة"""
        self.overwrite_existing = enabled
        
    def pause(self):
        """إيقاف مؤقت للنقل"""
        self.is_paused = True
        self._pause_event.clear()
        
    def resume(self):
        """استكمال النقل"""
        self.is_paused = False
        self._pause_event.set()
        
    def cancel(self):
        """إلغاء النقل"""
        self.is_cancelled = True
        self._pause_event.set()  # للتأكد من عدم التوقف
        
    def run(self):
        """تنفيذ عملية النقل"""
        try:
            self.stats['start_time'] = datetime.now()
            
            # فحص المسارات
            if not self._validate_paths():
                return
                
            # اكتشاف الملفات للنقل
            files_to_copy = self._discover_files()
            if not files_to_copy:
                self.progress_updated.emit(100, "No files to copy")
                return
                
            self.stats['total_files'] = len(files_to_copy)
            self.stats['total_size'] = sum(f['size'] for f in files_to_copy)
            
            # بدء النقل
            self._copy_files(files_to_copy)
            
            # إنهاء العملية
            self.stats['end_time'] = datetime.now()
            self.copy_completed.emit(self.stats.copy())
            
        except Exception as e:
            self.file_failed.emit("Copy Operation", str(e))
            
    def _validate_paths(self):
        """فحص صحة المسارات"""
        if not self.source_path.exists():
            self.file_failed.emit(str(self.source_path), "Source path does not exist")
            return False
            
        if not self.source_path.is_dir():
            self.file_failed.emit(str(self.source_path), "Source is not a directory")
            return False
            
        # إنشاء مجلد الوجهة إذا لم يكن موجود
        try:
            self.destination_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.file_failed.emit(str(self.destination_path), f"Cannot create destination: {e}")
            return False
            
        return True
        
    def _discover_files(self):
        """اكتشاف الملفات للنقل"""
        files_to_copy = []
        
        self.progress_updated.emit(0, "Discovering files...")
        
        try:
            for file_path in self.source_path.rglob('*'):
                if self.is_cancelled:
                    break
                    
                if file_path.is_file():
                    # فحص الفلاتر
                    if self._should_copy_file(file_path):
                        try:
                            file_info = {
                                'source': file_path,
                                'relative_path': file_path.relative_to(self.source_path),
                                'size': file_path.stat().st_size,
                                'mtime': file_path.stat().st_mtime
                            }
                            files_to_copy.append(file_info)
                        except Exception as e:
                            self.file_failed.emit(str(file_path), f"Cannot read file info: {e}")
                            
        except Exception as e:
            self.file_failed.emit(str(self.source_path), f"Error discovering files: {e}")
            
        return files_to_copy
        
    def _should_copy_file(self, file_path):
        """فحص ما إذا كان يجب نقل الملف"""
        
        # تجاهل ملفات النظام
        if file_path.name.startswith('.'):
            return False
            
        # تطبيق الفلاتر
        if self.file_filters:
            file_ext = file_path.suffix.lower()
            if file_ext not in self.file_filters:
                return False
                
        return True
        
    def _copy_files(self, files_to_copy):
        """نقل الملفات"""
        
        copied_size = 0
        
        for i, file_info in enumerate(files_to_copy):
            if self.is_cancelled:
                break
                
            # انتظار في حالة الإيقاف المؤقت
            self._pause_event.wait()
            
            if self.is_cancelled:
                break
                
            source_file = file_info['source']
            destination_file = self.destination_path / file_info['relative_path']
            
            try:
                # إنشاء مجلدات الوجهة
                destination_file.parent.mkdir(parents=True, exist_ok=True)
                
                # فحص إذا كان الملف موجود
                if destination_file.exists() and not self.overwrite_existing:
                    # فحص إذا كان نفس الملف
                    if self._are_files_identical(source_file, destination_file):
                        self.file_skipped.emit(str(source_file), "Already exists (identical)")
                        self.stats['skipped_files'] += 1
                        self.stats['skipped_list'].append(str(source_file))
                        continue
                        
                # نقل الملف
                success = self._copy_single_file(source_file, destination_file, file_info['size'])
                
                if success:
                    copied_size += file_info['size']
                    self.stats['copied_files'] += 1
                    self.stats['copied_size'] += file_info['size']
                    
                    self.file_copied.emit(str(source_file), str(destination_file), file_info['size'])
                    
                    # حذف المصدر إذا كان مطلوب
                    if self.delete_source_after_copy:
                        try:
                            source_file.unlink()
                        except Exception as e:
                            self.file_failed.emit(str(source_file), f"Cannot delete source: {e}")
                            
                else:
                    self.stats['failed_files'] += 1
                    
                # تحديث التقدم
                progress = int((copied_size / self.stats['total_size']) * 100) if self.stats['total_size'] > 0 else 100
                self.progress_updated.emit(progress, f"Copying: {source_file.name}")
                
            except Exception as e:
                self.file_failed.emit(str(source_file), str(e))
                self.stats['failed_files'] += 1
                self.stats['failed_list'].append(str(source_file))
                
    def _copy_single_file(self, source, destination, file_size):
        """نقل ملف واحد مع التحقق"""
        
        try:
            # نقل الملف بالـ chunks
            with open(source, 'rb') as src, open(destination, 'wb') as dst:
                copied = 0
                while copied < file_size:
                    if self.is_cancelled:
                        return False
                        
                    # انتظار في حالة الإيقاف المؤقت
                    self._pause_event.wait()
                    
                    if self.is_cancelled:
                        return False
                        
                    chunk_size = min(self.chunk_size, file_size - copied)
                    chunk = src.read(chunk_size)
                    
                    if not chunk:
                        break
                        
                    dst.write(chunk)
                    copied += len(chunk)
                    
            # التحقق من النقل
            if self.verification_enabled:
                if not self._verify_copy(source, destination):
                    destination.unlink(missing_ok=True)  # حذف الملف المنقول الفاشل
                    self.file_failed.emit(str(source), "Verification failed")
                    return False
                    
            # نسخ معلومات الملف
            shutil.copystat(source, destination)
            
            return True
            
        except Exception as e:
            # حذف الملف المنقول جزئياً
            if destination.exists():
                destination.unlink(missing_ok=True)
            self.file_failed.emit(str(source), str(e))
            return False
            
    def _verify_copy(self, source, destination):
        """التحقق من صحة النقل"""
        
        try:
            # مقارنة الأحجام
            source_size = source.stat().st_size
            dest_size = destination.stat().st_size
            
            if source_size != dest_size:
                return False
                
            # مقارنة الـ hash (للملفات الصغيرة فقط)
            if source_size < 100 * 1024 * 1024:  # أقل من 100MB
                return self._compare_file_hashes(source, destination)
            else:
                # للملفات الكبيرة، نكتفي بمقارنة الحجم والوقت
                source_mtime = source.stat().st_mtime
                dest_mtime = destination.stat().st_mtime
                return abs(source_mtime - dest_mtime) < 2  # فرق ثانيتين مقبول
                
        except Exception:
            return False
            
    def _compare_file_hashes(self, file1, file2):
        """مقارنة hash الملفين"""
        
        try:
            hash1 = self._calculate_file_hash(file1)
            hash2 = self._calculate_file_hash(file2)
            return hash1 == hash2
        except Exception:
            return False
            
    def _calculate_file_hash(self, file_path):
        """حساب hash الملف"""
        
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(self.chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
        
    def _are_files_identical(self, file1, file2):
        """فحص إذا كان الملفان متطابقان"""
        
        try:
            stat1 = file1.stat()
            stat2 = file2.stat()
            
            # مقارنة الحجم
            if stat1.st_size != stat2.st_size:
                return False
                
            # مقارنة وقت التعديل
            if abs(stat1.st_mtime - stat2.st_mtime) < 2:  # فرق ثانيتين
                return True
                
            # مقارنة المحتوى للملفات الصغيرة
            if stat1.st_size < 10 * 1024 * 1024:  # أقل من 10MB
                return self._compare_file_hashes(file1, file2)
                
            return False
            
        except Exception:
            return False

class FileCopyManager:
    """مدير عمليات النقل المتعددة"""
    
    def __init__(self):
        self.active_copies = {}
        self.copy_history = []
        
    def start_copy(self, copy_id, source, destination, file_filters=None):
        """بدء عملية نقل جديدة"""
        
        if copy_id in self.active_copies:
            raise ValueError(f"Copy operation {copy_id} already active")
            
        copier = SmartFileCopier(source, destination, file_filters)
        self.active_copies[copy_id] = copier
        
        # ربط الإشارات
        copier.copy_completed.connect(lambda stats: self._on_copy_completed(copy_id, stats))
        
        copier.start()
        return copier
        
    def pause_copy(self, copy_id):
        """إيقاف مؤقت لعملية نقل"""
        if copy_id in self.active_copies:
            self.active_copies[copy_id].pause()
            
    def resume_copy(self, copy_id):
        """استكمال عملية نقل"""
        if copy_id in self.active_copies:
            self.active_copies[copy_id].resume()
            
    def cancel_copy(self, copy_id):
        """إلغاء عملية نقل"""
        if copy_id in self.active_copies:
            self.active_copies[copy_id].cancel()
            self.active_copies[copy_id].wait()  # انتظار انتهاء الـ thread
            del self.active_copies[copy_id]
            
    def get_active_copies(self):
        """الحصول على عمليات النقل النشطة"""
        return list(self.active_copies.keys())
        
    def _on_copy_completed(self, copy_id, stats):
        """عند انتهاء عملية نقل"""
        
        # إضافة للتاريخ
        self.copy_history.append({
            'copy_id': copy_id,
            'stats': stats,
            'completed_at': datetime.now()
        })
        
        # إزالة من النشطة
        if copy_id in self.active_copies:
            del self.active_copies[copy_id]

# إختبار سريع
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # إنشاء مدير النقل
    manager = FileCopyManager()
    
    print("Smart File Copier system initialized!")
    print("Ready for integration with main application.")
    
    app.quit() 