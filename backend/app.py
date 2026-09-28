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
import subprocess
import sys
import tempfile
import time
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
SETTINGS_FILE = STORAGE / "_settings.json"
WIB = timezone(timedelta(hours=7))

ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".flv"}
MAX_BYTES = 500 * 1024 * 1024
MODES = ("visible", "metadata", "all", "invisible")
MARKS = ("auto", "sora", "veo", "seedance", "doubao", "dola", "hailuo", "kling")

app = FastAPI(title="watermark-remover")

APP_VERSION = "1.1.0"


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


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict) and data.get("output_root"):
                return data
    except Exception:
        pass
    return {"output_root": default_output_root()}


def save_settings(data: dict) -> None:
    STORAGE.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(SETTINGS_FILE)


def sanitize_stem(name: str) -> str:
    stem = Path(name or "video").stem
    clean = "".join(c if (c.isalnum() or c in ("-", "_", " ")) else "_" for c in stem).strip()
    return clean or "video"


class SettingsBody(BaseModel):
    output_root: str


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
    data = {"output_root": str(root)}
    save_settings(data)
    return data


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
                sys.executable, "-c", "import torch;print(torch.cuda.is_available())",
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
    binary = resolve_cli() or RAIW_BIN
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


SETUP_LOG = STORAGE / "_setup.log"
_setup: dict = {"installing": None}  # None | item key sedang diinstall


def user_site_bins() -> list[str]:
    """Lokasi binary pip --user per OS (semua versi minor yang didukung)."""
    cands = [str(Path.home() / ".local" / "bin")]
    if sys.platform == "darwin":
        for vers in ("3.14", "3.13", "3.12", "3.11"):
            cands.append(str(Path.home() / "Library" / "Python" / vers / "bin"))
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            for vers in ("313", "312", "311"):
                cands.append(str(Path(appdata) / "Python" / f"Python{vers}" / "Scripts"))
    return cands


def resolve_cli() -> Optional[str]:
    """Cari binary remove-ai-watermarks: env, venv, user-site, PATH."""
    suffix = ".exe" if os.name == "nt" else ""
    name = f"remove-ai-watermarks{suffix}"
    cands = []
    if RAIW_BIN != "remove-ai-watermarks":
        cands.append(RAIW_BIN)
    cands.append(str(Path(sys.executable).parent / name))
    cands.extend(str(Path(d) / name) for d in user_site_bins())
    found = shutil.which(name)
    if found:
        cands.append(found)
    for c in cands:
        if c and Path(c).exists():
            return c
    return None


def frozen_ffmpeg_dir() -> Optional[str]:
    """ffmpeg bawaan bundle PyInstaller (onedir): cari ffmpeg* di sebelah exe."""
    if not getattr(sys, "frozen", False):
        return None
    roots = [
        Path(sys.executable).parent / "_internal" / "imageio_ffmpeg" / "binaries",
        Path(sys.executable).parent / "imageio_ffmpeg" / "binaries",
    ]
    for d in roots:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            if f.name.startswith("ffmpeg") or f.suffix == ".exe":
                try:
                    if not os.access(f, os.X_OK):
                        os.chmod(f, 0o755)
                except Exception:
                    pass
                return str(d)
    return None


