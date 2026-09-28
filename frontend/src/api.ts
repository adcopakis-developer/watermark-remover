export type VwMode = 'visible' | 'metadata' | 'all' | 'invisible'

declare global {
  interface Window {
    watermarkApp?: { version: string; platform: string; selectFolder?: () => Promise<string | null> }
  }
}
export type VwMark =
  | 'auto' | 'sora' | 'veo' | 'seedance' | 'doubao' | 'dola' | 'hailuo' | 'kling'
export type VwStatus = 'uploaded' | 'processing' | 'done' | 'failed'

export interface VwRecord {
  id: string
  src_file: string
  src_bytes: number
  batch_id: string | null
  batch_name: string | null
  out_file: string | null
  mode: VwMode | null
  mark: VwMark | null
  status: VwStatus
  report: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface VwBatch {
  batch_id: string
  batch_name: string
  created_at: string
  videos: VwRecord[]
}

// Di Electron packaged (file://) tidak ada proxy vite,
// jadi API harus absolut ke backend lokal. Port sama dengan main.js.
const API_BASE =
  window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : ''

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + url, init)
  const text = await res.text()
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = JSON.parse(text) as { detail?: unknown }
      if (typeof body.detail === 'string') msg = body.detail
    } catch {
      if (text) msg = text.slice(0, 300)
    }
    throw new Error(msg)
  }
  return JSON.parse(text) as T
}

export interface SetupItem {
  key: string
  label: string
  required: boolean
  installed: boolean
  detail: string
  installing: boolean
}

export interface SetupStatus {
  ready: boolean
  installing: string | null
  items: SetupItem[]
  log: string
}

export const api = {
  settings: () => req<{ output_root: string }>('/api/settings'),
  saveSettings: (output_root: string) =>
    req<{ output_root: string }>('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ output_root }),
    }),
  meta: () => req<{ version: string; has_setup: boolean }>('/api/meta'),
  gpu: () => req<{ cuda: boolean; detail: string }>('/api/gpu'),
  setup: () => req<SetupStatus>('/api/setup/status'),
  installKey: (key: string) =>
    req<{ installing: string | null }>(`/api/setup/install/${key}`, { method: 'POST' }),
  batches: () => req<{ data: VwBatch[] }>('/api/batches').then((r) => r.data),

  uploadBatch: (files: File[], onProgress?: (pct: number) => void): Promise<VwBatch> => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', API_BASE + '/api/batches/upload')
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && e.total > 0) onProgress(Math.round((e.loaded / e.total) * 100))
        }
      }
      xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          let msg = `HTTP ${xhr.status}`
          try {
            const p = JSON.parse(xhr.responseText) as { detail?: unknown }
            if (typeof p.detail === 'string') msg = p.detail
          } catch {
            /* abaikan */
          }
          reject(new Error(msg))
          return
        }
        try {
          const b = (JSON.parse(xhr.responseText) as { data: VwBatch }).data
          resolve(b)
        } catch (err) {
          reject(err instanceof Error ? err : new Error('Respon tidak valid'))
        }
      }
      xhr.onerror = () => reject(new Error('Network error'))
      xhr.send(form)
    })
  },

  identify: (id: string) =>
    req<{ data: VwRecord }>(`/api/videos/${id}/identify`, { method: 'POST' }).then((r) => r.data),
  clean: (id: string) =>
    req<{ data: VwRecord }>(`/api/videos/${id}/clean`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }).then((r) => r.data),
  cleanAll: (batchId: string) =>
    req<{ data: { batch_id: string; queued: number } }>(`/api/batches/${batchId}/clean-all`, {
      method: 'POST',
    }),
  remove: (id: string) => req<{ ok: boolean }>(`/api/videos/${id}`, { method: 'DELETE' }),
  removeBatch: (batchId: string) =>
    req<{ ok: boolean }>(`/api/batches/${batchId}`, { method: 'DELETE' }),
  downloadUrl: (id: string, kind: 'clean' | 'src' = 'clean') =>
    `${API_BASE}/api/videos/${id}/download?kind=${kind}`,
}
