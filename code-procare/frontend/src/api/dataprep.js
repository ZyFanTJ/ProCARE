import { api } from './client';
export const listFiles = async () => {
    const res = await api.get('/dataprep/files');
    return res.data;
};
export const previewData = async (filePath) => {
    const res = await api.post('/dataprep/preview', { file_path: filePath });
    return res.data;
};
export const applyOps = async (filePath, operations, saveAs) => {
    const res = await api.post('/dataprep/apply', {
        file_path: filePath,
        operations,
        save_as: saveAs
    });
    return res.data;
};
