@echo off
REM Build installer Windows sekali jalan. Dijalankan dari root repo
REM di MESIN WINDOWS bergPU (Python + Node + CUDA + ffmpeg terinstall).
setlocal
cd /d %~dp0\..

echo [1/4] Backend venv + deps...
cd backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
pip install "remove-ai-watermarks[video,diffusion]"
pip install pyinstaller
cd ..

echo [2/4] PyInstaller backend...
cd packaging
pyinstaller watermark-server.spec
cd ..
rmdir /S /Q backend-dist 2>nul
xcopy packaging\dist\watermark-server backend-dist\ /E /I /Q

echo [3/4] Deps Electron + frontend...
call npm install
cd frontend && call npm install && cd ..

echo [4/4] Installer NSIS...
call npm run dist:win

echo.
echo SELESAI. Installer ada di folder release\. Klik dua kali untuk install,
echo lalu buka "Watermark Remover" dari Start Menu.
