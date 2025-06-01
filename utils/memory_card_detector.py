#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psutil
import os
import platform
from pathlib import Path
from datetime import datetime
import time

class MemoryCardDetector:
    """نظام كشف كروت الميموري الذكي"""
    
    def __init__(self):
        self.camera_extensions = {
            'RAW': ['.cr2', '.cr3', '.nef', '.arw', '.raw', '.dng', '.orf', '.pef'],
            'JPEG': ['.jpg', '.jpeg', '.jpe'],
            'TIFF': ['.tif', '.tiff'],
            'PNG': ['.png'],
            'VIDEO': ['.mp4', '.mov', '.avi', '.mts', '.m2ts', '.mkv'],
            'OTHER': ['.bmp', '.gif', '.heic', '.webp']
        }
        
        self.camera_folders = [
            'DCIM', '100CANON', '100NIKON', '100SONY', '100OLYMP',
            'Pictures', 'PRIVATE', 'MP_ROOT', 'AVCHD'
        ]
        
        # أنظمة التشغيل المختلفة
        self.system = platform.system()
        
    def detect_all_cards(self):
        """كشف جميع كروت الميموري المتصلة"""
        cards = []
        
        try:
            # الحصول على جميع الأقراص المتصلة
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                if self.is_potential_memory_card(partition):
                    card_info = self.analyze_card(partition)
                    if card_info:
                        cards.append(card_info)
                        
        except Exception as e:
            print(f"Error detecting cards: {e}")
            
        return cards
        
    def is_potential_memory_card(self, partition):
        """فحص إذا كان القرص محتمل أن يكون كارت ميموري"""
        
        mount_point = partition.mountpoint
        opts = partition.opts if hasattr(partition, 'opts') else ''
        
        # macOS
        if self.system == 'Darwin':
            # كروت الميموري عادة تكون في /Volumes/
            if '/Volumes/' in mount_point:
                # تجاهل أقراص النظام المعروفة
                excluded_volumes = [
                    'Macintosh HD', 'Recovery', 'Preboot', 'VM', 'Update',
                    'Data', 'System', 'com.apple'
                ]
                
                volume_name = Path(mount_point).name
                
                for excluded in excluded_volumes:
                    if excluded.lower() in volume_name.lower():
                        return False
                        
                return True
                
        # Windows
        elif self.system == 'Windows':
            # فحص نوع القرص
            if 'removable' in opts.lower():
                return True
                
            # فحص أحرف الأقراص المحتملة (عادة D: وما بعدها)
            if len(mount_point) == 3 and mount_point[0].upper() >= 'D':
                return True
                
        # Linux
        elif self.system == 'Linux':
            # فحص نقاط التوصيل المعتادة
            if any(path in mount_point for path in ['/media/', '/mnt/', '/run/media/']):
                return True
                
            if 'removable' in opts.lower() or 'usb' in opts.lower():
                return True
                
        return False
        
    def analyze_card(self, partition):
        """تحليل شامل لكارت الميموري"""
        
        try:
            mount_point = Path(partition.mountpoint)
            
            # معلومات أساسية
            card_info = {
                'name': mount_point.name,
                'path': str(mount_point),
                'device': partition.device if hasattr(partition, 'device') else 'Unknown',
                'fstype': partition.fstype if hasattr(partition, 'fstype') else 'Unknown',
            }
            
            # معلومات المساحة
            try:
                usage = psutil.disk_usage(str(mount_point))
                card_info.update({
                    'total_size': usage.total,
                    'used_size': usage.used,
                    'free_size': usage.free,
                    'usage_percent': round((usage.used / usage.total) * 100, 1)
                })
            except Exception:
                card_info.update({
                    'total_size': 0,
                    'used_size': 0,
                    'free_size': 0,
                    'usage_percent': 0
                })
            
            # فحص محتوى الكاميرا
            camera_analysis = self.analyze_camera_content(mount_point)
            card_info.update(camera_analysis)
            
            # إذا لم نجد ملفات كاميرا، لا نعتبره كارت ميموري
            if camera_analysis['total_camera_files'] == 0:
                return None
                
            # معلومات إضافية
            card_info.update({
                'detected_at': datetime.now().isoformat(),
                'is_camera_card': True,
                'card_type': self.determine_card_type(mount_point, camera_analysis)
            })
            
            return card_info
            
        except Exception as e:
            print(f"Error analyzing card {partition.mountpoint}: {e}")
            return None
            
    def analyze_camera_content(self, card_path):
        """تحليل محتوى ملفات الكاميرا"""
        
        analysis = {
            'total_camera_files': 0,
            'total_camera_size': 0,
            'file_types': {},
            'folder_structure': [],
            'latest_file_date': None,
            'oldest_file_date': None,
            'sample_files': []
        }
        
        try:
            # البحث في المجلدات المحتملة
            search_paths = [card_path]
            
            # إضافة مجلدات DCIM المعروفة
            for folder_name in self.camera_folders:
                folder_path = card_path / folder_name
                if folder_path.exists() and folder_path.is_dir():
                    search_paths.append(folder_path)
                    analysis['folder_structure'].append(folder_name)
            
            file_dates = []
            
            # فحص كل مسار للبحث عن ملفات الكاميرا
            for search_path in search_paths:
                for file_path in search_path.rglob('*'):
                    if file_path.is_file():
                        
                        file_type, category = self.categorize_file(file_path)
                        
                        if category != 'UNKNOWN':  # ملف كاميرا معروف
                            try:
                                file_size = file_path.stat().st_size
                                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                                
                                analysis['total_camera_files'] += 1
                                analysis['total_camera_size'] += file_size
                                
                                # إحصائيات أنواع الملفات
                                if category not in analysis['file_types']:
                                    analysis['file_types'][category] = {'count': 0, 'size': 0}
                                
                                analysis['file_types'][category]['count'] += 1
                                analysis['file_types'][category]['size'] += file_size
                                
                                # تواريخ الملفات
                                file_dates.append(file_mtime)
                                
                                # عينات من الملفات (أول 10)
                                if len(analysis['sample_files']) < 10:
                                    analysis['sample_files'].append({
                                        'name': file_path.name,
                                        'path': str(file_path),
                                        'size': file_size,
                                        'type': category,
                                        'date': file_mtime.isoformat()
                                    })
                                    
                            except Exception as e:
                                continue  # تجاهل الملفات التي لا يمكن قراءتها
            
            # حساب نطاق التواريخ
            if file_dates:
                analysis['latest_file_date'] = max(file_dates).isoformat()
                analysis['oldest_file_date'] = min(file_dates).isoformat()
                
        except Exception as e:
            print(f"Error analyzing camera content: {e}")
            
        return analysis
        
    def categorize_file(self, file_path):
        """تصنيف الملف حسب الامتداد"""
        
        extension = file_path.suffix.lower()
        
        for category, extensions in self.camera_extensions.items():
            if extension in extensions:
                return extension, category
                
        return extension, 'UNKNOWN'
        
    def determine_card_type(self, card_path, camera_analysis):
        """تحديد نوع كارت الميموري"""
        
        folder_structure = camera_analysis.get('folder_structure', [])
        file_types = camera_analysis.get('file_types', {})
        
        # تحديد نوع الكاميرا من structure المجلدات
        if any('CANON' in folder for folder in folder_structure):
            return 'Canon Camera'
        elif any('NIKON' in folder for folder in folder_structure):
            return 'Nikon Camera'
        elif any('SONY' in folder for folder in folder_structure):
            return 'Sony Camera'
        elif any('OLYMP' in folder for folder in folder_structure):
            return 'Olympus Camera'
        elif 'DCIM' in folder_structure:
            return 'Digital Camera'
        elif 'AVCHD' in folder_structure or 'VIDEO' in file_types:
            return 'Video Camera'
        elif 'RAW' in file_types:
            return 'Professional Camera'
        else:
            return 'Memory Card'
            
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
            
    def get_card_summary(self, card_info):
        """الحصول على ملخص الكارت"""
        
        summary = f"""
📱 {card_info['name']} ({card_info['card_type']})
📏 Size: {self.format_size(card_info['total_size'])} 
📊 Used: {self.format_size(card_info['used_size'])} ({card_info['usage_percent']}%)
📷 Camera Files: {card_info['total_camera_files']} files ({self.format_size(card_info['total_camera_size'])})

File Types:"""
        
        for file_type, stats in card_info.get('file_types', {}).items():
            summary += f"\n  📄 {file_type}: {stats['count']} files ({self.format_size(stats['size'])})"
            
        return summary
        
    def is_card_accessible(self, card_path):
        """فحص إمكانية الوصول للكارت"""
        try:
            card_path = Path(card_path)
            
            if not card_path.exists():
                return False, "Card path does not exist"
                
            # محاولة قراءة محتوى المجلد
            list(card_path.iterdir())
            return True, "Card is accessible"
            
        except PermissionError:
            return False, "Permission denied"
        except Exception as e:
            return False, f"Access error: {str(e)}"

# اختبار سريع للنظام
if __name__ == "__main__":
    detector = MemoryCardDetector()
    print("🔍 Detecting memory cards...")
    
    cards = detector.detect_all_cards()
    
    if cards:
        print(f"\n✅ Found {len(cards)} memory card(s):")
        for i, card in enumerate(cards, 1):
            print(f"\n--- Card {i} ---")
            print(detector.get_card_summary(card))
    else:
        print("\n❌ No memory cards detected") 