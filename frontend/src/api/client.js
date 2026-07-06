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
    } catch {
      // response wasn't JSON, keep statusText
    }
    throw new Error(`${path} failed (${response.status}): ${detail}`)
  }

  return response.json()
}

/** POST /api/synthesize -> { cpu_code, gpu_code } */
export function synthesizeCode(query, taskType = 'data_analysis') {
  return postJson('/api/synthesize', { query, task_type: taskType })
}

/** POST /api/execute-cpu -> { execution_time_sec, status, results } */
export function executeCpu(code) {
  return postJson('/api/execute-cpu', { code })
}

/** POST /api/execute-gpu -> { execution_time_sec, results, logs } */
export function executeGpu(code) {
  return postJson('/api/execute-gpu', { code })
}
