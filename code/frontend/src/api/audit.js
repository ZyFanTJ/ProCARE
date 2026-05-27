import { api } from './client';
export async function fetchAuditLogs(limit = 100, offset = 0) {
    const res = await api.get('/audit/logs', { params: { limit, offset } });
    return res.data;
}
export async function fetchAuditStats() {
    const res = await api.get('/audit/stats');
    return res.data;
}
