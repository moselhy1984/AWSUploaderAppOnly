import os
import platform
import subprocess
import sys

def build_executable():
    print("Building AWS File Uploader Application...")
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyInstaller"])
    
    # Use the new upload icon
    icon_file = "Uploadicon.ico"
    
    # Build command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--hidden-import=getmac",
        "--hidden-import=cryptography",
        "--hidden-import=boto3",
        "--hidden-import=mysql.connector",
        f"--icon={icon_file}",
        "--clean",
        "--name=AWSFileUploader",
        "main.py"
    ]
    
    # Add platform-specific options
    if platform.system() == "Darwin":  # macOS
        cmd.extend(["--windowed"])
    elif platform.system() == "Windows":
        cmd.extend(["--noconsole"])
    
    # Execute the build command
    try:
        subprocess.check_call(cmd)
        print("\nBuild completed successfully!")
        print(f"Executable can be found in the 'dist' directory")
    except subprocess.CalledProcessError as e:
        print(f"\nError during build: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build_executable() 