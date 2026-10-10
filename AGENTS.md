# AGENTS.md

Local-only tool: upload video/image → strip AI watermarks (visible + invisible + metadata) by shelling out to the `remove-ai-watermarks` CLI on local GPU/CPU. No auth, no DB, dev mode only.

## Layout

- `backend/app.py` — the entire FastAPI backend (625 lines, every route lives here). File-based JSON state under `storage/`.
- `frontend/src/` — React 19 + Vite 7 + TS. `App.tsx` is the main UI, `api.ts` holds types + the `fetch` wrapper, `InstallGuide.tsx` the setup help.
- `scripts/*.mjs` — Node orchestration only (`setup.mjs`, `dev-be.mjs`, `install-fe.mjs`). Root `package.json` just wires these.
- Root `storage/` is gitignored runtime state. `backend/storage/` is a stray leftover — ignore it.

## Commands (run from repo root)

- `npm i` — postinstall auto-installs frontend deps with the same package manager you invoked (npm/pnpm/yarn).
- `npm run setup` — one-time: create `backend/.venv`, pip install `backend/requirements.txt`, check ffmpeg + CLI.
- `npm run dev` — backend :8000 + frontend :5173 together. Bootstraps `backend/.venv` automatically if missing.
- `npm run dev:be` / `npm run dev:fe` — run one side only.
- `npm run build --prefix frontend` — the only real check: `tsc -b --noEmit && vite build`.

## No lint / test / CI

There is no eslint, prettier, test runner, or CI config anywhere. Do not add or invoke one unless asked. Verification = the TS build plus a manual run.

## Gotchas

- Runtime deps NOT in `backend/requirements.txt`: the `remove-ai-watermarks` pip CLI and `ffmpeg` on PATH. The backend shells out to both; without them `/api/setup/status` reports not-ready. Install: `pip install "remove-ai-watermarks[video]"`; add `,qwen-zimage` for invisible (SynthID) removal on an NVIDIA GPU. The `[diffusion]` extra is NOT enough — `REMOVAL_MODULES` needs `diffsynth` (only in `[qwen-zimage]`).
- Invisible image removal needs CLI `all --force`; without it the CLI silently skips step 2 (`--no-force` default) and the app reports `done`. Gated on `GET /api/capability` → `full_clean` (autodetects CUDA via `torch.cuda.is_available()` on the CLI's own interpreter + the `[qwen-zimage]` modules). `?refresh=1` re-probes after installing the extra.
- Frontend calls relative `/api/*` with no base URL, so it only works through the Vite proxy (`/api` → `127.0.0.1:8000`). The backend does not serve `frontend/dist`.
- Ports are env-overridable and must stay in sync between `scripts/dev-be.mjs` (`BACKEND_PORT`) and `vite.config.ts` (`BACKEND_PORT`/`FE_PORT`).
- Backend state = `storage/_store.json` + `storage/_settings.json`; override the dir with `STORAGE_DIR`. Paths resolve from cwd (repo root under `npm run dev`).
- Package manager is pnpm (`pnpm-lock.yaml` tracked at root and in `frontend/`); `package-lock.json` is gitignored. Use pnpm when adding deps.
- Hardcoded limits in `backend/app.py`: 500 MB/file, 50 files/batch, allowed extensions in `IMAGE_EXT`/`VIDEO_EXT`.
