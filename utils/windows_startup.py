#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windows Startup Management for AWS Uploader
"""

import os
import sys
import winreg
from pathlib import Path

class WindowsStartup:
    """Manage Windows startup registry entries"""
    
    def __init__(self, app_name="AWSFileUploader"):
        self.app_name = app_name
        self.registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    def add_to_startup(self, executable_path=None):
        """
        Add application to Windows startup
        
        Args:
            executable_path (str, optional): Path to executable. 
                                           If None, uses current script path.
        """
        try:
            if executable_path is None:
                # Use current script path
                if getattr(sys, 'frozen', False):
                    # Running as compiled executable
                    executable_path = sys.executable
                else:
                    # Running as Python script
                    script_dir = Path(__file__).parent.parent
                    executable_path = f'"{sys.executable}" "{script_dir / "main.py"}"'
            
            # Open registry key
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_path,
                0,
                winreg.KEY_SET_VALUE
            )
            
            # Set the value
            winreg.SetValueEx(
                key,
                self.app_name,
                0,
                winreg.REG_SZ,
                executable_path
            )
            
            winreg.CloseKey(key)
            return True, "Successfully added to Windows startup"
            
        except Exception as e:
            return False, f"Error adding to startup: {str(e)}"
    
    def remove_from_startup(self):
        """Remove application from Windows startup"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_path,
                0,
                winreg.KEY_SET_VALUE
            )
            
            winreg.DeleteValue(key, self.app_name)
            winreg.CloseKey(key)
            return True, "Successfully removed from Windows startup"
            
        except FileNotFoundError:
            return True, "Application was not in startup list"
        except Exception as e:
            return False, f"Error removing from startup: {str(e)}"
    
    def is_in_startup(self):
        """Check if application is in Windows startup"""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_path,
                0,
                winreg.KEY_READ
            )
            
            value, _ = winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return True, value
            
        except FileNotFoundError:
            return False, None
        except Exception as e:
            return False, f"Error checking startup: {str(e)}"

def main():
    """Test the startup functionality"""
    startup = WindowsStartup()
    
    print("Windows Startup Manager Test")
    print("=" * 30)
    
    # Check current status
    is_startup, value = startup.is_in_startup()
    print(f"Currently in startup: {is_startup}")
    if is_startup and isinstance(value, str):
        print(f"Startup command: {value}")
    
    # Test adding to startup
    success, message = startup.add_to_startup()
    print(f"Add to startup: {success} - {message}")
    
    # Check again
    is_startup, value = startup.is_in_startup()
    print(f"After adding - In startup: {is_startup}")

if __name__ == "__main__":
    main() 