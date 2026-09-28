// Setup sekali saja: venv + requirements + cek ffmpeg/CLI.
// Dijalankan via `npm run setup`. (`npm run dev` juga bootstrap
// otomatis bila venv belum ada.) Semua pesan berupa perintah siap salin.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureBackend, venvPython } from './dev-be.mjs';

const here = fileURLToPath(import.meta.url);
const isWin = process.platform === 'win32';

export function scriptsDir(
  platform = process.platform,
  appdata = process.env.APPDATA || '',
  home = os.homedir(),
) {
  if (platform === 'win32') {
    for (const tag of ['Python313', 'Python312', 'Python311']) {
      const d = path.join(appdata, 'Python', tag, 'Scripts');
      if (existsSync(path.join(d, 'remove-ai-watermarks.exe'))) return d;
    }
    return path.join(appdata, 'Python', 'Python312', 'Scripts');
  }
  return path.join(home, '.local', 'bin');
}

export function onPath(name) {
  try {
    return (
      spawnSync(isWin ? 'where' : 'which', [name], { stdio: 'ignore' }).status === 0
    );
  } catch {
    return false;
  }
}

function pipInstalled(py) {
  try {
    return (
      spawnSync(py, ['-m', 'pip', 'show', 'remove-ai-watermarks'], { stdio: 'ignore' })
        .status === 0
    );
  } catch {
    return false;
  }
}

function main() {
  const py = ensureBackend();

  if (onPath('ffmpeg')) {
    console.log('[setup] ffmpeg: OK di PATH');
  } else {
    const cmd = isWin
      ? 'winget install -e --id Gyan.FFmpeg'
      : 'brew install ffmpeg';
    console.log(`[setup] ffmpeg: TIDAK ADA — jalankan:\n  ${cmd}`);
  }

  const exeName = isWin ? 'remove-ai-watermarks.exe' : 'remove-ai-watermarks';
  if (onPath('remove-ai-watermarks')) {
    console.log('[setup] remove-ai-watermarks: OK di PATH');
  } else if (pipInstalled(py)) {
    const full = path.join(scriptsDir(), exeName);
    console.log('[setup] remove-ai-watermarks: terinstall tapi TIDAK di PATH.');
    console.log(`  Opsi 1 (termudah) — tempel path ini ke kolom Path di app:\n  ${full}`);
    const fix = isWin
      ? '[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:APPDATA\\Python\\Python312\\Scripts", "User")'
      : 'export PATH="$HOME/.local/bin:$PATH"';
    console.log(`  Opsi 2 — daftarkan ke PATH (PowerShell/terminal), tutup-buka terminal:\n  ${fix}`);
  } else {
    const cmd = isWin
      ? 'py -3.12 -m pip install --user "remove-ai-watermarks[video,diffusion]"'
      : 'python3 -m pip install --user "remove-ai-watermarks[video]"';
    console.log(`[setup] remove-ai-watermarks: BELUM ADA — jalankan:\n  ${cmd}`);
  }

  console.log(`[setup] selesai (python: ${py}). jalan: npm run dev`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === here) {
  main();
}
