#!/usr/bin/env bash
# Build/test app macOS Apple Silicon sekali jalan. Dijalankan dari root repo.
# Syarat: Python 3.11-3.14, Node 18+, ffmpeg (brew install ffmpeg).
# Catatan: Mac tanpa NVIDIA CUDA — mode invisible gagal anggun;
# visible + metadata tetap bisa dites bila library terinstall.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] Backend venv + deps..."
if [ ! -d backend/.venv ]; then uv venv backend/.venv; fi
uv pip install --python backend/.venv/bin/python -q -r backend/requirements.txt
uv pip install --python backend/.venv/bin/python -q pyinstaller
# Opsional (CPU test): uv pip install --python backend/.venv/bin/python "remove-ai-watermarks[video]"

echo "[2/4] PyInstaller backend..."
cd packaging
../backend/.venv/bin/pyinstaller watermark-server.spec
cd ..
rm -rf backend-dist && cp -R packaging/dist/watermark-server backend-dist

echo "[3/4] Deps Electron + frontend..."
npm install --no-audit --no-fund
npm install --prefix frontend --no-audit --no-fund

echo "[4/4] DMG arm64..."
npm run dist:mac

echo ""
echo "SELESAI. File .dmg ada di folder release/. Klik dua kali untuk install."
