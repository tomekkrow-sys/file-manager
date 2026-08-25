# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — File Manager (Linux .deb i Windows .exe)."""
import os, glob
from PyInstaller.utils.hooks import collect_all

datas = [('config/cloud_keys.example.json', 'config'),
         ('resources/icons', 'resources/icons')]
binaries = []
hiddenimports = []

for pkg in ('paramiko', 'smbprotocol', 'pyftpdlib'):
    tmp = collect_all(pkg)
    datas += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]

# wlasne pakiety: wszystkie podmoduly (importy leniwe)
for pkgdir in ('core', 'ui'):
    for f in glob.glob(os.path.join(pkgdir, '**', '*.py'), recursive=True):
        mod = f[:-3].replace(os.sep, '.')
        if mod.endswith('.__init__'):
            mod = mod[:-9]
        hiddenimports.append(mod)
    datas.append((pkgdir, pkgdir))

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
