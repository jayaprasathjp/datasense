const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function postJson(path, body) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const errorBody = await response.json()
      detail = errorBody.detail || detail
    } catch { /* response wasn't JSON */ }
    throw new Error(`${path} failed (${response.status}): ${detail}`)
  }
  return response.json()
}

export function analyzeQuery(query, taskType = 'data_analysis') {
  return postJson('/api/analyze', { query, task_type: taskType })
}

export function analyzeQueryStream(query, taskType, callbacks, platform) {
  const body = JSON.stringify({ query, task_type: taskType, platform: platform || 'auto' })

  return fetch(`${BASE_URL}/api/analyze/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  }).then(async (response) => {
    if (!response.ok) {
      let detail = response.statusText
      try { const e = await response.json(); detail = e.detail || detail } catch {}
      throw new Error(`analyze/stream failed (${response.status}): ${detail}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let eventType = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('event: ')) {
          eventType = trimmed.slice(7).trim()
        } else if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6))
            if (callbacks.onEvent) callbacks.onEvent(eventType, data)
            if (eventType === 'token' && callbacks.onToken) callbacks.onToken(data.token)
            if (eventType === 'status' && callbacks.onStatus) callbacks.onStatus(data)
            if (eventType === 'code_ready' && callbacks.onCodeReady) callbacks.onCodeReady(data)
            if (eventType === 'result' && callbacks.onResult) callbacks.onResult(data)
            if (eventType === 'summary' && callbacks.onSummary) callbacks.onSummary(data.text)
            if (eventType === 'answer' && callbacks.onAnswer) callbacks.onAnswer(data.text)
            if (eventType === 'error' && callbacks.onError) callbacks.onError(data.message)
            if (eventType === 'done' && callbacks.onDone) callbacks.onDone()
          } catch {}
        }
      }
    }
  })
}

export function getDatasetInfo() {
  return fetch(`${BASE_URL}/api/dataset/info`).then(r => {
    if (!r.ok) throw new Error(`dataset/info failed (${r.status})`)
    return r.json()
  })
}

export function getAvailableDatasets() {
  return fetch(`${BASE_URL}/api/datasets`).then(r => {
    if (!r.ok) throw new Error(`datasets failed (${r.status})`)
    return r.json()
  })
}

export function loadDataset(key) {
  return postJson('/api/dataset/load', { key })
}

export async function uploadDataset(file) {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${BASE_URL}/api/dataset/upload`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const errorBody = await response.json()
      detail = errorBody.detail || detail
    } catch { /* */ }
    throw new Error(`upload failed (${response.status}): ${detail}`)
  }
  return response.json()
}
