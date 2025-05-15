# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui', 'ui'),
        ('utils', 'utils'),
        ('config', 'config'),
        ('database', 'database'),
        ('icon.ico', '.'),
        ('config.enc', '.'),
        ('encryption_key.txt', '.'),
    ],
    hiddenimports=[
        'mysql.connector', 
        'boto3', 
        'cryptography', 
        'getmac',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure, 
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AWS Uploader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AWS Uploader',
)

app = BUNDLE(
    coll,
    name='AWS Uploader.app',
    icon='icon.ico',
    bundle_identifier='com.balistudios.awsuploader',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
    },
) 