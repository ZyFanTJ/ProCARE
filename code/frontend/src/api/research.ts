import { api } from './client'

export async function brainstorm(job_id: string, topic?: string) {
  const res = await api.post('/brainstorm', { job_id, topic })
  return res.data as { hypotheses: string[] }
}

export async function uploadExcel(file: File, description?: string) {
  const fd = new FormData()
  fd.append('file', file)
  if (description) fd.append('description', description)
  const res = await api.post('/upload_excel', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data as { excel_path: string; excel_info: any; duplicate?: boolean; profile_reused?: boolean; md5?: string; job_id?: string }
}

export async function deleteProfile(md5: string) {
  const res = await api.delete(`/profile/${md5}`)
  return res.data as { ok: boolean }
}

export async function fetchProfiles() {
  const res = await api.get('/profiles')
  return res.data as Array<{
    md5: string
    path: string
    description?: string
    sheet_count: number
    profile_count: number
    updated_at: string
    size: number
  }>
}

export async function fetchProfileDetail(md5: string) {
  const res = await api.get(`/profile/${md5}`)
  return res.data as any
}

export async function analyzeProfile(
  md5: string,
  onMessage?: (msg: { status: string; message?: string; profile?: any }) => void
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api') as string;
  // Remove trailing slash if present
  const baseApi = baseApiRaw.endsWith('/') ? baseApiRaw.slice(0, -1) : baseApiRaw
  
  const response = await fetch(`${baseApi}/profile/${md5}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
     throw new Error(`Analysis failed: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) return;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data: ')) {
        try {
          const jsonStr = trimmed.slice(6);
          const data = JSON.parse(jsonStr);
          onMessage?.(data);
        } catch (e) {
          console.error('Failed to parse SSE message:', e);
        }
      }
    }
  }
}

export async function previewSheetData(md5: string, sheet: string, limit: number = 20) {
    const res = await api.get(`/profile/${md5}/data`, { params: { sheet, limit } })
    return res.data as { columns: string[]; data: any[]; total_preview_rows: number }
}

export async function generatePlan(payload: {
  topic: string
  excel_path: string
  excel_description?: string
  job_id?: string
}) {
  const res = await api.post('/plan', payload)
  return res.data as { job_id: string; plan: any }
}

export async function streamPlan(
  payload: { topic: string; excel_path: string; excel_description?: string; job_id?: string; mode?: string },
  onChunk?: (t: string) => void,
  onStatus?: (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => void,
  signal?: AbortSignal,
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api')
  const baseApi = baseApiRaw.replace(/\/$/, '')
  const url = `${baseApi}/plan?stream=1`
  onStatus && onStatus('connecting')
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
    body: JSON.stringify(payload),
    signal,
  })
  onStatus && onStatus(resp.ok ? 'streaming' : 'error')
  const reader = resp.body?.getReader()
  const decoder = new TextDecoder()
  let jobId: string | undefined
  let fullText = ''
  try {
    if (reader) {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        fullText += chunk
        if (!jobId) {
          const m = chunk.match(/JOB_ID:([\w-]+)/)
          if (m) jobId = m[1]
        }
        const show = chunk.replace(/JOB_ID:[^\n]*\n?/, '')
        if (show && onChunk) onChunk(show)
      }
    }
    onStatus && onStatus('done')
  } catch (e: any) {
    if (e && e.name === 'AbortError') onStatus && onStatus('interrupted')
    else onStatus && onStatus('error')
  }
  let plan: any = null
  try {
    const i = fullText.indexOf('{')
    if (i >= 0) {
      let d = 0
      for (let k = i; k < fullText.length; k++) {
        const c = fullText[k]
        if (c === '{') d++
        else if (c === '}') {
          d--
          if (d === 0) {
            const s = fullText.slice(i, k + 1)
            try { plan = JSON.parse(s) } catch {}
            break
          }
        }
      }
    }
    if (!plan) {
      const m = fullText.match(/\{[\s\S]*\}/)
      if (m) plan = JSON.parse(m[0])
    }
  } catch {}
  return { job_id: jobId, plan, text: fullText } as { job_id?: string; plan: any; text: string }
}

