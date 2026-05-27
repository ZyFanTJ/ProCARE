import { api } from './client';
export async function fetchAssistantGuide(page_key) {
    try {
        const res = await api.get(`/assistant/guide`, { params: { page: page_key } });
        return res.data;
    }
    catch {
        return { text: '' };
    }
}
export async function assistantChatStream(payload, onDelta, onStatus, signal) {
    const baseApiRaw = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api');
    const baseApi = baseApiRaw.replace(/\/$/, '');
    const url = `${baseApi}/assistant/chat_stream`;
    onStatus && onStatus('connecting');
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
        body: JSON.stringify(payload),
        signal,
    });
    if (!resp.ok) {
        onStatus && onStatus('error');
        return;
    }
    onStatus && onStatus('streaming');
    const reader = resp.body?.getReader();
    const decoder = new TextDecoder('utf-8');
    try {
        if (reader) {
            while (true) {
                const { done, value } = await reader.read();
                if (done)
                    break;
                const chunk = decoder.decode(value);
                const show = chunk.replace(/JOB_ID:[^\n]*\n?/, '');
                if (show && onDelta)
                    onDelta(show);
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
}
export async function assistantChat(payload) {
    const res = await api.post('/assistant/chat', payload);
    return res.data;
}
