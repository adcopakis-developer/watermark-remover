// Launcher backend dev: pakai backend/.venv bila ada,
// else bootstrap otomatis (venv + requirements), lalu jalankan uvicorn.
// Cross-platform: macOS, Linux, Windows. Stdlib node saja.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(import.meta.url);
const root = path.dirname(path.dirname(here));
const backendDir = path.join(root, 'backend');
const reqFile = path.join(backendDir, 'requirements.txt');

export function venvPython() {
  return process.platform === 'win32'
    ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
    : path.join(backendDir, '.venv', 'bin', 'python');
}

function findSystemPython() {
  const cands =
    process.platform === 'win32'
      ? [{ cmd: 'py', extra: ['-3'] }, { cmd: 'python', extra: [] }, { cmd: 'python3', extra: [] }]
      : [{ cmd: 'python3', extra: [] }, { cmd: 'python', extra: [] }];
  for (const { cmd, extra } of cands) {
    try {
      const r = spawnSync(cmd, [...extra, '--version'], { stdio: 'ignore' });
      if (r.status === 0) return { cmd, extra };
    } catch {
      /* coba berikutnya */
    }
  }
  return null;
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: root });
  return r.status === 0;
}

export function ensureBackend() {
  let py = venvPython();
  if (existsSync(py)) return py;
  console.log('[setup] backend/.venv belum ada — bootstrap otomatis...');
  const sys = findSystemPython();
  if (!sys) {
    console.error('[setup] Python 3.11-3.13 tidak ditemukan. Install dulu: https://www.python.org/downloads/');
    process.exit(1);
  }
  if (!run(sys.cmd, [...sys.extra, '-m', 'venv', path.join(backendDir, '.venv')])) {
    console.error('[setup] gagal membuat venv.');
    process.exit(1);
  }
  py = venvPython();
  console.log('[setup] install backend/requirements.txt...');
  if (!run(py, ['-m', 'pip', 'install', '-r', reqFile])) {
    console.error('[setup] pip install gagal.');
    process.exit(1);
  }
  return py;
}

function main() {
  const py = ensureBackend();
  const port = process.env.BACKEND_PORT || '8000';
  // Suntik folder Scripts/bin venv ke PATH agar CLI (remove-ai-watermarks)
  // yang di-pip ke venv langsung terdeteksi backend.
  const venvBin = path.dirname(py);
  const env = {
    ...process.env,
    PATH: `${venvBin}${path.delimiter}${process.env.PATH || ''}`,
  };
  const child = spawn(
    py,
    ['-m', 'uvicorn', 'app:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', port],
    { stdio: 'inherit', cwd: root, env },
  );
  child.on('exit', (code) => process.exit(code ?? 1));
}

if (process.argv[1] && path.resolve(process.argv[1]) === here) {
  main();
}
