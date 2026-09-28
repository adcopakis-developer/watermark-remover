import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { VwBatch, VwRecord, VwSettings, VwSetup } from './api'

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exp = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, exp)).toFixed(exp === 0 ? 0 : 1)} ${units[exp]}`
}

function formatBatchName(name: string): string {
  const m = name.match(/^bulk_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/)
  if (!m) return name
  return `Bulk ${m[3]}-${m[2]}-${m[1]} ${m[4]}:${m[5]}:${m[6]}`
}

export default function App() {
  const [batches, setBatches] = useState<VwBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [busyBatch, setBusyBatch] = useState<string | null>(null)
  const [openReport, setOpenReport] = useState<string | null>(null)
  const [gpu, setGpu] = useState<string | null>(null)
  const [gpuOk, setGpuOk] = useState<boolean | null>(null)
  const [setup, setSetup] = useState<VwSetup | null>(null)
  const [settings, setSettings] = useState<VwSettings | null>(null)
  const [draft, setDraft] = useState<VwSettings | null>(null)
  const [appVersion, setAppVersion] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setBatches(await api.batches())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal memuat daftar')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    void api.meta().then((m) => setAppVersion(m.version ?? '?')).catch(() => {})
    void api.gpu().then((g) => {
      setGpuOk(g.cuda)
      setGpu(g.detail)
    }).catch(() => setGpu('Status GPU tidak diketahui'))
    void api.setup().then(setSetup).catch(() => setSetup(null))
    void api.settings().then((s) => {
      setSettings(s)
      setDraft(s)
    }).catch(() => {})
  }, [refresh])

  const handleSaveSettings = useCallback(async () => {
    if (!draft) return
    try {
      const s = await api.saveSettings(draft)
      setSettings(s)
      setDraft(s)
      const sr = await api.setup()
      setSetup(sr)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal menyimpan')
    }
  }, [draft])

  const anyProcessing = batches.some((b) => b.videos.some((v) => v.status === 'processing'))

  useEffect(() => {
    if (!anyProcessing) {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
      return
    }
    if (pollRef.current) return
    pollRef.current = window.setInterval(() => {
      void api.batches().then(setBatches).catch(() => {})
    }, 3000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [batches, anyProcessing])

  const handleFiles = useCallback(async (files: File[]) => {
    const vids = files.filter((f) => f.type.startsWith('video/') || /\.(mp4|mov|m4v|webm|mkv|avi|flv)$/i.test(f.name))
    if (vids.length === 0) {
      setError('Pilih file video (bisa banyak sekaligus)')
      return
    }
    setError(null)
    setUploadPct(0)
    try {
      await api.uploadBatch(vids, setUploadPct)
      setBatches(await api.batches())
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload gagal')
    } finally {
      setUploadPct(null)
    }
  }, [])

  const patchVideo = useCallback((rec: VwRecord) => {
    setBatches((prev) =>
      prev.map((b) => ({
        ...b,
        videos: b.videos.map((v) => (v.id === rec.id ? rec : v)),
      })),
    )
  }, [])

  const handleCleanAll = useCallback(async (batchId: string) => {
    setBusyBatch(batchId)
    setError(null)
    try {
      await api.cleanAll(batchId)
      setBatches(await api.batches())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal memulai bulk clean')
    } finally {
      setBusyBatch(null)
    }
  }, [])

  const handleIdentify = useCallback(
    async (id: string) => {
      setBusyId(id)
      setError(null)
      try {
        const rec = await api.identify(id)
        patchVideo(rec)
        setOpenReport(id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Identifikasi gagal')
      } finally {
        setBusyId(null)
      }
    },
    [patchVideo],
  )

  const handleDelete = useCallback(async (id: string) => {
    if (!window.confirm('Hapus video ini dari storage?')) return
    setBusyId(id)
    try {
      await api.remove(id)
      setBatches(await api.batches())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal menghapus')
    } finally {
      setBusyId(null)
    }
  }, [])

  const handleDeleteBatch = useCallback(async (batchId: string, name: string) => {
    if (!window.confirm(`Hapus seluruh grup ${name} dari storage?`)) return
    setBusyBatch(batchId)
    try {
      await api.removeBatch(batchId)
      setBatches(await api.batches())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal menghapus grup')
    } finally {
      setBusyBatch(null)
    }
  }, [])

  const ready = setup?.ready ?? false
  const cliPath = draft?.cli_path ?? ''
  const ffmpegPath = draft?.ffmpeg_path ?? ''
  const outputRoot = draft?.output_root ?? ''
  const activeRoot = settings?.output_root ?? ''

  return (
    <div className="wrap">
      <div className="card">
        <h2>Library Pendukung</h2>
        <table className="setup">
          <tbody>
            <tr>
              <td>remove-ai-watermarks</td>
              <td>
                <span className={`dot ${setup?.cli.installed ? 'ok' : 'no'}`} />
                <span className="path">{setup?.cli.path || 'tidak ditemukan'}</span>
              </td>
            </tr>
            <tr>
              <td>FFmpeg</td>
              <td>
                <span className={`dot ${setup?.ffmpeg.installed ? 'ok' : 'no'}`} />
                <span className="path">{setup?.ffmpeg.path || 'tidak ditemukan'}</span>
              </td>
            </tr>
          </tbody>
        </table>
        {draft && (
          <>
            <div className="row">
              <label className="field" style={{ flex: 1 }}>
                Path remove-ai-watermarks (kosongkan untuk pakai PATH)
                <input
                  type="text"
                  value={cliPath}
                  onChange={(e) => setDraft({ ...draft, cli_path: e.target.value })}
                  placeholder="/usr/local/bin/remove-ai-watermarks"
                />
              </label>
            </div>
            <div className="row">
              <label className="field" style={{ flex: 1 }}>
                Path FFmpeg (kosongkan untuk pakai PATH)
                <input
                  type="text"
                  value={ffmpegPath}
                  onChange={(e) => setDraft({ ...draft, ffmpeg_path: e.target.value })}
                  placeholder="/opt/homebrew/bin/ffmpeg"
                />
              </label>
            </div>
            <div className="row">
              <label className="field" style={{ flex: 1 }}>
                Folder hasil
                <input
                  type="text"
                  value={outputRoot}
                  onChange={(e) => setDraft({ ...draft, output_root: e.target.value })}
                />
              </label>
            </div>
            <div className="actions">
              <button onClick={() => void handleSaveSettings()}>Simpan</button>
              {!ready && (
                <span className="warnline">
                  Simpan dulu bila tidak ada CLI/FFmpeg. Upload dinonaktifkan.
                </span>
              )}
            </div>
            {activeRoot && activeRoot !== outputRoot && (
              <div className="muted">Aktif: {activeRoot}</div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h1>
          Watermark Remover{appVersion ? <span className="ver"> v{appVersion}</span> : ''}
        </h1>
        <div className="muted">
          Drop banyak video sekaligus → 1 tombol hapus semua watermark (visible + invisible +
          metadata) memakai GPU lokal. Hasil tiap bulk masuk folder baru sesuai tanggal-jam upload.
          {gpu && (
            <>
              <br />
              <span>GPU: {gpu}</span>
            </>
          )}
        </div>
        {gpuOk === false && (
          <div className="warnbox">
            Mode CPU: invisible watermark (pixel SynthID) <strong>dilewati otomatis</strong> karena
            GPU NVIDIA tidak terdeteksi. Visible + metadata tetap dibersihkan.
          </div>
        )}
        <div
          className="dropzone"
          style={{ outline: dragOver ? '2px dashed #2563eb' : undefined, opacity: ready ? 1 : 0.5 }}
          onDragOver={(e) => {
            e.preventDefault()
            if (ready) setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            if (ready) void handleFiles(Array.from(e.dataTransfer.files))
          }}
          onClick={() => ready && fileRef.current?.click()}
        >
          {uploadPct !== null ? (
            <span>Mengupload bulk {uploadPct}%...</span>
          ) : ready ? (
            <span>
              Tarik & letakkan video di sini, atau klik untuk pilih banyak file
              (mp4/mov/m4v/webm/mkv/avi/flv, max 500MB per file)
            </span>
          ) : (
            <span>Library belum siap — isi path CLI/FFmpeg di atas lalu Simpan.</span>
          )}
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,video/x-flv,.mp4,.mov,.m4v,.webm,.mkv,.avi,.flv"
            style={{ display: 'none' }}
            onChange={(e) => void handleFiles(Array.from(e.target.files ?? []))}
          />
        </div>
        <div className="row">
          <button className="ghost" onClick={() => void refresh()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="error"><div>{error}</div></div>}
      {loading && <div className="card muted">Memuat daftar...</div>}
      {!loading && batches.length === 0 && (
        <div className="card muted">Belum ada video. Drop file di atas.</div>
      )}

      {batches.map((b) => {
        const done = b.videos.filter((v) => v.status === 'done').length
        const busy = b.videos.some((v) => v.status === 'processing') || busyBatch === b.batch_id
        return (
          <div className="card" key={b.batch_id}>
            <div className="batch-head">
              <div>
                <h2>{formatBatchName(b.batch_name)}</h2>
                <div className="muted">
                  Folder hasil: <code>{activeRoot ? `${activeRoot}/${b.batch_name}/` : `${b.batch_name}/`}</code> —{' '}
                  {done}/{b.videos.length} selesai
                </div>
              </div>
              <div className="actions" style={{ marginTop: 0 }}>
                <button disabled={busy || !ready} onClick={() => void handleCleanAll(b.batch_id)}>
                  {busy ? 'Diproses...' : `Hapus Watermark Semua (${b.videos.length})`}
                </button>
                <button
                  className="danger"
                  disabled={busyBatch === b.batch_id}
                  onClick={() => void handleDeleteBatch(b.batch_id, b.batch_name)}
                >
                  Hapus Grup
                </button>
              </div>
            </div>
            <div className="grid">
              {b.videos.map((r) => {
                const vbusy = busyId === r.id || r.status === 'processing'
                return (
                  <div className="card inner" key={r.id}>
                    <video
                      src={r.out_file ? api.downloadUrl(r.id, 'clean') : api.downloadUrl(r.id, 'src')}
                      controls
                      preload="metadata"
                    />
                    <div className="meta">
                      <div className="name">{r.src_file}</div>
                      <div className="muted">
                        {formatBytes(r.src_bytes)} — {r.status}
                      </div>
                      {r.error && <div style={{ color: '#f87171', marginTop: 6 }}>{r.error}</div>}
                      {(r.warnings ?? []).map((w) => (
                        <div key={w.slice(0, 40)} className="warnline">
                          {w}
                        </div>
                      ))}
                      <div className="actions">
                        <button className="ghost" disabled={vbusy} onClick={() => void handleIdentify(r.id)}>
                          Cek Sinyal
                        </button>
                        {r.out_file && (
                          <a href={api.downloadUrl(r.id, 'clean')} download={r.out_file.split(/[\\/]/).pop()}>
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
      })}
    </div>
  )
}
