import { api } from './client';
export async function uploadExcel(file, description) {
    const fd = new FormData();
    fd.append('file', file);
    if (description)
        fd.append('description', description);
    const res = await api.post('/upload_excel', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
}
export async function generatePlan(payload) {
    const res = await api.post('/plan', payload);
    return res.data;
}
export async function streamPlan(payload, onChunk, onStatus, signal) {
    const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api');
    const baseApi = baseApiRaw.replace(/\/$/, '');
    const url = `${baseApi}/plan?stream=1`;
    onStatus && onStatus('connecting');
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
        body: JSON.stringify(payload),
        signal,
    });
    onStatus && onStatus(resp.ok ? 'streaming' : 'error');
    const reader = resp.body?.getReader();
    const decoder = new TextDecoder();
    let jobId;
    let fullText = '';
    try {
        if (reader) {
            while (true) {
                const { value, done } = await reader.read();
                if (done)
                    break;
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;
                if (!jobId) {
                    const m = chunk.match(/JOB_ID:([\w-]+)/);
                    if (m)
                        jobId = m[1];
                }
                const show = chunk.replace(/JOB_ID:[^\n]*\n?/, '');
                if (show && onChunk)
                    onChunk(show);
            }
        }
        onStatus && onStatus('done');
    }
    catch (e) {
        if (e && e.name === 'AbortError')
            onStatus && onStatus('interrupted');
        else
            onStatus && onStatus('error');
    }
    let plan = null;
    try {
        const i = fullText.indexOf('{');
        if (i >= 0) {
            let d = 0;
            for (let k = i; k < fullText.length; k++) {
                const c = fullText[k];
                if (c === '{')
                    d++;
                else if (c === '}') {
                    d--;
                    if (d === 0) {
                        const s = fullText.slice(i, k + 1);
                        try {
                            plan = JSON.parse(s);
                        }
                        catch { }
                        break;
                    }
                }
            }
        }
        if (!plan) {
            const m = fullText.match(/\{[\s\S]*\}/);
            if (m)
                plan = JSON.parse(m[0]);
        }
    }
    catch { }
    return { job_id: jobId, plan, text: fullText };
}
export async function refinePlan(job_id) {
    const res = await api.post('/plan_refine', { job_id });
    return res.data;
}
export async function streamRefinePlan(job_id, onChunk, onStatus, signal) {
    const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || '/api');
    const baseApi = baseApiRaw.replace(/\/$/, '');
    const url = `${baseApi}/plan_refine?stream=1`;
    onStatus && onStatus('connecting');
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
        body: JSON.stringify({ job_id }),
        signal,
    });
    onStatus && onStatus(resp.ok ? 'streaming' : 'error');
    const reader = resp.body?.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    try {
        if (reader) {
            while (true) {
                const { value, done } = await reader.read();
                if (done)
                    break;
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;
                const show = chunk.replace(/JOB_ID:[^\n]*\n?/, '');
                if (show && onChunk)
                    onChunk(show);
            }
        }
        onStatus && onStatus('done');
    }
    catch (e) {
        if (e && e.name === 'AbortError')
            onStatus && onStatus('interrupted');
        else
            onStatus && onStatus('error');
    }
    let plan_refined = null;
    try {
        const i = fullText.indexOf('{');
        if (i >= 0) {
            let d = 0;
            for (let k = i; k < fullText.length; k++) {
                const c = fullText[k];
                if (c === '{')
                    d++;
                else if (c === '}') {
                    d--;
                    if (d === 0) {
                        const s = fullText.slice(i, k + 1);
                        try {
                            const obj = JSON.parse(s);
                            plan_refined = obj.plan_refined || obj;
                        }
                        catch { }
                        break;
                    }
                }
            }
        }
    }
    catch { }
    return { text: fullText, plan_refined };
}
export async function executeJob(job_id) {
    const res = await api.post('/execute', { job_id });
    return res.data;
}
export async function executeJobAsync(job_id) {
    const res = await api.post('/execute_async', { job_id });
    return res.data;
}
export async function fetchReport(jobId) {
    const res = await api.get(`/report/${jobId}`, { responseType: 'text' });
    return res.data;
}
export async function savePlan(job_id, plan) {
    const res = await api.post('/plan_update', { job_id, plan });
    return res.data;
}
export async function updatePlan(job_id, plan) {
    const res = await api.post('/plan_update', { job_id, plan });
    return res.data;
}
export async function fetchStatus(jobId) {
    const res = await api.get(`/status/${jobId}`);
    return res.data;
}
export async function listJobs() {
    const res = await api.get('/jobs');
    return res.data;
}
export async function listUploads() {
    const res = await api.get('/uploads');
    return res.data;
}
export async function listReports() {
    const res = await api.get('/reports');
    return res.data;
}
export async function regenReport(job_id) {
    const res = await api.post('/report_regen', { job_id });
    return res.data;
}
export async function generateSection(job_id, section_id, opts) {
    const payload = { job_id, section_id };
    if (opts?.human_note)
        payload.human_note = opts.human_note;
    if (opts?.guidelines)
        payload.guidelines = opts.guidelines;
    const res = await api.post('/generate_section', payload);
    return res.data;
}
export async function composeReport(job_id, sections, overrides, save, use_existing = true) {
    const res = await api.post('/compose_report', { job_id, sections, overrides: overrides || {}, save: !!save, use_existing });
    return res.data;
}
export async function fetchSectionsMeta() {
    const res = await api.get('/sections_meta');
    return res.data;
}
export async function composeReportAsync(job_id, sections, overrides, use_existing = true) {
    const res = await api.post('/compose_report_async', { job_id, sections, overrides: overrides || {}, use_existing });
    return res.data;
}
export async function fetchReportStatus(job_id) {
    const res = await api.get(`/report_status/${job_id}`);
    return res.data;
}
export async function fetchReportPreview(job_id) {
    const res = await api.get(`/report_preview/${job_id}`, { responseType: 'text' });
    return res.data;
}
export async function fetchJobPlan(job_id) {
    const res = await api.get(`/job/${job_id}/plan`);
    return res.data;
}
export async function fetchExcelInfo(job_id) {
    const res = await api.get(`/job/${job_id}/excel_info`);
    return res.data;
}
export async function fetchExecLogs(job_id) {
    const res = await api.get(`/job/${job_id}/exec_logs`);
    return res.data;
}
export async function fetchAnalysisCode(job_id) {
    const res = await api.get(`/job/${job_id}/analysis_code`, { responseType: 'text' });
    return res.data;
}
export async function fetchReportSections(job_id) {
    const res = await api.get(`/report_sections/${job_id}`);
    return res.data;
}
export async function saveReport(job_id, content) {
    const res = await api.post('/save_report', { job_id, content });
    return res.data;
}
export async function deleteJob(job_id) {
    const res = await api.delete(`/job/${job_id}`);
    return res.data;
}
