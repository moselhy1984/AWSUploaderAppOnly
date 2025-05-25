import json
from pathlib import Path
from cryptography.fernet import Fernet

config_path = Path('config.enc')
key_path = Path('encryption_key.txt')

if not config_path.exists() or not key_path.exists():
    print("ملفات التشفير غير موجودة في هذا المجلد.")
    exit(1)

encryption_key = key_path.read_text().strip().encode()
fernet = Fernet(encryption_key)
encrypted_data = config_path.read_bytes()
try:
    decrypted_data = fernet.decrypt(encrypted_data)
    config = json.loads(decrypted_data)
    print("محتوى ملف التشفير بعد فك التشفير:\n", json.dumps(config, indent=2, ensure_ascii=False))
except Exception as e:
    print("خطأ أثناء فك التشفير:", e) 