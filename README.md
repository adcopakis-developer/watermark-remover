# watermark-remover (dev mode, 1 halaman, tanpa login)

Upload video/gambar → satu tombol **Hapus Watermark** → full-clean
(visible + invisible + metadata) via `remove-ai-watermarks` memakai
GPU/VGA lokal. Tanpa opsi mode.

Format: video (mp4/mov/m4v/webm/mkv/avi/flv) + gambar (png/jpg/jpeg/webp/bmp/tif/tiff/gif).

## Syarat

- Python 3.11–3.13, Node 18+
- `ffmpeg` di PATH
- NVIDIA driver + CUDA (opsional, untuk invisible watermark; tanpa GPU otomatis fallback CPU)
- `pip install -r backend/requirements.txt`
- `pip install "remove-ai-watermarks[video]"` (tambah `[video,diffusion]` bila ada GPU NVIDIA)

## Jalan (sekali perintah)

```bash
# sekali saja: clone + semua deps (postinstall otomatis install frontend)
npm i

# sekali saja: venv backend + cek ffmpeg/CLI (dev juga bootstrap otomatis bila lupa)
npm run setup
# bila remove-ai-watermarks belum ada, di venv: pip install "remove-ai-watermarks[video]"

# tiap hari: backend :8000 + frontend :5173 (tanpa aktivasi venv manual)
npm run dev
```

Buka http://127.0.0.1:5173. Edit `frontend/src/*` hot-reload langsung.

Tiga proses terpisah tetap bisa: `npm run dev:be`, `npm run dev:fe`.

## Cara pakai

1. Buka app → card **Library Pendukung** tampil status CLI + FFmpeg.
2. Belum hijau? Isi path manual di input (kosongkan = pakai PATH) → Simpan.
3. Drop banyak video → **Hapus Watermark Semua** → hasil di folder tanggal-jam.

## API backend

- `GET /api/setup/status` — status CLI/FFmpeg
- `GET /api/settings`, `PUT /api/settings` — output_root + path override
- `GET /api/gpu` — status CUDA lokal
- `GET /api/batches`, `POST /api/batches/upload` (multipart, max 500MB/file, max 50 file)
- `POST /api/batches/{id}/clean-all`
- `GET /api/videos/{id}/download?kind=clean|src`
- `DELETE /api/videos/{id}`, `DELETE /api/batches/{id}`
