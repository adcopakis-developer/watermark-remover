export type VwMode = 'visible' | 'metadata' | 'all' | 'invisible'
export type VwMark =
  | 'auto' | 'sora' | 'veo' | 'seedance' | 'doubao' | 'dola' | 'hailuo' | 'kling'
export type VwStatus = 'uploaded' | 'processing' | 'done' | 'failed'

export interface VwRecord {
  id: string
  src_file: string
  src_bytes: number
  out_file: string | null
  mode: VwMode | null
  mark: VwMark | null
  status: VwStatus
  report: string | null
  error: string | null
  created_at: string
  updated_at: string
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
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

export const api = {
  gpu: () => req<{ cuda: boolean; detail: string }>('/api/gpu'),
  list: () => req<{ data: VwRecord[] }>('/api/videos').then((r) => r.data),
  upload: async (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    if (!onProgress) {
      return req<{ data: VwRecord }>('/api/videos/upload', { method: 'POST', body: form }).then(
        (r) => r.data,
      )
    }
    return new Promise<VwRecord>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/videos/upload')
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && e.total > 0) onProgress(Math.round((e.loaded / e.total) * 100))
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
          resolve((JSON.parse(xhr.responseText) as { data: VwRecord }).data)
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
  remove: (id: string) =>
    req<{ ok: boolean }>(`/api/videos/${id}`, { method: 'DELETE' }),
  downloadUrl: (id: string, kind: 'clean' | 'src' = 'clean') =>
    `/api/videos/${id}/download?kind=${kind}`,
}