def ffmpeg_exe_dir() -> Optional[str]:
    """Dir ffmpeg: PATH, lalu bundle frozen, lalu import imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    frozen = frozen_ffmpeg_dir()
    if frozen:
        return frozen
    try:
        import imageio_ffmpeg  # type: ignore

        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if exe.exists():
            return str(exe.parent)
    except Exception:
        pass
    return None


def py_version_ok(interp: str) -> bool:
    """True bila interpreter Python >= 3.11 (syarat remove-ai-watermarks)."""
    try:
        r = subprocess.run(
            [interp, "-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])"],
            capture_output=True, timeout=30, check=True,
        )
        return int(r.stdout.decode().strip()) >= 311
    except Exception:
        return False


def pip_candidates() -> list[list[str]]:
    """Base command pip yang valid + Python >= 3.11. Urutan: venv,
    python3.11-3.14 eksplisit, python3, pip3. Python tua (Xcode/dll) dilewat."""
    ok: list[list[str]] = []
    interps = [sys.executable, "python3.14", "python3.13", "python3.12", "python3.11", "python3"]
    for interp in interps:
        base = [interp, "-m", "pip"]
        try:
            subprocess.run(base + ["--version"], capture_output=True, timeout=30, check=True)
        except Exception:
            continue
        if py_version_ok(interp):
            ok.append(base)
    try:
        r = subprocess.run(["pip3", "--version"], capture_output=True, timeout=30, check=True)
        import re

        m = re.search(r"python (\d+)\.(\d+)", r.stdout.decode())
        if m and int(m.group(1)) * 100 + int(m.group(2)) >= 311:
            ok.append(["pip3"])
    except Exception:
        pass
    return ok


def setup_append_log(text: str) -> None:
    try:
        STORAGE.mkdir(parents=True, exist_ok=True)
        with open(SETUP_LOG, "a") as f:
            f.write(f"[{now_wib()}] {text}\n")
    except Exception:
        pass


@app.get("/api/setup/status")
def setup_status():
    cli = resolve_cli()
    ffmpeg = ffmpeg_exe_dir() is not None
    pips = pip_candidates()
    python_ok = len(pips) > 0
    cuda = False
    try:
        cuda = bool(shutil.which("nvidia-smi"))
    except Exception:
        pass
    log = ""
    try:
        if SETUP_LOG.exists():
            log = "\n".join(SETUP_LOG.read_text().splitlines()[-30:])
    except Exception:
        pass
    items = [
        {
            "key": "python",
            "label": "Python ≥3.11 + pip",
            "required": True,
            "installed": python_ok,
            "detail": f"{pips[0][0]}" if python_ok else "tidak ditemukan",
            "installing": _setup["installing"] == "python",
        },        {
            "key": "cli",
            "label": "remove-ai-watermarks (+ffmpeg bila perlu)",
            "required": True,
            "installed": bool(cli),
            "detail": cli or "belum terinstall",
            "installing": _setup["installing"] == "cli",
        },
        {
            "key": "ffmpeg",
            "label": "FFmpeg",
            "required": True,
            "installed": ffmpeg,
            "detail": "tersedia" if ffmpeg else "belum ada",
            "installing": _setup["installing"] == "ffmpeg",
        },
        {
            "key": "cuda",
            "label": "NVIDIA CUDA (untuk invisible)",
            "required": False,
            "installed": cuda,
            "detail": "terdeteksi" if cuda else "tidak ada — fallback CPU otomatis",
            "installing": False,
        },
    ]
    resp: dict = {
        "ready": bool(cli and ffmpeg),
        "installing": _setup["installing"],
        "items": items,
        "log": log,
    }
    if os.environ.get("VW_DEBUG") == "1":
        exe = sys.executable
        probe = str(Path(exe).parent / "_internal" / "imageio_ffmpeg" / "binaries")
        try:
            listing = sorted(os.listdir(probe))
        except Exception as e:  # noqa: BLE001
            listing = [f"LIST_FAIL: {e}"]
        resp["_debug"] = {
            "frozen": getattr(sys, "frozen", False),
            "executable": exe,
            "probe": probe,
            "listing": listing,
        }
    return resp


async def run_pip_install(packages: list[str], tag: str) -> bool:
    """pip install --user paket; True bila sukses. Log ke SETUP_LOG."""
    cands = await asyncio.to_thread(pip_candidates)
    if not cands:
        setup_append_log("ERROR: tidak ada Python 3.11+ dengan pip. Install Python dulu.")
        return False
    up = await asyncio.to_thread(
        lambda: subprocess.run(cands[0] + ["install", "--upgrade", "pip"],
                               capture_output=True, timeout=300)
    )
    setup_append_log(f"[{tag}] pip upgrade exit={up.returncode}")
    cmd = cands[0] + ["install", "--user", *packages]
    setup_append_log(f"[{tag}] RUN: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        setup_append_log(f"[{tag}] " + raw.decode(errors="replace").rstrip()[-400:])
    await proc.wait()
    ok = proc.returncode == 0
    setup_append_log(f"[{tag}] {'OK' if ok else f'ERROR exit={proc.returncode}'}")
    return ok


async def do_install_key(key: str) -> None:
    _setup["installing"] = key
    try:
        STORAGE.mkdir(parents=True, exist_ok=True)
        if key == "cli":
            extra = "remove-ai-watermarks[video,diffusion]" if sys.platform == "win32" else "remove-ai-watermarks[video]"
            if await run_pip_install([extra, "imageio-ffmpeg"], "cli"):
                setup_append_log(f"OK: CLI -> {resolve_cli()}")
        elif key == "ffmpeg":
            await run_pip_install(["imageio-ffmpeg"], "ffmpeg")
        elif key == "python":
            if sys.platform == "darwin" and shutil.which("brew"):
                setup_append_log("[python] RUN: brew install python@3.12")
                proc = await asyncio.create_subprocess_exec(
                    "brew", "install", "python@3.12",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    setup_append_log("[python] " + raw.decode(errors="replace").rstrip()[-400:])
                await proc.wait()
                setup_append_log(f"[python] exit={proc.returncode}")
            elif sys.platform == "win32" and shutil.which("winget"):
                setup_append_log("[python] RUN: winget install Python.3.12")
                proc = await asyncio.create_subprocess_exec(
                    "winget", "install", "-e", "--id", "Python.3.12",
                    "--accept-package-agreements", "--accept-source-agreements",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    setup_append_log("[python] " + raw.decode(errors="replace").rstrip()[-400:])
                await proc.wait()
                setup_append_log(f"[python] exit={proc.returncode}")
            else:
                setup_append_log("ERROR: install Python otomatis tidak didukung di sini. "
                                 "Download manual: https://www.python.org/downloads/")
    except Exception as e:  # noqa: BLE001
        setup_append_log(f"ERROR: {e}")
    finally:
        _setup["installing"] = None


@app.post("/api/setup/install/{key}")
async def setup_install_key(key: str, bg: BackgroundTasks):
    if key not in ("python", "cli", "ffmpeg"):
        raise HTTPException(400, "key harus python|cli|ffmpeg")
    if _setup["installing"]:
        return {"installing": _setup["installing"]}
    bg.add_task(do_install_key, key)
    _setup["installing"] = key
    return {"installing": key}


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


def has_cuda_sync() -> bool:
    """Cek cepat GPU NVIDIA (tanpa load torch)."""
    if shutil.which("nvidia-smi"):
        return True
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import torch;print(torch.cuda.is_available())"],
            capture_output=True, timeout=60,
        )
        return r.returncode == 0 and r.stdout.decode().strip() == "True"
    except Exception:
        return False


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
                # CUDA ada tapi extra diffusion hilang: fallback CPU.
                res = await run_cli(["video", "all", str(src), "-o", str(out)], timeout=5400)
                warnings.append(INVISIBLE_WARN + " (extra diffusion tidak terinstall)")
        else:
            # Hemat: langsung CPU tanpa mencoba profil CUDA yang pasti gagal.
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
            # Hasil: {output_root}/{folder-datetime}/{nama}_clean_{fully|partially}{ext}.
            # Folder grup bulk = batch_name; upload satuan = stamp baru.
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


async def run_batch_clean(batch_id: str) -> None:
    """Bersihkan semua video grup yang belum done, berurutan."""
    rows = load_store()
    vids = [r["id"] for r in rows
            if r.get("batch_id") == batch_id and r.get("status") != "processing"]
    for vid in vids:
        rows = load_store()
        rec = find_rec(rows, vid)
        if not rec or rec.get("status") == "done":
            continue
        rec.update(mode="all", mark="auto", status="processing",
                   error=None, report="Diproses full-clean (GPU)...", updated_at=now_wib())
        save_store(rows)
        await run_clean(vid, "all", "auto")


@app.post("/api/batches/{batch_id}/clean-all")
async def clean_batch(batch_id: str, bg: BackgroundTasks):
    rows = load_store()
    vids = [r for r in rows if r.get("batch_id") == batch_id]
    if not vids:
        raise HTTPException(404, "Batch tidak ditemukan")
    if any(r.get("status") == "processing" for r in vids):
        raise HTTPException(400, "Batch masih diproses, tunggu selesai.")
    bg.add_task(run_batch_clean, batch_id)
    return {"data": {"batch_id": batch_id, "queued": len(vids)}}


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
    # Dipakai saat dibundle PyInstaller menjadi watermark-server(.exe).
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
