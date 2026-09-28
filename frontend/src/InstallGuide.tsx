import { useState } from 'react'

type GuideOS = 'mac' | 'windows' | 'linux'

interface GuideStep {
  text: string
  cmd?: string
  note?: string
}

const OS_LABEL: Record<GuideOS, string> = {
  mac: 'Mac',
  windows: 'Windows',
  linux: 'Linux',
}

const STEPS: Record<GuideOS, GuideStep[]> = {
  mac: [
    {
      text: 'Install Homebrew (pengelola paket Mac) — lewati bila brew sudah ada. Tempel di Terminal, Enter, ikuti instruksi:',
      cmd: '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
    },
    {
      text: 'Install Python 3.12 dan FFmpeg:',
      cmd: 'brew install python@3.12 ffmpeg',
    },
    {
      text: 'Install library watermark:',
      cmd: 'python3.12 -m pip install --user "remove-ai-watermarks[video]"',
    },
    {
      text: 'Cek hasil (harus keluar nomor versi):',
      cmd: 'remove-ai-watermarks --version && ffmpeg -version',
    },
    {
      text: 'Bila muncul "command not found", jalankan ini lalu tutup-buka Terminal:',
      cmd: 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"',
    },
  ],
  windows: [
    {
      text: 'Install Python 3.12 (atau download dari python.org — centang Add to PATH). Di PowerShell/CMD:',
      cmd: 'winget install -e --id Python.Python.3.12',
    },
    {
      text: 'Install FFmpeg:',
      cmd: 'winget install -e --id Gyan.FFmpeg',
    },
    {
      text: 'Tutup terminal, buka terminal BARU, lalu install library (diffusion = untuk GPU NVIDIA):',
      cmd: 'py -3.12 -m pip install --user "remove-ai-watermarks[video,diffusion]"',
    },
    {
      text: 'Cek library:',
      cmd: 'remove-ai-watermarks --version',
    },
    {
      text: 'Cek FFmpeg:',
      cmd: 'ffmpeg -version',
      note: 'Bila "not recognized", tutup-buka terminal sekali lagi agar PATH terbaca.',
    },
  ],
  linux: [
    {
      text: 'Install Python dan FFmpeg (Ubuntu/Debian):',
      cmd: 'sudo apt update && sudo apt install -y python3-pip ffmpeg',
    },
    {
      text: 'Install library:',
      cmd: 'python3 -m pip install --user "remove-ai-watermarks[video]"',
      note: 'Bila error "externally-managed-environment", ulangi perintah dengan tambahan --break-system-packages.',
    },
    {
      text: 'Cek hasil (harus keluar nomor versi):',
      cmd: 'remove-ai-watermarks --version && ffmpeg -version',
    },
  ],
}

function detectOS(): GuideOS {
  const ua = navigator.userAgent.toLowerCase()
  const plat = (navigator.platform || '').toLowerCase()
  if (plat.startsWith('mac') || ua.includes('mac os')) return 'mac'
  if (plat.startsWith('win') || ua.includes('windows')) return 'windows'
  return 'linux'
}

export default function InstallGuide() {
  const [os, setOs] = useState<GuideOS>(detectOS)
  const [copied, setCopied] = useState<number | null>(null)

  const copy = async (cmd: string, i: number) => {
    try {
      await navigator.clipboard.writeText(cmd)
      setCopied(i)
      window.setTimeout(() => {
        setCopied((c) => (c === i ? null : c))
      }, 1500)
    } catch {
      setCopied(null)
    }
  }

  return (
    <details className="guide">
      <summary>Cara install FFmpeg &amp; remove-ai-watermarks (klik untuk buka)</summary>
      <div className="guide-tabs">
        {(Object.keys(OS_LABEL) as GuideOS[]).map((k) => (
          <button
            key={k}
            className={os === k ? 'active' : ''}
            onClick={() => {
              setOs(k)
              setCopied(null)
            }}
          >
            {OS_LABEL[k]}
          </button>
        ))}
      </div>
      <ol className="guide-steps">
        {STEPS[os].map((s, i) => (
          <li key={i}>
            <div>{s.text}</div>
            {s.cmd && (
              <div className="step-cmd">
                <code>{s.cmd}</code>
                <button className="copy-btn" onClick={() => void copy(s.cmd ?? '', i)}>
                  {copied === i ? 'Disalin!' : 'Salin'}
                </button>
              </div>
            )}
            {s.note && <div className="muted">{s.note}</div>}
          </li>
        ))}
      </ol>
      <div className="muted">
        Selesai? Kosongkan path di atas = pakai otomatis, atau isi path manual, lalu klik Simpan.
      </div>
    </details>
  )
}
