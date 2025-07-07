import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import getmac
from cryptography.fernet import Fernet
from pathlib import Path
import pyperclip
import os

class AwsCredentialsEncryptorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AWS Credentials & RDS Encryptor")
        self.root.geometry("650x800")
        self.root.resizable(True, True)
        
        # Configure style
        style = ttk.Style()
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabel', background='#f0f0f0', font=('Arial', 11))
        style.configure('TButton', font=('Arial', 11))
        style.configure('Header.TLabel', font=('Arial', 14, 'bold'))
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="AWS Credentials & RDS Encryptor", style='Header.TLabel')
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="w")
        
        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 20))
        
        # AWS Credentials Tab
        aws_frame = ttk.Frame(notebook, padding="10")
        notebook.add(aws_frame, text="AWS Credentials")
        
        # RDS Database Tab
        rds_frame = ttk.Frame(notebook, padding="10")
        notebook.add(rds_frame, text="RDS Database")
        
        # Create AWS credentials widgets
        self.create_aws_widgets(aws_frame)
        
        # Create RDS widgets
        self.create_rds_widgets(rds_frame)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        # Generate button
        self.generate_btn = ttk.Button(button_frame, text="Generate & Encrypt", command=self.generate_config)
        self.generate_btn.grid(row=0, column=0, padx=5, sticky="e")
        
        # Clear button
        self.clear_btn = ttk.Button(button_frame, text="Clear All Forms", command=self.clear_form)
        self.clear_btn.grid(row=0, column=1, padx=5, sticky="w")
        
        # Result frame
        result_frame = ttk.LabelFrame(main_frame, text="Results", padding="10")
        result_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=10)
        main_frame.rowconfigure(3, weight=1)
        
        # Key display
        ttk.Label(result_frame, text="Encryption Key:").grid(row=0, column=0, sticky="w", pady=5)
        self.key_display = scrolledtext.ScrolledText(result_frame, height=3, width=50, wrap=tk.WORD)
        self.key_display.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")
        
        # Copy key button
        self.copy_key_btn = ttk.Button(result_frame, text="Copy Key", command=lambda: self.copy_to_clipboard(self.key_display.get("1.0", tk.END).strip()))
        self.copy_key_btn.grid(row=2, column=0, pady=5, sticky="e")
        
        # Status
        self.status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        self.status_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)
        
        self.status_text = scrolledtext.ScrolledText(self.status_frame, height=5, width=50, wrap=tk.WORD)
        self.status_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.status_text.config(state=tk.DISABLED)
        
        # Make expandable
        main_frame.rowconfigure(1, weight=1)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)
        self.status_frame.columnconfigure(0, weight=1)
    
    def create_aws_widgets(self, parent):
        # Device Name
        ttk.Label(parent, text="Device Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.device_name = ttk.Entry(parent, width=40)
        self.device_name.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # AWS Access Key
        ttk.Label(parent, text="AWS Access Key ID:").grid(row=1, column=0, sticky="w", pady=5)
        self.aws_access_key = ttk.Entry(parent, width=40)
        self.aws_access_key.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # AWS Secret Key
        ttk.Label(parent, text="AWS Secret Access Key:").grid(row=2, column=0, sticky="w", pady=5)
        self.aws_secret_key = ttk.Entry(parent, width=40, show="*")
        self.aws_secret_key.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Show/Hide password
        self.show_secret = tk.BooleanVar()
        show_secret_check = ttk.Checkbutton(parent, text="Show Secret Key", 
                                          variable=self.show_secret, 
                                          command=self.toggle_secret_visibility)
        show_secret_check.grid(row=3, column=1, sticky="w", pady=2)
        
        # AWS Region
        ttk.Label(parent, text="AWS Region:").grid(row=4, column=0, sticky="w", pady=5)
        self.aws_region = ttk.Entry(parent, width=40, state="readonly")
        self.aws_region.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        
        # Set default region
        self.aws_region_var = tk.StringVar(value="me-south-1")
        self.aws_region.config(textvariable=self.aws_region_var)
        
        # S3 Bucket
        ttk.Label(parent, text="S3 Bucket Name:").grid(row=5, column=0, sticky="w", pady=5)
        self.bucket_name = ttk.Entry(parent, width=40)
        self.bucket_name.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
        self.bucket_name.insert(0, 'balistudiostorage')
        
        # MAC Address
        ttk.Label(parent, text="MAC Address:").grid(row=6, column=0, sticky="w", pady=5)
        self.mac_address = ttk.Entry(parent, width=40)
        self.mac_address.grid(row=6, column=1, padx=5, pady=5, sticky="ew")
        
        # Get current MAC button
        self.get_mac_btn = ttk.Button(parent, text="Get Current MAC", command=self.get_current_mac)
        self.get_mac_btn.grid(row=7, column=1, pady=5, sticky="w")
        
        # Make expandable
        parent.columnconfigure(1, weight=1)
    
    def create_rds_widgets(self, parent):
        # RDS Database Host
        ttk.Label(parent, text="RDS Endpoint (Host):").grid(row=0, column=0, sticky="w", pady=5)
        self.rds_host = ttk.Entry(parent, width=40)
        self.rds_host.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # RDS Port
        ttk.Label(parent, text="Port:").grid(row=1, column=0, sticky="w", pady=5)
        self.rds_port = ttk.Entry(parent, width=40)
        self.rds_port.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.rds_port.insert(0, "3306")  # Default MySQL port
        
        # Database Name
        ttk.Label(parent, text="Database Name:").grid(row=2, column=0, sticky="w", pady=5)
        self.db_name = ttk.Entry(parent, width=40)
        self.db_name.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Database Username
        ttk.Label(parent, text="Username:").grid(row=3, column=0, sticky="w", pady=5)
        self.db_username = ttk.Entry(parent, width=40)
        self.db_username.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        
        # Database Password
        ttk.Label(parent, text="Password:").grid(row=4, column=0, sticky="w", pady=5)
        self.db_password = ttk.Entry(parent, width=40, show="*")
        self.db_password.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        
        # Show/Hide DB password
        self.show_db_password = tk.BooleanVar()
        show_db_password_check = ttk.Checkbutton(parent, text="Show Password", 
                                               variable=self.show_db_password, 
                                               command=self.toggle_db_password_visibility)
        show_db_password_check.grid(row=5, column=1, sticky="w", pady=2)
        
        # Database Engine
        ttk.Label(parent, text="Database Engine:").grid(row=6, column=0, sticky="w", pady=5)
        self.db_engine = ttk.Combobox(parent, width=37, values=["mysql", "postgresql", "mariadb", "oracle", "sqlserver"])
        self.db_engine.grid(row=6, column=1, padx=5, pady=5, sticky="ew")
        self.db_engine.set("mysql")  # Default to MySQL
        
        # SSL Mode
        ttk.Label(parent, text="SSL Mode:").grid(row=7, column=0, sticky="w", pady=5)
        self.ssl_mode = ttk.Combobox(parent, width=37, values=["require", "prefer", "allow", "disable"])
        self.ssl_mode.grid(row=7, column=1, padx=5, pady=5, sticky="ew")
        self.ssl_mode.set("require")  # Default to require SSL
        
        # Connection Timeout
        ttk.Label(parent, text="Connection Timeout (seconds):").grid(row=8, column=0, sticky="w", pady=5)
        self.connection_timeout = ttk.Entry(parent, width=40)
        self.connection_timeout.grid(row=8, column=1, padx=5, pady=5, sticky="ew")
        self.connection_timeout.insert(0, "30")
        
        # Test Connection Button
        self.test_connection_btn = ttk.Button(parent, text="Test RDS Connection", command=self.test_rds_connection)
        self.test_connection_btn.grid(row=9, column=1, pady=10, sticky="w")
        
        # Make expandable
        parent.columnconfigure(1, weight=1)
    
    def test_rds_connection(self):
        """Test RDS database connection (placeholder - would need actual DB drivers)"""
        if not all([self.rds_host.get(), self.db_name.get(), self.db_username.get(), self.db_password.get()]):
            messagebox.showerror("Error", "Please fill in all RDS database fields!")
            return
        
        self.update_status("Testing RDS connection...")
        # This is a placeholder - in real implementation you would use:
        # - pymysql for MySQL
        # - psycopg2 for PostgreSQL
        # - etc.
        
        messagebox.showinfo("Connection Test", 
                           "Connection test placeholder.\n"
                           "In production, this would test the actual database connection.\n"
                           "Make sure your RDS instance is accessible and credentials are correct.")
        self.update_status("Connection test completed (placeholder)")
    
    def get_current_mac(self):
        try:
            current_mac = getmac.get_mac_address()
            self.mac_address.delete(0, tk.END)
            self.mac_address.insert(0, str(current_mac))
            self.update_status(f"MAC address detected: {current_mac}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not get MAC address: {str(e)}")
            self.update_status(f"ERROR: Could not get MAC address: {str(e)}")
        
    def toggle_secret_visibility(self):
        if self.show_secret.get():
            self.aws_secret_key.config(show="")
        else:
            self.aws_secret_key.config(show="*")
    
    def toggle_db_password_visibility(self):
        if self.show_db_password.get():
            self.db_password.config(show="")
        else:
            self.db_password.config(show="*")
    
    def update_status(self, message):
        self.status_text.config(state=tk.NORMAL)
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def copy_to_clipboard(self, text):
        pyperclip.copy(text)
        messagebox.showinfo("Copied", "Text copied to clipboard!")
    
    def clear_form(self):
        # Clear AWS fields
        self.device_name.delete(0, tk.END)
        self.aws_access_key.delete(0, tk.END)
        self.aws_secret_key.delete(0, tk.END)
        self.mac_address.delete(0, tk.END)
        self.bucket_name.delete(0, tk.END)
        self.bucket_name.insert(0, 'balistudiostorage')  # Reset default bucket
        
        # Clear RDS fields
        self.rds_host.delete(0, tk.END)
        self.rds_port.delete(0, tk.END)
        self.rds_port.insert(0, "3306")
        self.db_name.delete(0, tk.END)
        self.db_username.delete(0, tk.END)
        self.db_password.delete(0, tk.END)
        self.db_engine.set("mysql")
        self.ssl_mode.set("require")
        self.connection_timeout.delete(0, tk.END)
        self.connection_timeout.insert(0, "30")
        
        # Clear results
        self.key_display.delete("1.0", tk.END)
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.config(state=tk.DISABLED)
    
    def generate_config(self):
        # Check if all required fields are filled
        aws_fields_filled = all([
            self.device_name.get(),
            self.aws_access_key.get(),
            self.aws_secret_key.get(),
            self.bucket_name.get(),
            self.mac_address.get()
        ])
        
        rds_fields_filled = all([
            self.rds_host.get(),
            self.rds_port.get(),
            self.db_name.get(),
            self.db_username.get(),
            self.db_password.get()
        ])
        
        if not aws_fields_filled:
            messagebox.showerror("Error", "Please fill in all AWS credential fields!")
            return
        
        if not rds_fields_filled:
            messagebox.showerror("Error", "Please fill in all RDS database fields!")
            return
        
        try:
            # Generate a new encryption key
            key = Fernet.generate_key()
            
            # Create configuration with both AWS and RDS data
            config = {
                "device_name": self.device_name.get(),
                "aws_access_key_id": self.aws_access_key.get(),
                "aws_secret_key": self.aws_secret_key.get(),
                "region": self.aws_region_var.get(),
                "bucket": self.bucket_name.get(),
                "authorized_mac": self.mac_address.get(),
                "rds_config": {
                    "host": self.rds_host.get(),
                    "port": int(self.rds_port.get()),
                    "database": self.db_name.get(),
                    "username": self.db_username.get(),
                    "password": self.db_password.get(),
                    "engine": self.db_engine.get(),
                    "ssl_mode": self.ssl_mode.get(),
                    "connection_timeout": int(self.connection_timeout.get())
                }
            }
            
            # Encrypt configuration
            f = Fernet(key)
            encrypted_data = f.encrypt(json.dumps(config, indent=2).encode())
            
            # Create folder with device name if it doesn't exist
            device_folder = Path(self.device_name.get())
            if not device_folder.exists():
                device_folder.mkdir(parents=True)
                self.update_status(f"Created folder: {device_folder}")
            
            # Save encrypted configuration in the device folder
            config_path = device_folder / 'config.enc'
            config_path.write_bytes(encrypted_data)
            
            # Save key to a file in the device folder
            key_path = device_folder / 'encryption_key.txt'
            key_path.write_text(key.decode())
            
            # Also save copies in the root directory for the application to find
            root_config_path = Path('config.enc')
            root_key_path = Path('encryption_key.txt')
            
            try:
                root_config_path.write_bytes(encrypted_data)
                root_key_path.write_text(key.decode())
                self.update_status("Also saved copies in application root directory")
            except Exception as e:
                self.update_status(f"Warning: Could not save to root directory: {e}")
            
            # Display the key
            self.key_display.delete("1.0", tk.END)
            self.key_display.insert(tk.END, key.decode())
            
            # Update status
            self.update_status(f"Configuration file created successfully at: {config_path}")
            self.update_status(f"Key file saved at: {key_path}")
            self.update_status(f"Device name: {self.device_name.get()}")
            self.update_status(f"MAC address: {self.mac_address.get()}")
            self.update_status(f"RDS Host: {self.rds_host.get()}")
            self.update_status(f"Database: {self.db_name.get()}")
            self.update_status("Configuration includes both AWS credentials and RDS database settings.")
            self.update_status("Please save your encryption key safely. You'll need it to run the application.")
            
            messagebox.showinfo("Success", 
                               f"Configuration encrypted successfully!\n"
                               f"Files saved in folder: {self.device_name.get()}\n"
                               f"Includes AWS credentials and RDS database settings.\n"
                               f"Please save your encryption key.")
            
        except ValueError as ve:
            messagebox.showerror("Error", f"Invalid input: {str(ve)}")
            self.update_status(f"ERROR: Invalid input - {str(ve)}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
            self.update_status(f"ERROR: {str(e)}")

def main():
    root = tk.Tk()
    app = AwsCredentialsEncryptorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()