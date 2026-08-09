# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — File Manager (Linux .deb i Windows .exe)."""
from PyInstaller.utils.hooks import collect_all

datas = [('config/cloud_keys.example.json', 'config')]
binaries = []
hiddenimports = []

# pakiety z dynamicznymi importami / zasobami
for pkg in ('paramiko', 'smbprotocol', 'pyftpdlib'):
    tmp = collect_all(pkg)
    datas += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]

a = Analysis(
    ['file_manager.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='file-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icons/file_manager.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='file-manager',
)
