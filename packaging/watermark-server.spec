# -*- mode: python ; coding: utf-8 -*-
# Build di MESIN WINDOWS bergPU, dari folder packaging/:
#   cd packaging && pyinstaller watermark-server.spec
# Hasil: packaging/dist/watermark-server/ -> copy ke ..\backend-dist\
# (onedir agar hook torch ikut; jangan --onefile untuk app GPU besar).
# Atau sekali jalan dari root: scripts\build-win.bat
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# imageio_ffmpeg: kumpulkan SEMUA sebagai file (bukan arsip) agar
# __file__ package mengarah ke dir nyata berisi binary ffmpeg.
imageio_datas, imageio_bins, imageio_hidden = collect_all('imageio_ffmpeg')

# Path portable: dijalankan dari folder packaging/ (mac & windows).
a = Analysis(
    ['../backend/app.py'],
    pathex=[],
    binaries=imageio_bins,
    datas=imageio_datas,
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto'] + imageio_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='watermark-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='watermark-server',
)
