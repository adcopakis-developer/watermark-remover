# watermark-remover (Electron + GPU lokal, 1 halaman, tanpa login)

Upload video → satu tombol **Hapus Watermark** → full-clean
(visible + invisible + metadata) via `remove-ai-watermarks` memakai
GPU/VGA lokal. Tanpa opsi mode.

## Syarat (mesin Windows bergPU NVIDIA)

- Python 3.11–3.14, NVIDIA driver + CUDA, `ffmpeg` di PATH, Node 18+
- `pip install -r backend/requirements.txt`
- `pip install "remove-ai-watermarks[video,diffusion]"` (profil invisible = CUDA-only)

## Dev

```bat
REM terminal 1 — backend :8000
cd backend && uvicorn app:app --host 127.0.0.1 --port 8000

REM terminal 2 — frontend :5173
cd frontend && npm install && npm run dev

REM terminal 3 — electron (setelah 2 di atas jalan)
set ELEC_DEV=1 && npx electron .
```

## Build installer Windows (di mesin Windows GPU, sekali jalan)

```bat
git clone https://github.com/adcopakis-developer/watermark-remover.git
cd watermark-remover
scripts\build-win.bat
```

Script mengerjakan: venv + `remove-ai-watermarks[video,diffusion]` +
PyInstaller (`packaging/`) → copy ke `backend-dist/` → `npm run dist:win`.
Hasil: installer NSIS x64 di `release/`. Klik dua kali untuk install,
buka "Watermark Remover" dari Start Menu (backend ikut nyala otomatis,
storage di `%APPDATA%\Watermark Remover\storage`).

Catatan: Windows SmartScreen mungkin memberi peringatan (app tanpa
code-sign) → pilih install anyway. Badge GPU di halaman utama harus
bertuliskan aktif; jika tidak, cek driver NVIDIA/CUDA.

## API backend

- `GET /api/gpu` — status CUDA lokal
- `GET /api/videos`, `GET /api/videos/{id}`
- `POST /api/videos/upload` (multipart, max 500MB)
- `POST /api/videos/{id}/identify`
- `POST /api/videos/{id}/clean` — selalu full-clean GPU
- `GET /api/videos/{id}/download?kind=clean|src`
- `DELETE /api/videos/{id}`

Hapus folder ini = uninstall total.
