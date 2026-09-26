# -*- mode: python ; coding: utf-8 -*-
# Build di MESIN WINDOWS bergPU:
#   pip install pyinstaller "remove-ai-watermarks[video,diffusion]"
#   pyinstaller watermark-server.spec
# Hasil: dist/watermark-server/watermark-server.exe -> copy ke backend-dist/
# (onedir agar model/hook torch ikut; jangan --onefile untuk app GPU besar).

block_cipher = None

a = Analysis(
    ['..\\backend\\app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto'],
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
