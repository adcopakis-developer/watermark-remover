import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { VwRecord } from './api'

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exp = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, exp)).toFixed(exp === 0 ? 0 : 1)} ${units[exp]}`
}

export default function App() {
  const [rows, setRows] = useState<VwRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [openReport, setOpenReport] = useState<string | null>(null)
  const [gpu, setGpu] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await api.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal memuat daftar')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    void api
      .gpu()
      .then((g) => setGpu(g.cuda ? `GPU aktif: ${g.detail}` : `GPU tidak terdeteksi (${g.detail})`))
      .catch(() => setGpu('Status GPU tidak diketahui'))
  }, [refresh])

  useEffect(() => {
    if (!rows.some((r) => r.status === 'processing')) {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    if (pollRef.current) return
    pollRef.current = window.setInterval(() => {
      void api.list().then(setRows).catch(() => {})
    }, 3000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [rows])

  const handleUpload = useCallback(async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) {
      setError('Pilih file video dulu')
      return
    }
    setError(null)
    setUploadPct(0)
    try {
      const rec = await api.upload(file, setUploadPct)
      setRows((prev) => [rec, ...prev])
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload gagal')
    } finally {
      setUploadPct(null)
    }
  }, [])

  const mutate = useCallback(async (id: string, fn: (id: string) => Promise<VwRecord>) => {
    setBusyId(id)
    setError(null)
    try {
      const rec = await fn(id)
      setRows((prev) => prev.map((r) => (r.id === id ? rec : r)))
      return rec
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Aksi gagal')
      return null
    } finally {
      setBusyId(null)
    }
  }, [])

  const handleDelete = useCallback(
    async (id: string) => {
      if (!window.confirm('Hapus video ini dari storage?')) return
      setBusyId(id)
      try {
        await api.remove(id)
        setRows((prev) => prev.filter((r) => r.id !== id))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Gagal menghapus')
      } finally {
        setBusyId(null)
      }
    },
    [],
  )

  return (
    <div className="wrap">
      <div className="card">
        <h1>Watermark Remover</h1>
        <div className="muted">
          Upload video AI (mp4/mov/m4v/webm/mkv/avi/flv, max 500MB). Satu tombol:
          hapus watermark visible + invisible + metadata memakai GPU lokal.
          {gpu && (
            <>
              <br />
              <span>{gpu}</span>
            </>
          )}
        </div>
        <div className="row">
          <label className="field">
            File video
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,video/x-flv,.mp4,.mov,.m4v,.webm,.mkv,.avi,.flv"
            />
          </label>
          <button onClick={() => void handleUpload()} disabled={uploadPct !== null}>
            {uploadPct !== null ? `Mengupload ${uploadPct}%...` : 'Upload'}
          </button>
          <button className="ghost" onClick={() => void refresh()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {loading && <div className="card muted">Memuat daftar video...</div>}
      {!loading && rows.length === 0 && (
        <div className="card muted">Belum ada video. Upload dulu di atas.</div>
      )}

      <div className="grid">
        {rows.map((r) => {
          const busy = busyId === r.id || r.status === 'processing'
          return (
            <div className="card" key={r.id} style={{ padding: 0, overflow: 'hidden' }}>
              <video
                src={r.out_file ? api.downloadUrl(r.id, 'clean') : api.downloadUrl(r.id, 'src')}
                controls
                preload="metadata"
              />
              <div className="meta">
                <div className="name">{r.src_file}</div>
                <div className="muted">
                  {formatBytes(r.src_bytes)} — {r.status}
                  {r.mode ? ` — ${r.mode}${r.mark ? `/${r.mark}` : ''}` : ''}
                </div>
                {r.error && <div style={{ color: '#f87171', marginTop: 6 }}>{r.error}</div>}
                <div className="actions">
                  <button
                    className="ghost"
                    disabled={busy}
                    onClick={() =>
                      void mutate(r.id, api.identify).then((rec) => {
                        if (rec) setOpenReport(r.id)
                      })
                    }
                  >
                    Cek Sinyal
                  </button>
                  <button disabled={busy} onClick={() => void mutate(r.id, (id) => api.clean(id))}>
                    {r.status === 'processing' ? 'Diproses...' : 'Hapus Watermark'}
                  </button>
                  {r.out_file && (
                    <a href={api.downloadUrl(r.id, 'clean')} download={r.out_file}>
                      <button className="ghost">Download Hasil</button>
                    </a>
                  )}
                  <button className="danger" disabled={busyId === r.id} onClick={() => void handleDelete(r.id)}>
                    Hapus
                  </button>
                  {r.report && (
                    <button className="ghost" onClick={() => setOpenReport(openReport === r.id ? null : r.id)}>
                      {openReport === r.id ? 'Tutup Report' : 'Lihat Report'}
                    </button>
                  )}
                </div>
                {openReport === r.id && r.report && <pre>{r.report}</pre>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
