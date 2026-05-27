import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState, useRef } from 'react';
import { Typography, Upload, message, Button, Popconfirm, Empty, Spin, Segmented, theme } from 'antd';
import { DeleteOutlined, FileTextOutlined, ReloadOutlined, AppstoreOutlined, BarsOutlined, PlusOutlined } from '@ant-design/icons';
import { getKnowledgeFiles, uploadKnowledgeFile, deleteKnowledgeFile, getKnowledgeGraph } from '../api/knowledge';
import KnowledgeGraph from '../components/KnowledgeGraph';
import styles from './KnowledgeBase.module.css';
const { Title, Text } = Typography;
const { Dragger } = Upload;
export default function KnowledgeBase() {
    const { token } = theme.useToken();
    const isDark = token.colorBgBase === '#0f172a' || token.colorTextBase === '#f1f5f9';
    const [files, setFiles] = useState([]);
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [viewMode, setViewMode] = useState('graph');
    const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });
    const graphContainerRef = useRef(null);
    const fetchData = async () => {
        setLoading(true);
        try {
            const [filesRes, graphRes] = await Promise.all([
                getKnowledgeFiles(),
                getKnowledgeGraph()
            ]);
            const fileList = Array.isArray(filesRes.files) ? filesRes.files : [];
            setFiles(fileList.sort((a, b) => b.created_ts - a.created_ts));
            setGraphData(graphRes);
        }
        catch (error) {
            console.error(error);
            message.error('加载数据失败');
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        fetchData();
    }, []);
    // Resize observer for graph container
    useEffect(() => {
        if (graphContainerRef.current) {
            const resizeObserver = new ResizeObserver((entries) => {
                for (const entry of entries) {
                    const { width, height } = entry.contentRect;
                    setContainerSize({ width, height });
                }
            });
            resizeObserver.observe(graphContainerRef.current);
            return () => resizeObserver.disconnect();
        }
    }, [viewMode]);
    const handleUpload = async (file) => {
        setUploading(true);
        try {
            await uploadKnowledgeFile(file);
            message.success(`${file.name} 上传成功`);
            fetchData();
        }
        catch (error) {
            console.error(error);
            message.error(`${file.name} 上传失败`);
        }
        finally {
            setUploading(false);
        }
        return false;
    };
    const handleDelete = async (filename) => {
        try {
            await deleteKnowledgeFile(filename);
            message.success('删除成功');
            fetchData();
        }
        catch (error) {
            console.error(error);
            message.error('删除失败');
        }
    };
    const uploadProps = {
        name: 'file',
        multiple: true,
        showUploadList: false,
        beforeUpload: (file) => {
            handleUpload(file);
            return false;
        },
        onDrop(e) {
            console.log('Dropped files', e.dataTransfer.files);
        },
    };
    return (_jsxs("div", { className: styles.container, children: [_jsxs("div", { className: styles.sidebar, children: [_jsxs("div", { className: styles.sidebarHeader, children: [_jsx("h2", { className: styles.title, children: "\u77E5\u8BC6\u5E93" }), _jsx(Button, { type: "text", icon: _jsx(ReloadOutlined, { style: { color: 'var(--kb-accent)' } }), onClick: fetchData, loading: loading })] }), _jsx("div", { className: styles.uploadArea, children: _jsx(Dragger, { ...uploadProps, className: styles.uploadDragger, style: { border: 'none', background: 'transparent' }, children: _jsxs("div", { className: styles.uploadBox, children: [_jsx(PlusOutlined, { style: { fontSize: 24, color: 'var(--kb-accent)', marginBottom: 8 } }), _jsx("div", { style: { color: 'var(--kb-accent)', fontSize: 14 }, children: "\u4E0A\u4F20\u6587\u4EF6" }), _jsx("div", { style: { color: 'var(--kb-text-secondary)', fontSize: 10 }, children: "\u652F\u6301 PDF / Excel / TXT" })] }) }) }), _jsx("div", { className: styles.fileList, children: files.length === 0 ? (_jsx(Empty, { description: _jsx("span", { style: { color: 'var(--kb-text-secondary)' }, children: "\u6682\u65E0\u6587\u4EF6" }), image: Empty.PRESENTED_IMAGE_SIMPLE })) : (files.map(file => (_jsxs("div", { className: styles.fileItem, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10, flex: 1, overflow: 'hidden' }, children: [_jsx(FileTextOutlined, { style: { color: 'var(--kb-accent)' } }), _jsxs("div", { style: { overflow: 'hidden' }, children: [_jsx("div", { className: styles.fileName, title: file.name, children: file.name }), _jsxs("div", { className: styles.fileMeta, children: [(file.size / 1024).toFixed(1), " KB \u2022 ", new Date(file.created_ts * 1000).toLocaleDateString()] })] })] }), _jsx(Popconfirm, { title: "\u786E\u5B9A\u5220\u9664\u6587\u4EF6\uFF1F", onConfirm: (e) => {
                                        e?.stopPropagation();
                                        handleDelete(file.name);
                                    }, okText: "\u662F", cancelText: "\u5426", placement: "right", children: _jsx(DeleteOutlined, { className: styles.deleteBtn, onClick: (e) => e.stopPropagation() }) })] }, file.name)))) })] }), _jsxs("div", { className: styles.mainContent, children: [_jsx("div", { className: styles.toolbar, children: _jsx(Segmented, { options: [
                                { label: '知识图谱', value: 'graph', icon: _jsx(AppstoreOutlined, {}) },
                                { label: '文件列表', value: 'list', icon: _jsx(BarsOutlined, {}) },
                            ], value: viewMode, onChange: (val) => setViewMode(val), style: {
                                background: 'var(--kb-sidebar-bg)',
                                border: '1px solid var(--kb-sidebar-border)',
                                color: 'var(--kb-text)',
                                backdropFilter: 'blur(12px)'
                            } }) }), viewMode === 'graph' ? (_jsx("div", { className: styles.graphContainer, ref: graphContainerRef, children: graphData.nodes.length > 0 ? (_jsx(KnowledgeGraph, { data: graphData, width: containerSize.width, height: containerSize.height, isDark: isDark, onNodeClick: (node) => {
                                if (node.type === 'document') {
                                    message.info(`文件: ${node.name}`);
                                }
                            } })) : (_jsx("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--kb-text-secondary)' }, children: _jsx(Empty, { description: _jsx("span", { style: { color: 'var(--kb-text-secondary)' }, children: "\u6682\u65E0\u56FE\u8C31\u6570\u636E" }), image: Empty.PRESENTED_IMAGE_SIMPLE }) })) })) : (_jsxs("div", { style: { padding: 40, overflow: 'auto' }, children: [_jsx(Title, { level: 3, style: { color: 'var(--kb-text)', marginBottom: 20 }, children: "\u6587\u4EF6\u8BE6\u60C5" }), _jsx("div", { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 20 }, children: files.map(file => (_jsxs("div", { className: styles.card, children: [_jsx(FileTextOutlined, { style: { fontSize: 32, color: 'var(--kb-accent)', marginBottom: 15 } }), _jsx("div", { style: { color: 'var(--kb-text)', fontWeight: 'bold', marginBottom: 5, overflow: 'hidden', textOverflow: 'ellipsis' }, children: file.name }), _jsxs("div", { style: { color: 'var(--kb-text-secondary)', fontSize: 12 }, children: [(file.size / 1024).toFixed(1), " KB"] }), _jsx("div", { style: { color: 'var(--kb-text-secondary)', fontSize: 12 }, children: new Date(file.created_ts * 1000).toLocaleString() })] }, file.name))) })] })), (loading || uploading) && (_jsx("div", { className: styles.loadingOverlay, children: _jsx(Spin, { size: "large", tip: "\u6B63\u5728\u5904\u7406\u6570\u636E..." }) }))] })] }));
}
