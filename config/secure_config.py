#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import getmac
from pathlib import Path
from cryptography.fernet import Fernet

class SecureConfigManager:
    """
    Manages secure configuration files and decryption
    """
    def __init__(self):
        self.config_path = Path('config.enc')
        self.key_path = Path('encryption_key.txt')
        self.mac_address = getmac.get_mac_address()
    
    def read_key_from_file(self):
        """
        Read encryption key from file
        
        Returns:
            bytes: The encryption key
            
        Raises:
            ValueError: If key file not found or error reading the key
        """
        try:
            if not self.key_path.exists():
                raise ValueError(f"Encryption key file not found at {self.key_path}")
                
            encryption_key = self.key_path.read_text().strip().encode()
            return encryption_key
        except Exception as e:
            raise ValueError(f"Error reading encryption key: {str(e)}")
    
    def decrypt_config(self):
        """
        Decrypt configuration file
        
        Returns:
            dict: Decrypted configuration as dictionary
            
        Raises:
            ValueError: If there's an error in decryption or configuration format
        """
        try:
            encryption_key = self.read_key_from_file()
            fernet = Fernet(encryption_key)
            encrypted_data = self.config_path.read_bytes()
            decrypted_data = fernet.decrypt(encrypted_data)
            config = json.loads(decrypted_data)
            
            # Make MAC check optional - will be handled by database check now
            if 'authorized_mac' in config and config['authorized_mac'].lower() != self.mac_address.lower():
                print(f"Warning: MAC address mismatch. Config: {config['authorized_mac']}, Current: {self.mac_address}")
                
            return config
        except Exception as e:
            raise ValueError(f"Configuration error: {str(e)}")
