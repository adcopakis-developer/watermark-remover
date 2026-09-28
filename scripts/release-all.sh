#!/usr/bin/env bash
# SATU perintah untuk semua target: pnpm release (atau npm run release).
# Prinsip jujur: tiap target hanya dibuild bila backend exe arch tersebut
# tersedia — exe Python TIDAK bisa cross-build (ikut arch host).
# Yang belum tersedia di-skip dengan pesan actionable, bukan artefak rusak.
#
# Layout backend prebuilt (dibuat di hardware masing-masing via build-mac.sh /
# build-win.bat, lalu copy ke sini):
#   backend-dist/          <- dipakai aktif saat packaging (jangan edit manual)
#   prebuilt/backend-mac-arm64/
#   prebuilt/backend-mac-x64/      (dari Mac Intel)
#   prebuilt/backend-win-x64/      (dari Windows: dist\watermark-server\)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST_OS="$(uname -s)"
HOST_ARCH="$(uname -m)"
BUILT=()
SKIPPED=()

have_wine() { command -v wine >/dev/null 2>&1; }

build_backend_host() {
  # Build exe backend untuk arch HOST ini (butuh venv + pyinstaller).
  if [ ! -x backend/.venv/bin/pyinstaller ]; then
    echo "  ! backend/.venv tanpa pyinstaller — lewati build backend host"
    return 1
  fi
  rm -rf packaging/dist packaging/build
  (cd packaging && ../backend/.venv/bin/pyinstaller watermark-server.spec >/dev/null)
  rm -rf backend-dist && cp -R packaging/dist/watermark-server backend-dist
  return 0
}

use_prebuilt() {
  # $1 = nama dir prebuilt. Copy ke backend-dist bila ada.
  if [ -d "prebuilt/$1" ]; then
    rm -rf backend-dist && cp -R "prebuilt/$1" backend-dist
    return 0
  fi
  return 1
}

echo "==> [0/4] Frontend build"
npm run build --prefix frontend >/dev/null 2>&1
echo "    frontend OK"

echo "==> [1/4] macOS Apple Silicon (dmg arm64)"
if [ "$HOST_OS" = "Darwin" ] && [ "$HOST_ARCH" = "arm64" ]; then
  if build_backend_host && npx electron-builder --mac dmg --arm64 >/dev/null 2>&1; then
    BUILT+=("mac-arm64")
    echo "    OK: dist/*.arm64.dmg"
  else
    SKIPPED+=("mac-arm64 (build gagal — lihat log di atas)")
  fi
elif use_prebuilt "backend-mac-arm64"; then
  if npx electron-builder --mac dmg --arm64 >/dev/null 2>&1; then
    BUILT+=("mac-arm64")
  else
    SKIPPED+=("mac-arm64 (packaging gagal)")
  fi
else
  SKIPPED+=("mac-arm64 (butuh Mac arm64 ATAU prebuilt/backend-mac-arm64/)")
  echo "    SKIP: butuh Mac arm64 atau prebuilt/backend-mac-arm64/"
fi

echo "==> [2/4] macOS Intel (dmg x64)"
if [ "$HOST_OS" = "Darwin" ]; then
  if [ "$HOST_ARCH" = "x86_64" ]; then
    if build_backend_host && npx electron-builder --mac dmg --x64 >/dev/null 2>&1; then
      BUILT+=("mac-x64"); echo "    OK"
    else
      SKIPPED+=("mac-x64 (build gagal)")
    fi
  elif use_prebuilt "backend-mac-x64"; then
    if npx electron-builder --mac dmg --x64 >/dev/null 2>&1; then
      BUILT+=("mac-x64"); echo "    OK (backend dari prebuilt/)"
    else
      SKIPPED+=("mac-x64 (packaging gagal)")
    fi
  else
    SKIPPED+=("mac-x64 (butuh prebuilt/backend-mac-x64/ dari Mac Intel)")
    echo "    SKIP: copy backend-dist hasil Mac Intel ke prebuilt/backend-mac-x64/"
  fi
else
  SKIPPED+=("mac-x64 (dmg hanya bisa dirakit di macOS)")
  echo "    SKIP: dmg hanya bisa dirakit di macOS"
fi

echo "==> [3/4] Windows x64 (NSIS)"
if [ "$HOST_OS" = "MINGW"* ] || [ "$HOST_OS" = "MSYS"* ] || [ "$HOST_OS" = "CYGWIN"* ] || [ -n "${WINDIR:-}" ]; then
  ON_WIN=1
else
  ON_WIN=0
fi
if { [ "$ON_WIN" = "1" ] || have_wine; } && { use_prebuilt "backend-win-x64" || [ "$ON_WIN" = "1" ]; }; then
  if [ "$ON_WIN" = "1" ] && [ ! -d prebuilt/backend-win-x64 ]; then
    echo "    backend win belum ada — build dulu via scripts\\build-win.bat lalu pindahkan ke prebuilt/"
    SKIPPED+=("win-x64 (backend exe Windows belum ada)")
  elif npx electron-builder --win nsis --x64 >/dev/null 2>&1; then
    BUILT+=("win-x64"); echo "    OK"
  else
    SKIPPED+=("win-x64 (packaging gagal — lihat log)")
  fi
else
  SKIPPED+=("win-x64 (butuh Mesin Windows + prebuilt/backend-win-x64/)")
  echo "    SKIP: rakit di Windows (scripts\\build-win.bat) atau sediakan prebuilt/ + wine"
fi

echo ""
echo "========== HASIL =========="
if [ "${#BUILT[@]}" -gt 0 ]; then
  for b in "${BUILT[@]}"; do echo "  [BUILT]   $b"; done
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  for s in "${SKIPPED[@]}"; do echo "  [SKIP]    $s"; done
fi
echo "Artefak di dist/"
ls dist/ 2>/dev/null | grep -iE "\.dmg$|\.exe$" || echo "(belum ada installer)"
