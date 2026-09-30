// Postinstall root: install deps frontend pakai package manager yang sama
// dengan yang dipakai di root (npm i -> npm, pnpm i -> pnpm).
// Deteksi via npm_config_user_agent. Stdlib node saja.
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(import.meta.url);
const root = path.dirname(path.dirname(here));
const frontendDir = path.join(root, 'frontend');

function main() {
  const ua = process.env.npm_config_user_agent || '';
  let cmd;
  let args;
  if (ua.includes('pnpm')) {
    cmd = 'pnpm';
    args = ['install', '--dir', frontendDir];
  } else if (ua.startsWith('yarn')) {
    cmd = 'yarn';
    args = ['--cwd', frontendDir, 'install'];
  } else {
    cmd = 'npm';
    args = ['install', '--prefix', frontendDir];
  }
  console.log(`[install] ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, {
    stdio: 'inherit',
    cwd: root,
    shell: process.platform === 'win32',
  });
  if (r.status !== 0) {
    console.error(
      `[install] gagal (exit ${r.status}). buka folder frontend manual lalu jalankan install di sana.`,
    );
    process.exit(r.status ?? 1);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === here) {
  main();
}
