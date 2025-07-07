#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
from typing import Union, Optional, List
import logging

class ResourceManager:
    """
    مدير الموارد للتعامل مع مسارات الملفات بطريقة متوافقة مع PyInstaller
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._base_path: Optional[Path] = None
        self._is_frozen = self._check_if_frozen()
        self._initialize_base_path()
        
    @property
    def base_path(self) -> Path:
        """Get the base path for the application"""
        if self._base_path is None:
            raise RuntimeError("Base path not initialized")
        return self._base_path
        
    @property
    def is_frozen(self) -> bool:
        """Check if the application is frozen (compiled)"""
        return self._is_frozen
    
    def _check_if_frozen(self) -> bool:
        """فحص ما إذا كان التطبيق يعمل كـ executable أم لا"""
        return bool(
            getattr(sys, 'frozen', False) or  # PyInstaller
            hasattr(sys, '_MEIPASS') or       # PyInstaller temp folder
            getattr(sys, 'importers', None)   # py2exe
        )
    
    def _initialize_base_path(self):
        """تهيئة المسار الأساسي للموارد"""
        if self._is_frozen:
            # إذا كان التطبيق مجمد (executable)
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller creates a temp folder and stores path in _MEIPASS
                self._base_path = Path(sys._MEIPASS)  # type: ignore
                self.logger.info(f"Running as PyInstaller executable. Base path: {self._base_path}")
            else:
                # Fallback for other frozen applications
                self._base_path = Path(sys.executable).parent
                self.logger.info(f"Running as frozen executable. Base path: {self._base_path}")
        else:
            # إذا كان يعمل كـ Python script
            # العثور على مجلد root للمشروع
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent  # من utils/ إلى project root
            self._base_path = project_root
            self.logger.info(f"Running as Python script. Base path: {self._base_path}")
    
    def get_resource_path(self, relative_path: Union[str, Path]) -> Path:
        """
        الحصول على المسار الكامل للمورد
        
        Args:
            relative_path: المسار النسبي للمورد من root المشروع
            
        Returns:
            Path: المسار الكامل للمورد
        """
        if not relative_path:
            return self.base_path
        
        # تحويل إلى Path object
        resource_path = Path(relative_path)
        
        # إنشاء المسار الكامل
        full_path = self.base_path / resource_path
        
        # فحص وجود الملف
        if full_path.exists():
            self.logger.debug(f"Resource found: {full_path}")
            return full_path
        else:
            # محاولة البحث في مسارات بديلة
            alternative_paths = self._get_alternative_paths(resource_path)
            
            for alt_path in alternative_paths:
                if alt_path.exists():
                    self.logger.info(f"Resource found in alternative location: {alt_path}")
                    return alt_path
            
            # إذا لم يوجد الملف، إرجاع المسار الأصلي مع تحذير
            self.logger.warning(f"Resource not found: {full_path}")
            return full_path
    
    def _get_alternative_paths(self, resource_path: Path) -> List[Path]:
        """الحصول على مسارات بديلة للبحث عن المورد"""
        alternatives = []
        
        # البحث في مجلد التطبيق الحالي
        if self._is_frozen:
            app_dir = Path(sys.executable).parent
            alternatives.append(app_dir / resource_path)
        
        # البحث في مجلد العمل الحالي
        current_working_dir = Path.cwd()
        alternatives.append(current_working_dir / resource_path)
        
        # البحث في مجلد المشروع
        if not self._is_frozen:
            project_dirs = [
                Path(__file__).parent.parent,  # من utils/
                Path(__file__).parent.parent.parent,  # مستوى أعلى
            ]
            for project_dir in project_dirs:
                alternatives.append(project_dir / resource_path)
        
        return alternatives
    
    def get_config_path(self, config_name: str) -> Path:
        """الحصول على مسار ملف التكوين"""
        return self.get_resource_path(config_name)
    
    def get_icon_path(self, icon_name: str) -> Path:
        """الحصول على مسار الأيقونة"""
        return self.get_resource_path(icon_name)
    
    def get_data_path(self, data_file: str) -> Path:
        """الحصول على مسار ملف البيانات"""
        return self.get_resource_path(data_file)
    
    def ensure_directory_exists(self, dir_path: Union[str, Path]) -> Path:
        """التأكد من وجود المجلد وإنشاؤه إذا لم يكن موجود"""
        full_path = self.get_resource_path(dir_path)
        full_path.mkdir(parents=True, exist_ok=True)
        return full_path
    
    def list_resources(self, pattern: str = "*") -> List[Path]:
        """عرض قائمة بجميع الموارد المتاحة"""
        resources = []
        try:
            for item in self.base_path.glob(pattern):
                if item.is_file():
                    resources.append(item.relative_to(self.base_path))
        except Exception as e:
            self.logger.error(f"Error listing resources: {e}")
        return resources


# إنشاء instance عالمي
resource_manager = ResourceManager()

# دوال مساعدة للتوافق مع الكود الموجود
def resource_path(relative_path: Union[str, Path]) -> Path:
    """
    دالة مساعدة للحصول على مسار المورد
    
    Args:
        relative_path: المسار النسبي للمورد
        
    Returns:
        Path: المسار الكامل للمورد
    """
    return resource_manager.get_resource_path(relative_path)

def get_icon_path(icon_name: str) -> Path:
    """دالة مساعدة للحصول على مسار الأيقونة"""
    return resource_manager.get_icon_path(icon_name)

def get_config_path(config_name: str) -> Path:
    """دالة مساعدة للحصول على مسار ملف التكوين"""
    return resource_manager.get_config_path(config_name)

def get_data_path(data_file: str) -> Path:
    """دالة مساعدة للحصول على مسار ملف البيانات"""
    return resource_manager.get_data_path(data_file)

# دالة تقليدية للتوافق مع PyInstaller
def resource_path_legacy(relative_path: str) -> str:
    """
    دالة تقليدية للتوافق مع PyInstaller (ترجع string)
    
    Args:
        relative_path: المسار النسبي للمورد
        
    Returns:
        str: المسار الكامل للمورد
    """
    return str(resource_path(relative_path))

# اختبار الدالة عند التشغيل
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("=== Resource Manager Test ===")
    print(f"Base path: {resource_manager.base_path}")
    print(f"Is frozen: {resource_manager.is_frozen}")
    
    # اختبار الأيقونات
    test_resources = ["Uploadicon.ico", "downloadicon.ico", "config.enc", "encryption_key.txt"]
    
    for resource in test_resources:
        path = resource_path(resource)
        status = "✅ EXISTS" if path.exists() else "❌ MISSING"
        print(f"{status} {resource}: {path}")
    
    # عرض الموارد المتاحة
    print("\n=== Available Resources ===")
    resources = resource_manager.list_resources("*")
    for res in resources[:10]:  # عرض أول 10 موارد
        print(f"- {res}")
    
    if len(resources) > 10:
        print(f"... and {len(resources) - 10} more") 