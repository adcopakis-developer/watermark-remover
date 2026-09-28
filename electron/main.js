const { app, BrowserWindow, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const isDev = process.env.ELEC_DEV === '1';
const BACKEND_PORT = process.env.BACKEND_PORT || '8000';

// App GUI (launchd) dapat PATH minim: /usr/bin:/bin saja.
// Suntik lokasi umum agar backend bisa menemukan python3, pip,
// ~/Library/Python/*/bin, ~/.local/bin, dan ffmpeg (brew).
function buildBackendEnv() {
  const home = app.getPath('home');
  const extra = [
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    '/opt/homebrew/opt/ffmpeg/bin',
    '/opt/homebrew/opt/python/libexec/bin',
    '/usr/local/bin',
    `${home}/.local/bin`,
    `${home}/Library/Python/3.13/bin`,
    `${home}/Library/Python/3.12/bin`,
    `${home}/Library/Python/3.11/bin`,
  ];
  const seen = new Set();
  const clean = [];
  const base = (process.env.PATH || '').split(':');
  for (const p of [...extra, ...base]) {
    if (p && !seen.has(p) && fs.existsSync(p)) {
      seen.add(p);
      clean.push(p);
    }
  }
  return {
    ...process.env,
    PATH: clean.join(':'),
    BACKEND_PORT,
    STORAGE_DIR: path.join(app.getPath('userData'), 'storage'),
  };
}

let backendProc = null;
let mainWin = null;

function backendCandidates() {
  if (isDev) return [];
  const res = process.resourcesPath;
  const exe = process.platform === 'win32' ? 'watermark-server.exe' : 'watermark-server';
  return [path.join(res, 'backend-dist', exe)];
}

function startBackend() {
  return new Promise((resolve) => {
    if (isDev) {
      resolve();
      return;
    }
    const exe = backendCandidates().find((p) => fs.existsSync(p));
    if (!exe) {
      dialog.showErrorBox(
        'Backend hilang',
        'watermark-server tidak ditemukan di resources. Install ulang aplikasi.',
      );
      resolve();
      return;
    }
    backendProc = spawn(exe, [], {
      env: buildBackendEnv(),
      windowsHide: true,
    });
    backendProc.on('error', (err) => {
      dialog.showErrorBox('Backend gagal jalan', String((err && err.message) || err));
    });
    const timer = setTimeout(resolve, 2500);
    timer.unref?.();
  });
}

async function waitBackendReady(tries = 40) {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${BACKEND_PORT}/api/videos`);
      if (res.ok) return true;
    } catch {
      /* belum siap */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function createWindow() {
  mainWin = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Watermark Remover',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  if (isDev) {
    const fePort = process.env.FE_PORT || '5173';
    await mainWin.loadURL(`http://127.0.0.1:${fePort}`);
    mainWin.webContents.openDevTools({ mode: 'detach' });
  } else {
    await mainWin.loadFile(path.join(__dirname, '..', 'frontend', 'dist', 'index.html'));
  }
  mainWin.on('closed', () => {
    mainWin = null;
  });
}

app.whenReady().then(async () => {
  ipcMain.handle('select-folder', async () => {
    const res = await dialog.showOpenDialog({
      properties: ['openDirectory', 'createDirectory'],
    });
    return res.canceled ? null : res.filePaths[0] || null;
  });
  await startBackend();
  if (!isDev) {
    const ok = await waitBackendReady();
    if (!ok) {
      dialog.showErrorBox('Backend tidak merespons', 'Cek GPU/driver lalu restart aplikasi.');
    }
  }
  await createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow();
  });
});

app.on('window-all-closed', () => {
  if (backendProc) {
    try {
      backendProc.kill();
    } catch {
      /* abaikan */
    }
    backendProc = null;
  }
  if (process.platform !== 'darwin') app.quit();
});
