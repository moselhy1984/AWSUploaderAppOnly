#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import getmac
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

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
            # Validate key format
            try:
                Fernet(encryption_key)
            except Exception as e:
                raise ValueError(f"Invalid encryption key format: {str(e)}")
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
            if not self.config_path.exists():
                raise ValueError(f"Configuration file not found at {self.config_path}")
                
            encryption_key = self.read_key_from_file()
            fernet = Fernet(encryption_key)
            
            try:
                encrypted_data = self.config_path.read_bytes()
            except Exception as e:
                raise ValueError(f"Error reading encrypted configuration file: {str(e)}")
            
            try:
                decrypted_data = fernet.decrypt(encrypted_data)
            except InvalidToken:
                raise ValueError("Invalid encryption key or corrupted configuration file")
            except Exception as e:
                raise ValueError(f"Error decrypting configuration: {str(e)}")
            
            try:
                config = json.loads(decrypted_data)
            except json.JSONDecodeError:
                raise ValueError("Decrypted data is not valid JSON")
            except Exception as e:
                raise ValueError(f"Error parsing decrypted configuration: {str(e)}")
            
            # دعم الأسماء البديلة للحقول
            mapping = {
                'AWS_ACCESS_KEY_ID': ['AWS_ACCESS_KEY_ID', 'aws_access_key_id'],
                'AWS_SECRET_ACCESS_KEY': ['AWS_SECRET_ACCESS_KEY', 'aws_secret_key', 'AWS_SECRET_KEY'],
                'AWS_REGION': ['AWS_REGION', 'region'],
                'AWS_S3_BUCKET': ['AWS_S3_BUCKET', 'bucket']
            }
            normalized_config = {}
            missing_fields = []
            for std_key, possible_keys in mapping.items():
                for k in possible_keys:
                    if k in config:
                        normalized_config[std_key] = config[k]
                        break
                else:
                    missing_fields.append(std_key)
            if missing_fields:
                raise ValueError(f"Missing required AWS configuration fields: {', '.join(missing_fields)}")
            # إضافة باقي الحقول الأخرى كما هي
            for k, v in config.items():
                if k not in sum(mapping.values(), []):
                    normalized_config[k] = v
            # Make MAC check optional - will be handled by database check now
            if 'authorized_mac' in config and config['authorized_mac'].lower() != self.mac_address.lower():
                print(f"Warning: MAC address mismatch. Config: {config['authorized_mac']}, Current: {self.mac_address}")
            return normalized_config
        except Exception as e:
            raise ValueError(f"Configuration error: {str(e)}")
