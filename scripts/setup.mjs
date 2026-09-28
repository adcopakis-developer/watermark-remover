// Setup sekali saja: venv + requirements + cek ffmpeg/CLI.
// Dijalankan via `npm run setup`. (`npm run dev` juga bootstrap
// otomatis bila venv belum ada.)
import { spawnSync } from 'node:child_process';
import { ensureBackend, venvPython } from './dev-be.mjs';

const py = ensureBackend();

const whichCmd = process.platform === 'win32' ? 'where' : 'which';
let ffmpegOk = false;
try {
  ffmpegOk = spawnSync(whichCmd, ['ffmpeg'], { stdio: 'ignore' }).status === 0;
} catch {
  ffmpegOk = false;
}
console.log(
  ffmpegOk
    ? '[setup] ffmpeg: OK di PATH'
    : '[setup] ffmpeg: TIDAK ADA — install (winget install Gyan.FFmpeg / brew install ffmpeg) atau isi path manual di UI',
);

let cliOk = false;
try {
  cliOk =
    spawnSync(venvPython(), ['-m', 'pip', 'show', 'remove-ai-watermarks'], { stdio: 'ignore' })
      .status === 0;
} catch {
  cliOk = false;
}
console.log(
  cliOk
    ? '[setup] remove-ai-watermarks: OK'
    : '[setup] remove-ai-watermarks: BELUM ADA — pip install "remove-ai-watermarks[video]" (venv aktif) atau isi path manual di UI',
);

console.log(`[setup] selesai (python: ${py}). jalan: npm run dev`);
