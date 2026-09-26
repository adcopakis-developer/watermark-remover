"""Standalone backend: upload video + hapus watermark via CLI remove-ai-watermarks.

Jalan di mesin bergPU (tanpa login). Frontend Vite memanggil /api/*.
Install: pip install -r requirements.txt
         + pip install "remove-ai-watermarks[video]"        (CPU: visible+metadata)
         + pip install "remove-ai-watermarks[video,diffusion]" (GPU: + invisible)
         + ffmpeg di PATH
Run: uvicorn app:app --host 127.0.0.1 --port 8000
Env: RAIW_BIN (default: remove-ai-watermarks), STORAGE_DIR (default: ./storage)
"""

import asyncio
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

RAIW_BIN = os.environ.get("RAIW_BIN", "").strip() or "remove-ai-watermarks"
STORAGE = Path(os.environ.get("STORAGE_DIR", "./storage")).resolve()
STORE_FILE = STORAGE / "_store.json"
WIB = timezone(timedelta(hours=7))

ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".flv"}
MAX_BYTES = 500 * 1024 * 1024
MODES = ("visible", "metadata", "all", "invisible")
MARKS = ("auto", "sora", "veo", "seedance", "doubao", "dola", "hailuo", "kling")

app = FastAPI(title="watermark-remover")


def now_wib() -> str:
    return datetime.now(WIB).isoformat(timespec="seconds")


def load_store() -> list:
    if not STORE_FILE.exists():
        return []
    try:
        data = json.loads(STORE_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_store(rows: list) -> None:
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    tmp.replace(STORE_FILE)


def find_rec(rows: list, vid: str) -> Optional[dict]:
    return next((r for r in rows if r["id"] == vid), None)


class CleanBody(BaseModel):
    # Diabaikan: Electron selalu full-clean (visible + invisible + metadata)
    # memakai GPU lokal. Field dijaga agar request lama tetap valid.
    mode: str = "all"
    mark: str = "auto"


@app.get("/api/gpu")
async def gpu_status():
    """Cek GPU lokal (NVIDIA/CUDA) untuk invisible removal."""
    info = {"cuda": False, "detail": "GPU tidak terdeteksi"}
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            proc = await asyncio.create_subprocess_exec(
                nvidia_smi, "-L",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), 15)
            text = out.decode(errors="replace").strip()
            if text:
                info = {"cuda": True, "detail": text.splitlines()[0][:200]}
        except Exception:
            pass
    if not info["cuda"]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-c", "import torch;print(torch.cuda.is_available())",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), 60)
            if out.decode().strip() == "True":
                info = {"cuda": True, "detail": "torch.cuda tersedia"}
        except Exception:
            pass
    return info


