import axios from 'axios';
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';
export const api = axios.create({ baseURL: API_BASE_URL });
export function getBackendBaseUrl() {
    const normalized = API_BASE_URL.replace(/\/$/, '');
    return normalized.replace(/\/api$/, '');
}
export function resolveStaticUrl(url) {
    if (!url)
        return '';
    if (/^https?:\/\//i.test(url) || url.startsWith('data:'))
        return url;
    if (url.startsWith('/static/')) {
        const backendBase = getBackendBaseUrl();
        return backendBase ? `${backendBase}${url}` : url;
    }
    return url;
}
