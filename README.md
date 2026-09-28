# watermark-remover (Electron + GPU lokal, 1 halaman, tanpa login)

Upload video → satu tombol **Hapus Watermark** → full-clean
(visible + invisible + metadata) via `remove-ai-watermarks` memakai
GPU/VGA lokal. Tanpa opsi mode.

## Syarat (mesin Windows bergPU NVIDIA)

- Python 3.11–3.14, NVIDIA driver + CUDA, `ffmpeg` di PATH, Node 18+
- `pip install -r backend/requirements.txt`
- `pip install "remove-ai-watermarks[video,diffusion]"` (profil invisible = CUDA-only)

## Dev (tanpa compile, sekali perintah)

```bash
# sekali saja: venv + deps + frontend
uv venv --seed backend/.venv
uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
npm install && npm install --prefix frontend

# tiap hari: backend :8000 + frontend :5173 + electron (boleh npm/pnpm)
pnpm dev
# atau: npm run dev
```

Buka otomatis jendela Electron (mode dev, DevTools terbuka). Edit
`frontend/src/*` hot-reload langsung — tidak perlu build dmg tiap fix.
Backend dev pakai `backend/.venv`; install library test:
`uv pip install --python backend/.venv/bin/python "remove-ai-watermarks[video]"`.

Tiga proses terpisah tetap bisa (3 terminal): `dev:be`, `dev:fe`,
`dev:electron`.

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