export async function refinePlan(job_id: string) {
  const res = await api.post('/plan_refine', { job_id })
  return res.data as { job_id: string; plan_initial?: any; plan_refined: any }
}

export async function streamRefinePlan(
  job_id: string,
  onChunk?: (t: string) => void,
  onStatus?: (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => void,
  signal?: AbortSignal,
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api')
  const baseApi = baseApiRaw.replace(/\/$/, '')
  const url = `${baseApi}/plan_refine?stream=1`
  onStatus && onStatus('connecting')
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
    body: JSON.stringify({ job_id }),
    signal,
  })
  onStatus && onStatus(resp.ok ? 'streaming' : 'error')
  const reader = resp.body?.getReader()
  const decoder = new TextDecoder()
  let fullText = ''
  try {
    if (reader) {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        fullText += chunk
        const show = chunk.replace(/JOB_ID:[^\n]*\n?/, '')
        if (show && onChunk) onChunk(show)
      }
    }
    onStatus && onStatus('done')
  } catch (e: any) {
    if (e && e.name === 'AbortError') onStatus && onStatus('interrupted')
    else onStatus && onStatus('error')
  }
  let plan_refined: any = null
  try {
    const i = fullText.indexOf('{')
    if (i >= 0) {
      let d = 0
      for (let k = i; k < fullText.length; k++) {
        const c = fullText[k]
        if (c === '{') d++
        else if (c === '}') {
          d--
          if (d === 0) {
            const s = fullText.slice(i, k + 1)
            try { const obj = JSON.parse(s); plan_refined = obj.plan_refined || obj } catch {}
            break
          }
        }
      }
    }
  } catch {}
  return { text: fullText, plan_refined }
}

export async function streamExecute(
  job_id: string,
  onEvent?: (event: any) => void,
  onStatus?: (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => void,
  signal?: AbortSignal,
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api')
  const baseApi = baseApiRaw.replace(/\/$/, '')
  const url = `${baseApi}/execute_opencode_stream`
  onStatus && onStatus('connecting')
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id }),
    signal,
  })
  onStatus && onStatus(resp.ok ? 'streaming' : 'error')
  const reader = resp.body?.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    if (reader) {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const event = JSON.parse(line)
            if (onEvent) onEvent(event)
          } catch (e) {
            console.warn('JSON parse error', e)
          }
        }
      }
    }
    onStatus && onStatus('done')
  } catch (e: any) {
    if (e && e.name === 'AbortError') onStatus && onStatus('interrupted')
    else onStatus && onStatus('error')
  }
}

export async function executeJob(job_id: string) {
  const res = await api.post('/execute', { job_id })
  return res.data as { success: boolean; report_path: string; logs?: any[]; plots?: string[] }
}

export async function executeJobAsync(job_id: string) {
  const res = await api.post('/execute_async', { job_id })
  return res.data as { started: boolean; job_id: string }
}

export async function fetchReport(jobId: string) {
  const res = await api.get(`/report/${jobId}`, { responseType: 'text' })
  return res.data as string
}

export async function savePlan(job_id: string, plan: any) {
  const res = await api.post('/plan_update', { job_id, plan })
  return res.data as { ok: boolean; job_id: string }
}

export async function updatePlan(job_id: string, plan: any) {
  const res = await api.post('/plan_update', { job_id, plan })
  return res.data as { ok: boolean; job_id: string }
}

export async function fetchStatus(jobId: string) {
  const res = await api.get(`/status/${jobId}`)
  return res.data as { running: boolean; success: boolean; logs: any[]; plots: string[]; current_step: number; max_iters: number; max_iters_reached?: boolean; message?: string; report_ready?: boolean; report_path?: string }
}

export async function listJobs() {
  const res = await api.get('/jobs')
  return res.data as { jobs: Array<{ job_id: string; topic?: string; success?: boolean; report_exists?: boolean; plots?: string[]; created_ts?: number }> }
}

