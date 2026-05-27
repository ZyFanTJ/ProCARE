import { api } from './client';
export const getKnowledgeFiles = async () => {
    const res = await api.get('/knowledge_base');
    return res.data;
};
export const uploadKnowledgeFile = async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post('/knowledge_base/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
};
export const deleteKnowledgeFile = async (filename) => {
    const res = await api.delete(`/knowledge_base/${filename}`);
    return res.data;
};
export const getKnowledgeGraph = async () => {
    const res = await api.get('/knowledge_graph');
    return res.data;
};
