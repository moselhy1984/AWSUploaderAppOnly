#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS Uploader - EXE Builder Script
Build standalone executable for Windows distribution
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from datetime import datetime

class ExeBuilder:
    def __init__(self):
        self.project_dir = Path.cwd()
        self.build_dir = self.project_dir / "build"
        self.dist_dir = self.project_dir / "dist"
        self.spec_file = self.project_dir / "aws_uploader.spec"
        self.exe_name = "AWS_Uploader"
        self.version = "1.0.0"
        
    def print_header(self):
        """Print build header"""
        print("=" * 70)
        print("🏗️  AWS Uploader - EXE Builder")
        print("=" * 70)
        print(f"📁 Project Directory: {self.project_dir}")
        print(f"🎯 Target EXE: {self.exe_name}.exe")
        print(f"📊 Version: {self.version}")
        print(f"🖥️  Platform: {platform.system()} {platform.release()}")
        print(f"🐍 Python: {sys.version.split()[0]}")
        print(f"📅 Build Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    
    def check_requirements(self):
        """Check build requirements"""
        print("🔍 Checking build requirements...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            print("❌ Python 3.8+ required")
            return False
        print(f"✅ Python {sys.version.split()[0]} compatible")
        
        # Check PyInstaller
        try:
            import PyInstaller
            print(f"✅ PyInstaller {PyInstaller.__version__} found")
        except ImportError:
            print("❌ PyInstaller not found, installing...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
                print("✅ PyInstaller installed successfully")
            except subprocess.CalledProcessError:
                print("❌ Failed to install PyInstaller")
                return False
        
        # Check main.py
        if not (self.project_dir / "main.py").exists():
            print("❌ main.py not found")
            return False
        print("✅ main.py found")
        
        # Check config files
        required_files = [
            ('config.enc', 'Configuration file'),
            ('encryption_key.txt', 'Encryption key'),
            ('Uploadicon.ico', 'Application icon')
        ]
        
        for filename, description in required_files:
            if (self.project_dir / filename).exists():
                print(f"✅ {filename} found - {description}")
            else:
                print(f"⚠️  {filename} not found - {description}")
        
        # Check directories
        for dirname in ['ui', 'database', 'utils']:
            if (self.project_dir / dirname).exists():
                print(f"✅ {dirname}/ directory found")
            else:
                print(f"❌ {dirname}/ directory not found")
                return False
        
        return True
    
    def install_dependencies(self):
        """Install build dependencies"""
        print("📦 Installing build dependencies...")
        
        requirements_file = self.project_dir / "requirements-exe-build.txt"
        if not requirements_file.exists():
            print("❌ requirements-exe-build.txt not found")
            return False
        
        try:
            # Update pip first
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
            
            # Install requirements
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)], check=True)
            
            print("✅ Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            return False
    
    def clean_build(self):
        """Clean previous build artifacts"""
        print("🧹 Cleaning previous builds...")
        
        dirs_to_clean = [self.build_dir, self.dist_dir]
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"🗑️  Removed {dir_path}")
        
        if self.spec_file.exists():
            self.spec_file.unlink()
            print(f"🗑️  Removed {self.spec_file}")
    
    def create_spec_file(self):
        """Create PyInstaller spec file"""
        print("📝 Creating PyInstaller spec file...")
        
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=['{self.project_dir}'],
    binaries=[],
    datas=[
        ('Uploadicon.ico', '.'),
        ('downloadicon.ico', '.'),
        ('ui', 'ui'),
        ('database', 'database'),
        ('utils', 'utils'),
        ('config', 'config'),
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
        'mysql.connector',
        'boto3',
        'botocore',
        'psutil',
        'getmac',
        'cryptography',
        'requests',
        'wmi',
        'pywin32',
        'pathlib',
        'json',
        'datetime',
        'threading',
        'queue',
        'tempfile',
        'shutil',
        'platform',
        'uuid',
        'hashlib',
        'base64',
        'configparser',
        'xml.etree.ElementTree',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'numpy',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{self.exe_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='Uploadicon.ico',
)
'''
        
        with open(self.spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)
        
        print(f"✅ Spec file created: {self.spec_file}")
        return True
    
    def build_exe(self):
        """Build the executable"""
        print("🔨 Building executable...")
        print("⏳ This may take 5-15 minutes...")
        
        try:
            cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(self.spec_file)]
            
            subprocess.run(cmd, check=True)
            print("✅ Build completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Build failed: {e}")
            return False
    
    def create_portable_package(self):
        """Create portable package"""
        print("📦 Creating portable package...")
        
        exe_path = self.dist_dir / f"{self.exe_name}.exe"
        if not exe_path.exists():
            print(f"❌ EXE not found: {exe_path}")
            return False
        
        # Create portable directory
        portable_dir = self.project_dir / f"{self.exe_name}_Portable"
        if portable_dir.exists():
            shutil.rmtree(portable_dir)
        portable_dir.mkdir()
        
        # Copy files
        shutil.copy2(exe_path, portable_dir / f"{self.exe_name}.exe")
        print(f"✅ Copied {self.exe_name}.exe")
        
        # Copy required files
        required_files = ['config.enc', 'encryption_key.txt', 'Uploadicon.ico', 'downloadicon.ico']
        for filename in required_files:
            src = self.project_dir / filename
            if src.exists():
                shutil.copy2(src, portable_dir / filename)
                print(f"✅ Copied {filename}")
        
        # Create README
        readme_content = f"""# {self.exe_name} - Portable Version

## Quick Start:
1. Double-click {self.exe_name}.exe to run
2. Make sure config.enc and encryption_key.txt are in the same folder

## Required Files:
- {self.exe_name}.exe (main application)
- config.enc (configuration file)
- encryption_key.txt (encryption key)
- Uploadicon.ico (application icon)

## Troubleshooting:
- If Windows Defender blocks the exe, add it to exclusions
- Run as Administrator if you encounter permission issues
- Make sure all config files are present

Build Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        with open(portable_dir / "README.txt", 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        print(f"✅ Portable package created: {portable_dir}")
        return True
    
    def run_build(self):
        """Run the complete build process"""
        self.print_header()
        
        steps = [
            ("Checking requirements", self.check_requirements),
            ("Installing dependencies", self.install_dependencies),
            ("Cleaning previous builds", self.clean_build),
            ("Creating spec file", self.create_spec_file),
            ("Building executable", self.build_exe),
            ("Creating portable package", self.create_portable_package),
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 {step_name}...")
            try:
                if not step_func():
                    print(f"❌ {step_name} failed")
                    return False
                print(f"✅ {step_name} completed")
            except Exception as e:
                print(f"❌ {step_name} failed with error: {e}")
                return False
        
        # Print summary
        print("\n" + "=" * 70)
        print("🎉 BUILD COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        
        exe_path = self.dist_dir / f"{self.exe_name}.exe"
        portable_dir = self.project_dir / f"{self.exe_name}_Portable"
        
        print(f"📦 Standalone EXE: {exe_path}")
        print(f"📁 Portable Package: {portable_dir}")
        print()
        print("🚀 Ready for distribution!")
        print()
        print("📋 Next steps:")
        print("1. Test the EXE on your local machine")
        print("2. Test on a different Windows machine")
        print("3. Distribute the portable package")
        print()
        print("⚠️  Important: Make sure config.enc and encryption_key.txt")
        print("   are included with the distributed files!")
        
        return True

def main():
    """Main entry point"""
    if platform.system() != 'Windows':
        print("⚠️  This build script is designed for Windows")
        print("   You can still run it, but the EXE will be for Windows only")
    
    builder = ExeBuilder()
    success = builder.run_build()
    
    if not success:
        print("\n❌ Build failed. Check the errors above.")
        sys.exit(1)
    
    print("\nPress Enter to continue...")
    input()

if __name__ == '__main__':
    main() 