export async function listUploads() {
  const res = await api.get('/uploads')
  return res.data as { files: Array<{ name: string; size?: number; created_ts?: number; url?: string }> }
}

export async function listReports() {
  const res = await api.get('/reports')
  return res.data as { reports: Array<{ job_id: string; report_url: string; static_url: string; created_ts?: number }> }
}

export async function regenReport(job_id: string) {
  const res = await api.post('/report_regen', { job_id })
  return res.data as { ok: boolean; report_path: string }
}

export async function generateSection(job_id: string, section_id: string, opts?: { human_note?: string; guidelines?: string }) {
  const payload: any = { job_id, section_id }
  if (opts?.human_note) payload.human_note = opts.human_note
  if (opts?.guidelines) payload.guidelines = opts.guidelines
  const res = await api.post('/generate_section', payload)
  return res.data as { section_id: string; content: string }
}

export async function composeReport(job_id: string, sections: string[], overrides?: Record<string, { human_note?: string; guidelines?: string }>, save?: boolean, use_existing: boolean = true) {
  const res = await api.post('/compose_report', { job_id, sections, overrides: overrides || {}, save: !!save, use_existing })
  return res.data as { ok: boolean; content: string; saved: boolean; report_path?: string | null }
}

export async function fetchSectionsMeta() {
  const res = await api.get('/sections_meta')
  return res.data as { sections: Array<{ id: string; title: string; desc?: string; default?: boolean; category?: string }> }
}

export async function composeReportAsync(job_id: string, sections: string[], overrides?: Record<string, { human_note?: string; guidelines?: string }>, use_existing: boolean = true) {
  const res = await api.post('/compose_report_async', { job_id, sections, overrides: overrides || {}, use_existing })
  return res.data as { started: boolean }
}

export async function fetchReportStatus(job_id: string) {
  const res = await api.get(`/report_status/${job_id}`)
  return res.data as { state?: string; step?: string; progress?: number; total?: number; completed?: number; report_path?: string }
}

export async function fetchReportPreview(job_id: string) {
  const res = await api.get(`/report_preview/${job_id}`, { responseType: 'text' })
  return res.data as string
}

export async function fetchJobPlan(job_id: string) {
  const res = await api.get(`/job/${job_id}/plan`)
  return res.data as any
}

export async function fetchExcelInfo(job_id: string) {
  const res = await api.get(`/job/${job_id}/excel_info`)
  return res.data as any
}

export async function fetchExecLogs(job_id: string) {
  const res = await api.get(`/job/${job_id}/exec_logs`)
  return res.data as { success?: boolean; logs?: any[] }
}

export async function fetchAnalysisCode(job_id: string) {
  const res = await api.get(`/job/${job_id}/analysis_code`, { responseType: 'text' })
  return res.data as string
}

export type ContractSummary = {
  job_id: string
  exists: boolean
  trace?: any
  files?: Record<string, string | null>
  artifacts?: any
}

export async function compileContract(job_id: string) {
  const res = await api.post(`/contract/${job_id}/compile`)
  return res.data as ContractSummary
}

export async function fetchContract(job_id: string, include_artifacts: boolean = false) {
  const res = await api.get(`/contract/${job_id}`, { params: { include_artifacts } })
  return res.data as ContractSummary
}

export async function fetchProfileContract(job_id: string) {
  const res = await api.get(`/contract/${job_id}/profile`)
  return res.data as any
}

export async function fetchRwsIr(job_id: string) {
  const res = await api.get(`/contract/${job_id}/rws_ir`)
  return res.data as any
}

export async function fetchContractValidation(job_id: string) {
  const res = await api.get(`/contract/${job_id}/validation`)
  return res.data as any
}

export async function fetchEvidenceCertificates(job_id: string) {
  const res = await api.get(`/contract/${job_id}/certificates`)
  return res.data as any
}