async def run_cli(args: list[str], timeout: int = 3600) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            RAIW_BIN,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return {"code": 127, "stdout": "", "stderr": "binary tidak ditemukan", "timed_out": False}
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
        return {
            "code": proc.returncode or 0,
            "stdout": out.decode(errors="replace")[-8000:],
            "stderr": err.decode(errors="replace")[-8000:],
            "timed_out": False,
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {"code": 1, "stdout": "", "stderr": "timeout", "timed_out": True}


@app.get("/api/videos")
def list_videos():
    rows = sorted(load_store(), key=lambda r: r["created_at"], reverse=True)
    return {"data": rows}


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    rec = find_rec(load_store(), vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    return {"data": rec}


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Ekstensi {ext or '?'} tidak didukung.")
    STORAGE.mkdir(parents=True, exist_ok=True)
    vid = uuid.uuid4().hex[:12]
    dest = STORAGE / f"{vid}_src{ext}"
    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(400, "Ukuran melebihi 500MB.")
            f.write(chunk)
    rec = {
        "id": vid,
        "src_file": dest.name,
        "src_bytes": size,
        "out_file": None,
        "mode": None,
        "mark": None,
        "status": "uploaded",
        "report": None,
        "error": None,
        "created_at": now_wib(),
        "updated_at": now_wib(),
    }
    rows = load_store()
    rows.append(rec)
    save_store(rows)
    return {"data": rec}


@app.post("/api/videos/{vid}/identify")
async def identify_video(vid: str):
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    src = STORAGE / rec["src_file"]
    res = await run_cli(["video", "identify", str(src)])
    head = "TIMEOUT" if res["timed_out"] else f"exit={res['code']}"
    rec["report"] = f"[identify] {head}\nOUT:\n{res['stdout']}\nERR:\n{res['stderr']}"[:8000]
    rec["error"] = None if res["code"] == 0 else (res["stderr"] or res["stdout"])[-500:]
    rec["updated_at"] = now_wib()
    save_store(rows)
    return {"data": rec}


def build_args(mode: str, mark: str, src: str, out: str) -> list[str]:
    # Selalu full-clean: visible + invisible + metadata.
    # --invisible (profil VAE CUDA) hanya didukung MP4/MOV/M4V;
    # format lain otomatis fallback ke `video all` tanpa invisible.
    ext = Path(src).suffix.lower()
    if ext in (".mp4", ".mov", ".m4v"):
        args = ["video", "all", src, "-o", out, "--invisible"]
    else:
        args = ["video", "all", src, "-o", out]
    if mark != "auto":
        args += ["--mark", mark]
    return args


async def run_clean(vid: str, mode: str, mark: str) -> None:
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        return
    workdir = Path(tempfile.mkdtemp(prefix=f"vw-{vid}-"))
    try:
        src = STORAGE / rec["src_file"]
        ext = Path(rec["src_file"]).suffix.lower() or ".mp4"
        out = workdir / f"clean{ext}"
        res = await run_cli(build_args(mode, mark, str(src), str(out)), timeout=5400)
        rows = load_store()
        rec = find_rec(rows, vid)
        if not rec:
            return
        if res["timed_out"] or res["code"] != 0 or not out.exists():
            rec.update(
                status="failed",
                error=(res["stderr"] or res["stdout"])[-500:] or "Gagal memproses",
                report=f"[{mode}] exit={res['code']}\nOUT:\n{res['stdout']}\nERR:\n{res['stderr']}"[:8000],
                updated_at=now_wib(),
            )
        else:
            out_name = f"{vid}_clean{ext}"
            shutil.copy(out, STORAGE / out_name)
            rec.update(
                status="done",
                out_file=out_name,
                report=f"[{mode}] exit=0\nOUT:\n{res['stdout']}\nERR:\n{res['stderr']}"[:8000],
                error=None,
                updated_at=now_wib(),
            )
        save_store(rows)
    except Exception as e:  # noqa: BLE001
        rows = load_store()
        rec = find_rec(rows, vid)
        if rec:
            rec.update(status="failed", error=str(e)[-500:], updated_at=now_wib())
            save_store(rows)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.post("/api/videos/{vid}/clean")
async def clean_video(vid: str, body: CleanBody, bg: BackgroundTasks):
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    if rec["status"] == "processing":
        raise HTTPException(400, "Masih diproses, tunggu selesai.")
    rec.update(mode="all", mark="auto", status="processing",
               error=None, report="Diproses full-clean (GPU)...", updated_at=now_wib())
    save_store(rows)
    bg.add_task(run_clean, vid, "all", "auto")
    return {"data": rec}


@app.get("/api/videos/{vid}/download")
def download_video(vid: str, kind: str = "clean"):
    rec = find_rec(load_store(), vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    name = rec["out_file"] if kind == "clean" else rec["src_file"]
    if kind == "clean" and not name:
        raise HTTPException(404, "Belum ada hasil.")
    path = STORAGE / name
    if not path.exists():
        raise HTTPException(404, "File tidak ada di storage.")
    return FileResponse(path, filename=name)


@app.delete("/api/videos/{vid}")
def delete_video(vid: str):
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    for name in (rec["src_file"], rec.get("out_file") or ""):
        if name:
            (STORAGE / name).unlink(missing_ok=True)
    save_store([r for r in rows if r["id"] != vid])
    return {"ok": True}


if __name__ == "__main__":
    # Dipakai saat dibundle PyInstaller menjadi watermark-server(.exe).
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
