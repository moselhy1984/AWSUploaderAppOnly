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
        self.root.title("AWS Credentials Encryptor")
        self.root.geometry("600x650")
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
        title_label = ttk.Label(main_frame, text="AWS Credentials Encryptor", style='Header.TLabel')
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="w")
        
        # Form frame
        form_frame = ttk.LabelFrame(main_frame, text="AWS Credentials", padding="10")
        form_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 20))
        
        # Device Name (new field)
        ttk.Label(form_frame, text="Device Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.device_name = ttk.Entry(form_frame, width=40)
        self.device_name.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # AWS Access Key
        ttk.Label(form_frame, text="AWS Access Key ID:").grid(row=1, column=0, sticky="w", pady=5)
        self.aws_access_key = ttk.Entry(form_frame, width=40)
        self.aws_access_key.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # AWS Secret Key
        ttk.Label(form_frame, text="AWS Secret Access Key:").grid(row=2, column=0, sticky="w", pady=5)
        self.aws_secret_key = ttk.Entry(form_frame, width=40, show="*")
        self.aws_secret_key.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Show/Hide password
        self.show_secret = tk.BooleanVar()
        show_secret_check = ttk.Checkbutton(form_frame, text="Show Secret Key", 
                                          variable=self.show_secret, 
                                          command=self.toggle_secret_visibility)
        show_secret_check.grid(row=3, column=1, sticky="w", pady=2)
        
        # AWS Region (default to me-south-1)
        ttk.Label(form_frame, text="AWS Region:").grid(row=4, column=0, sticky="w", pady=5)
        self.aws_region = ttk.Entry(form_frame, width=40, state="readonly")
        self.aws_region.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        
        # Set default region
        self.aws_region_var = tk.StringVar(value="me-south-1")
        self.aws_region.config(textvariable=self.aws_region_var)
        
        # S3 Bucket
        ttk.Label(form_frame, text="S3 Bucket Name:").grid(row=5, column=0, sticky="w", pady=5)
        self.bucket_name = ttk.Entry(form_frame, width=40)
        self.bucket_name.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
        
        # MAC Address (editable now)
        ttk.Label(form_frame, text="MAC Address:").grid(row=6, column=0, sticky="w", pady=5)
        self.mac_address = ttk.Entry(form_frame, width=40)
        self.mac_address.grid(row=6, column=1, padx=5, pady=5, sticky="ew")
        
        # Get current MAC button
        self.get_mac_btn = ttk.Button(form_frame, text="Get Current MAC", command=self.get_current_mac)
        self.get_mac_btn.grid(row=7, column=1, pady=5, sticky="w")

        # Set default bucket name
        self.bucket_name.insert(0, 'balistudiostorage')
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        # Generate button
        self.generate_btn = ttk.Button(button_frame, text="Generate & Encrypt", command=self.generate_config)
        self.generate_btn.grid(row=0, column=0, padx=5, sticky="e")
        
        # Clear button
        self.clear_btn = ttk.Button(button_frame, text="Clear Form", command=self.clear_form)
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
        
        # Make form expandable
        form_frame.columnconfigure(1, weight=1)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(1, weight=1)
        self.status_frame.columnconfigure(0, weight=1)
    
    def get_current_mac(self):
        try:
            current_mac = getmac.get_mac_address()
            self.mac_address.delete(0, tk.END)
            self.mac_address.insert(0, current_mac)
            self.update_status(f"MAC address detected: {current_mac}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not get MAC address: {str(e)}")
            self.update_status(f"ERROR: Could not get MAC address: {str(e)}")
        
    def toggle_secret_visibility(self):
        if self.show_secret.get():
            self.aws_secret_key.config(show="")
        else:
            self.aws_secret_key.config(show="*")
    
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
        self.device_name.delete(0, tk.END)
        self.aws_access_key.delete(0, tk.END)
        self.aws_secret_key.delete(0, tk.END)
        self.mac_address.delete(0, tk.END)
        self.bucket_name.delete(0, tk.END)
        self.bucket_name.insert(0, 'balistudiostorage')  # Reset default bucket
        self.key_display.delete("1.0", tk.END)
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.config(state=tk.DISABLED)
    
    def generate_config(self):
        # Check if all fields are filled
        if not self.device_name.get() or not self.aws_access_key.get() or not self.aws_secret_key.get() or not self.bucket_name.get() or not self.mac_address.get():
            messagebox.showerror("Error", "Please fill in all fields!")
            return
        
        try:
            # Generate a new encryption key
            key = Fernet.generate_key()
            
            # Create configuration
            config = {
                "device_name": self.device_name.get(),
                "aws_access_key_id": self.aws_access_key.get(),
                "aws_secret_key": self.aws_secret_key.get(),
                "region": self.aws_region_var.get(),
                "bucket": self.bucket_name.get(),
                "authorized_mac": self.mac_address.get()
            }
            
            # Encrypt configuration
            f = Fernet(key)
            encrypted_data = f.encrypt(json.dumps(config).encode())
            
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
            
            # Display the key
            self.key_display.delete("1.0", tk.END)
            self.key_display.insert(tk.END, key.decode())
            
            # Update status
            self.update_status(f"Configuration file created successfully at: {config_path}")
            self.update_status(f"Key file saved at: {key_path}")
            self.update_status(f"Device name: {self.device_name.get()}")
            self.update_status(f"MAC address: {self.mac_address.get()}")
            self.update_status("Please save your encryption key safely. You'll need it to run the application.")
            
            messagebox.showinfo("Success", 
                               f"Configuration encrypted successfully!\n"
                               f"Files saved in folder: {self.device_name.get()}\n"
                               f"Please save your encryption key.")
            
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
            self.update_status(f"ERROR: {str(e)}")

def main():
    root = tk.Tk()
    app = AwsCredentialsEncryptorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()