export async function streamRunCode(
  job_id: string,
  onChunk?: (t: string) => void,
  onStatus?: (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => void,
  signal?: AbortSignal,
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api')
  const baseApi = baseApiRaw.replace(/\/$/, '')
  const url = `${baseApi}/run_code_stream`
  onStatus && onStatus('connecting')
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id }),
    signal,
  })
  onStatus && onStatus(resp.ok ? 'streaming' : 'error')
  const reader = resp.body?.getReader()
  const decoder = new TextDecoder()
  try {
    if (reader) {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        if (onChunk) onChunk(chunk)
      }
    }
    onStatus && onStatus('done')
  } catch (e: any) {
    if (e && e.name === 'AbortError') onStatus && onStatus('interrupted')
    else onStatus && onStatus('error')
  }
}
export async function fetchReportSections(job_id: string) {
  const res = await api.get(`/report_sections/${job_id}`)
  return res.data as { sections: Array<{ id: string; path: string; size: number; mtime: number }> }
}

export async function saveReport(job_id: string, content: string) {
  const res = await api.post('/save_report', { job_id, content })
  return res.data as { ok: boolean; report_path: string; url: string }
}

export type PaperStatus = {
  job_id: string
  task_id: string
  status: string
  error?: string | null
  output_file?: string | null
  latex_file?: string | null
  figure_dir?: string | null
  latex_project_dir?: string | null
  latex_zip?: string | null
  bibliography_file?: string | null
  pdf_url?: string | null
  tex_url?: string | null
  figures_url?: string | null
  latex_project_url?: string | null
  latex_zip_url?: string | null
  bib_url?: string | null
  compile_engine?: string | null
  llm_model?: string | null
  updated_at?: string | null
}

export async function generatePaper(job_id: string, opts?: {
  llm_enabled?: boolean
  report_language?: string
  report_name?: string
  template_path?: string
  writing_requirements?: string
  llm_timeout_seconds?: number
  reference_files?: File[]
}) {
  const files = opts?.reference_files || []
  if (files.length) {
    const fd = new FormData()
    fd.append('llm_enabled', String(opts?.llm_enabled ?? true))
    fd.append('report_language', opts?.report_language || 'zh')
    if (opts?.report_name) fd.append('report_name', opts.report_name)
    if (opts?.template_path) fd.append('template_path', opts.template_path)
    if (opts?.writing_requirements) fd.append('writing_requirements', opts.writing_requirements)
    if (opts?.llm_timeout_seconds) fd.append('llm_timeout_seconds', String(opts.llm_timeout_seconds))
    files.forEach((file) => fd.append('reference_files', file))
    const res = await api.post(`/paper/${job_id}/generate`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data as PaperStatus
  }
  const res = await api.post(`/paper/${job_id}/generate`, {
    llm_enabled: opts?.llm_enabled ?? true,
    report_language: opts?.report_language ?? 'zh',
    report_name: opts?.report_name,
    template_path: opts?.template_path,
    writing_requirements: opts?.writing_requirements,
    llm_timeout_seconds: opts?.llm_timeout_seconds,
  })
  return res.data as PaperStatus
}

export async function fetchPaperStatus(job_id: string) {
  const res = await api.get(`/paper/${job_id}`)
  return res.data as PaperStatus
}

export async function deleteJob(job_id: string) {
  const res = await api.delete(`/job/${job_id}`)
  return res.data as { ok: boolean }
}

export async function streamSandboxCode(
  job_id: string,
  code: string,
  onChunk?: (t: string) => void,
  onStatus?: (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => void,
  signal?: AbortSignal,
) {
  const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api')
  const baseApi = baseApiRaw.replace(/\/$/, '')
  const url = `${baseApi}/sandbox/run`
  onStatus && onStatus('connecting')
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id, code }),
      signal,
    })
    if (!resp.ok) {
        onStatus && onStatus('error')
        const text = await resp.text()
        if (onChunk) onChunk(`Error: ${text}`)
        return
    }
    onStatus && onStatus('streaming')
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    if (reader) {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        if (onChunk) onChunk(chunk)
      }
    }
    onStatus && onStatus('done')
  } catch (e: any) {
    if (e && e.name === 'AbortError') onStatus && onStatus('interrupted')
    else onStatus && onStatus('error')
  }
}
