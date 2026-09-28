"""Standalone backend: upload video + hapus watermark via CLI remove-ai-watermarks.

Jalan di mesin lokal. Frontend Vite memanggil /api/*.
Require: `remove-ai-watermarks` (pip) + `ffmpeg` di PATH, atau path manual
di /api/settings (UI punya input).
Run: uvicorn app:app --host 127.0.0.1 --port 8000
Env: STORAGE_DIR (default: ./storage)
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

STORAGE = Path(os.environ.get("STORAGE_DIR", "./storage")).resolve()
STORE_FILE = STORAGE / "_store.json"
SETTINGS_FILE = STORAGE / "_settings.json"
WIB = timezone(timedelta(hours=7))

ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".flv"}
MAX_BYTES = 500 * 1024 * 1024
APP_VERSION = "1.1.0"

app = FastAPI(title="watermark-remover")


@app.get("/api/meta")
def meta():
    return {"version": APP_VERSION, "has_setup": True}


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


def batch_stamp() -> str:
    return datetime.now(WIB).strftime("bulk_%Y%m%d_%H%M%S")


def safe_join(name: str) -> Path:
    """Resolve path di dalam STORAGE (cegah traversal)."""
    p = (STORAGE / name).resolve()
    if p != STORAGE.resolve() and STORAGE.resolve() not in p.parents:
        raise HTTPException(400, "Path tidak valid")
    return p


def default_output_root() -> str:
    vids = Path.home() / "Videos" / "WatermarkRemover"
    try:
        vids.mkdir(parents=True, exist_ok=True)
        return str(vids)
    except Exception:
        fallback = Path("./output").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)


def default_settings() -> dict:
    return {"output_root": default_output_root(), "cli_path": "", "ffmpeg_path": ""}


def load_settings() -> dict:
    base = default_settings()
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                for k in base:
                    if isinstance(data.get(k), str):
                        base[k] = data[k]
    except Exception:
        pass
    return base


def save_settings(data: dict) -> None:
    STORAGE.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SETTINGS_FILE)


def sanitize_stem(name: str) -> str:
    stem = Path(name or "video").stem
    clean = "".join(c if (c.isalnum() or c in ("-", "_", " ")) else "_" for c in stem).strip()
    return clean or "video"


def is_executable_file(p: Path) -> bool:
    return p.is_file() and os.access(p, os.X_OK)


def default_cli_candidates() -> list[str]:
    """Lokasi umum pip --user (statis, tanpa subprocess). Windows: instalasi
    --user tidak masuk PATH, exe ada di %APPDATA%\\Python\\Python3xx\\Scripts."""
    name = "remove-ai-watermarks.exe" if os.name == "nt" else "remove-ai-watermarks"
    cands = [str(Path.home() / ".local" / "bin" / name)]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            for tag in ("Python313", "Python312", "Python311"):
                cands.append(str(Path(appdata) / "Python" / tag / "Scripts" / name))
    else:
        for ver in ("3.13", "3.12", "3.11"):
            cands.append(str(Path.home() / "Library" / "Python" / ver / "bin" / name))
    return cands


def resolve_cli_path() -> Optional[str]:
    """User override > shutil.which > lokasi umum pip --user."""
    s = load_settings()
    override = (s.get("cli_path") or "").strip()
    if override and is_executable_file(Path(override).expanduser()):
        return str(Path(override).expanduser().resolve())
    name = "remove-ai-watermarks.exe" if os.name == "nt" else "remove-ai-watermarks"
    found = shutil.which(name)
    if found:
        return found
    for c in default_cli_candidates():
        if is_executable_file(Path(c)):
            return c
    return None


def ffmpeg_exe_dir() -> Optional[str]:
    """Dir ffmpeg: user override > shutil.which."""
    s = load_settings()
    override = (s.get("ffmpeg_path") or "").strip()
    if override and is_executable_file(Path(override).expanduser()):
        return str(Path(override).expanduser().resolve().parent)
    found = shutil.which("ffmpeg")
    return str(Path(found).parent) if found else None


class SettingsBody(BaseModel):
    output_root: str
    cli_path: str = ""
    ffmpeg_path: str = ""


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.put("/api/settings")
def put_settings(body: SettingsBody):
    root = Path(body.output_root).expanduser()
    if not root.is_absolute():
        raise HTTPException(400, "Folder harus path absolut.")
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-test"
        probe.write_text("ok")
        probe.unlink()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Folder tidak bisa ditulis: {e}")
    for key, val in (("cli_path", body.cli_path), ("ffmpeg_path", body.ffmpeg_path)):
        v = (val or "").strip()
        if not v:
            continue
        p = Path(v).expanduser()
        if not is_executable_file(p):
            raise HTTPException(400, f"{key} tidak ditemukan / tidak bisa dieksekusi: {v}")
    save_settings({
        "output_root": str(root),
        "cli_path": body.cli_path.strip(),
        "ffmpeg_path": body.ffmpeg_path.strip(),
    })
    return load_settings()


@app.get("/api/setup/status")
def setup_status():
    cli = resolve_cli_path()
    ffmpeg = ffmpeg_exe_dir()
    return {
        "ready": bool(cli and ffmpeg),
        "cli": {"installed": bool(cli), "path": cli or ""},
        "ffmpeg": {"installed": bool(ffmpeg), "path": ffmpeg or ""},
    }


def has_cuda_sync() -> bool:
    """Cek cepat GPU NVIDIA. nvidia-smi = cukup, tanpa import torch."""
    return bool(shutil.which("nvidia-smi"))


@app.get("/api/gpu")
async def gpu_status():
    if await asyncio.to_thread(has_cuda_sync):
        return {"cuda": True, "detail": "GPU NVIDIA terdeteksi"}
    return {"cuda": False, "detail": "GPU tidak terdeteksi"}


async def run_cli(args: list[str], timeout: int = 3600) -> dict:
    binary = resolve_cli_path()
    if not binary:
        return {"code": 127, "stdout": "", "stderr": "binary tidak ditemukan", "timed_out": False}
    env = None
    ffmpeg_dir = ffmpeg_exe_dir()
    if ffmpeg_dir:
        env = {**os.environ, "PATH": f"{ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
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
        "orig_name": file.filename or dest.name,
        "src_bytes": size,
        "batch_id": None,
        "batch_name": None,
        "out_file": None,
        "out_folder": None,
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


@app.post("/api/batches/upload")
async def upload_batch(files: list[UploadFile] = File(...)):
    """Upload bulk: semua file masuk 1 grup batch + 1 folder hasil datetime."""
    if not files:
        raise HTTPException(400, "Tidak ada file.")
    if len(files) > 50:
        raise HTTPException(400, "Maksimal 50 file per bulk.")
    STORAGE.mkdir(parents=True, exist_ok=True)
    stamp = batch_stamp()
    batch_id = stamp
    rows = load_store()
    n = 1
    while any(r.get("batch_id") == batch_id for r in rows):
        n += 1
        batch_id = f"{stamp}_{n}"
    videos = []
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Ekstensi {ext or '?'} tidak didukung: {file.filename}")
        vid = uuid.uuid4().hex[:12]
        dest = STORAGE / f"{vid}_src{ext}"
        size = 0
        with dest.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(400, f"Melebihi 500MB: {file.filename}")
                f.write(chunk)
        rec = {
            "id": vid,
            "src_file": dest.name,
            "orig_name": file.filename or dest.name,
            "src_bytes": size,
            "batch_id": batch_id,
            "batch_name": batch_id,
            "out_file": None,
            "out_folder": None,
            "mode": None,
            "mark": None,
            "status": "uploaded",
            "report": None,
            "error": None,
            "created_at": now_wib(),
            "updated_at": now_wib(),
        }
        rows.append(rec)
        videos.append(rec)
    save_store(rows)
    return {"data": {"batch_id": batch_id, "batch_name": batch_id, "videos": videos}}


@app.get("/api/batches")
def list_batches():
    groups: dict[str, dict] = {}
    order: list[str] = []
    for r in sorted(load_store(), key=lambda x: x["created_at"]):
        bid = r.get("batch_id") or f"single_{r['id']}"
        if bid not in groups:
            groups[bid] = {
                "batch_id": bid,
                "batch_name": r.get("batch_name") or "Upload satuan",
                "created_at": r["created_at"],
                "videos": [],
            }
            order.append(bid)
        groups[bid]["videos"].append(r)
    return {"data": [groups[bid] for bid in reversed(order)]}


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


INVISIBLE_WARN = (
    "Tidak full-clean: invisible watermark (pixel SynthID) DILEWATI "
    "karena GPU NVIDIA/CUDA tidak terdeteksi. "
    "Visible + metadata tetap dibersihkan."
)


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
        warnings: list[str] = []
        cuda = await asyncio.to_thread(has_cuda_sync)
        if cuda:
            res = await run_cli(build_args(mode, mark, str(src), str(out)), timeout=5400)
            err_low = (res["stderr"] or "").lower()
            if res["code"] != 0 and ("cuda" in err_low or "diffusion" in err_low):
                res = await run_cli(["video", "all", str(src), "-o", str(out)], timeout=5400)
                warnings.append(INVISIBLE_WARN + " (extra diffusion tidak terinstall)")
        else:
            res = await run_cli(["video", "all", str(src), "-o", str(out)], timeout=5400)
            if ext in (".mp4", ".mov", ".m4v"):
                warnings.append(INVISIBLE_WARN)
        note = f" [{'; '.join(warnings)}]" if warnings else ""
        rows = load_store()
        rec = find_rec(rows, vid)
        if not rec:
            return
        if res["timed_out"] or res["code"] != 0 or not out.exists():
            rec.update(
                status="failed",
                warnings=warnings,
                error=(res["stderr"] or res["stdout"])[-500:] or "Gagal memproses",
                report=f"[{mode}]{note} exit={res['code']}\nOUT:\n{res['stdout']}\nERR:\n{res['stderr']}"[:8000],
                updated_at=now_wib(),
            )
        else:
            settings = load_settings()
            root = Path(settings["output_root"])
            root.mkdir(parents=True, exist_ok=True)
            folder = rec.get("batch_name") or batch_stamp()
            out_dir = root / folder
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = sanitize_stem(rec.get("orig_name") or rec["src_file"])
            tag = "clean_partially" if warnings else "clean_fully"
            dest = out_dir / f"{stem}_{tag}{ext}"
            n = 1
            while dest.exists():
                n += 1
                dest = out_dir / f"{stem}_{tag}_{n}{ext}"
            shutil.copy(out, dest)
            rec.update(
                status="done",
                out_file=str(dest),
                out_folder=str(out_dir),
                warnings=warnings,
                report=f"[{mode}]{note} exit=0\nOUT:\n{res['stdout']}\nERR:\n{res['stderr']}"[:8000],
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
async def clean_video(vid: str, body: dict, bg: BackgroundTasks):
    if not resolve_cli_path():
        raise HTTPException(400, "remove-ai-watermarks belum ditemukan. Isi path di Library Pendukung.")
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    if rec["status"] == "processing":
        raise HTTPException(400, "Masih diproses, tunggu selesai.")
    rec.update(mode="all", mark="auto", status="processing",
               error=None, report="Diproses full-clean...", updated_at=now_wib())
    save_store(rows)
    bg.add_task(run_clean, vid, "all", "auto")
    return {"data": rec}


@app.post("/api/batches/{batch_id}/clean-all")
async def clean_batch(batch_id: str, bg: BackgroundTasks):
    if not resolve_cli_path():
        raise HTTPException(400, "remove-ai-watermarks belum ditemukan. Isi path di Library Pendukung.")
    rows = load_store()
    vids = [r for r in rows if r.get("batch_id") == batch_id]
    if not vids:
        raise HTTPException(404, "Batch tidak ditemukan")
    if any(r.get("status") == "processing" for r in vids):
        raise HTTPException(400, "Batch masih diproses, tunggu selesai.")
    bg.add_task(_run_batch, batch_id)
    return {"data": {"batch_id": batch_id, "queued": len(vids)}}


async def _run_batch(batch_id: str) -> None:
    rows = load_store()
    vids = [r["id"] for r in rows
            if r.get("batch_id") == batch_id and r.get("status") != "processing"]
    for vid in vids:
        rows = load_store()
        rec = find_rec(rows, vid)
        if not rec or rec.get("status") == "done":
            continue
        rec.update(mode="all", mark="auto", status="processing",
                   error=None, report="Diproses full-clean...", updated_at=now_wib())
        save_store(rows)
        await run_clean(vid, "all", "auto")


def resolve_out(name: str) -> Path:
    """out_file boleh absolut (folder hasil pilihan user) atau relatif lama."""
    p = Path(name)
    if p.is_absolute():
        return p
    return safe_join(name)


@app.delete("/api/batches/{batch_id}")
def delete_batch(batch_id: str):
    rows = load_store()
    vids = [r for r in rows if r.get("batch_id") == batch_id]
    if not vids:
        raise HTTPException(404, "Batch tidak ditemukan")
    for rec in vids:
        if rec.get("src_file"):
            try:
                safe_join(rec["src_file"]).unlink(missing_ok=True)
            except HTTPException:
                pass
        if rec.get("out_file"):
            try:
                resolve_out(rec["out_file"]).unlink(missing_ok=True)
            except HTTPException:
                pass
    save_store([r for r in rows if r.get("batch_id") != batch_id])
    return {"ok": True}


@app.get("/api/videos/{vid}/download")
def download_video(vid: str, kind: str = "clean"):
    rec = find_rec(load_store(), vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    name = rec["out_file"] if kind == "clean" else rec["src_file"]
    if kind == "clean" and not name:
        raise HTTPException(404, "Belum ada hasil.")
    path = resolve_out(name) if kind == "clean" else safe_join(name)
    if not path.exists():
        raise HTTPException(404, "File tidak ada di storage.")
    return FileResponse(path, filename=Path(name).name)


@app.delete("/api/videos/{vid}")
def delete_video(vid: str):
    rows = load_store()
    rec = find_rec(rows, vid)
    if not rec:
        raise HTTPException(404, "Video tidak ditemukan")
    if rec.get("src_file"):
        try:
            safe_join(rec["src_file"]).unlink(missing_ok=True)
        except HTTPException:
            pass
    if rec.get("out_file"):
        try:
            resolve_out(rec["out_file"]).unlink(missing_ok=True)
        except HTTPException:
            pass
    save_store([r for r in rows if r["id"] != vid])
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
