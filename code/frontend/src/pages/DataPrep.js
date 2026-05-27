import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Typography, Card, Upload, Table, Button, message, Select, Form, Input, List, Tabs, Tag, Spin } from 'antd';
import { InboxOutlined, FileExcelOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { listFiles, previewData, applyOps } from '../api/dataprep';
import { uploadExcel } from '../api/research'; // Reuse upload
const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;
const { Option } = Select;
export default function DataPrep() {
    const [files, setFiles] = useState([]);
    const [currentFile, setCurrentFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [loading, setLoading] = useState(false);
    const [processing, setProcessing] = useState(false);
    // Operation State
    const [opType, setOpType] = useState('fillna');
    const [opParams, setOpParams] = useState({});
    const refreshFiles = async () => {
        try {
            const res = await listFiles();
            setFiles(res.files);
            // If current file exists, refresh it? Or just keep it.
        }
        catch (e) {
            message.error('加载文件列表失败');
        }
    };
    useEffect(() => {
        refreshFiles();
    }, []);
    const loadFile = async (file) => {
        setLoading(true);
        setCurrentFile(file);
        try {
            const res = await previewData(file.path);
            setPreview(res);
            // Reset params when file changes
            setOpParams({});
        }
        catch (e) {
            message.error('加载预览失败');
        }
        finally {
            setLoading(false);
        }
    };
    const handleUpload = async ({ file, onSuccess, onError }) => {
        try {
            // Reuse the research upload API which saves to the same uploads dir
            await uploadExcel(file);
            message.success('上传成功');
            refreshFiles();
            onSuccess && onSuccess("ok");
        }
        catch (e) {
            message.error('上传失败');
            onError && onError(e);
        }
    };
    const handleApply = async () => {
        if (!currentFile)
            return;
        // Validate params
        if (opType === 'fillna' && opParams.value === undefined) {
            message.warning('请输入填充值');
            return;
        }
        if (opType === 'rename' && (!opParams.old || !opParams.new)) {
            message.warning('请输入新旧列名');
            return;
        }
        setProcessing(true);
        try {
            let actualParams = { ...opParams };
            if (opType === 'rename') {
                actualParams = { columns: { [opParams.old]: opParams.new } };
            }
            const op = {
                type: opType,
                params: actualParams
            };
            const res = await applyOps(currentFile.path, [op]);
            message.success('操作已应用，生成新文件');
            // Refresh list and switch to new file
            await refreshFiles();
            // Find the new file (by path or name)
            // Since we don't know the exact object ref, we find by path
            const newFile = (await listFiles()).files.find(f => f.path === res.path);
            if (newFile) {
                loadFile(newFile);
            }
        }
        catch (e) {
            message.error(e.response?.data?.detail || '操作失败');
        }
        finally {
            setProcessing(false);
        }
    };
    const renderOpForm = () => {
        if (!preview)
            return _jsx(EmptyState, { text: "\u8BF7\u5148\u9009\u62E9\u6587\u4EF6" });
        const colOptions = preview.info.columns.map(c => _jsx(Option, { value: c.name, children: c.name }, c.name));
        return (_jsxs(Form, { layout: "vertical", children: [_jsx(Form.Item, { label: "\u9009\u62E9\u64CD\u4F5C", children: _jsxs(Select, { value: opType, onChange: v => { setOpType(v); setOpParams({}); }, children: [_jsx(Option, { value: "fillna", children: "\u586B\u5145\u7F3A\u5931\u503C (Fill NA)" }), _jsx(Option, { value: "dropna", children: "\u5220\u9664\u7F3A\u5931\u884C (Drop NA)" }), _jsx(Option, { value: "rename", children: "\u91CD\u547D\u540D\u5217 (Rename)" }), _jsx(Option, { value: "astype", children: "\u7C7B\u578B\u8F6C\u6362 (Convert Type)" }), _jsx(Option, { value: "drop_col", children: "\u5220\u9664\u5217 (Drop Column)" })] }) }), opType === 'fillna' && (_jsxs(_Fragment, { children: [_jsx(Form.Item, { label: "\u76EE\u6807\u5217 (\u53EF\u9009\uFF0C\u7559\u7A7A\u5219\u586B\u5145\u6240\u6709)", children: _jsx(Select, { allowClear: true, placeholder: "\u6240\u6709\u5217", onChange: v => setOpParams({ ...opParams, column: v }), value: opParams.column, children: colOptions }) }), _jsx(Form.Item, { label: "\u586B\u5145\u503C", children: _jsx(Input, { placeholder: "\u4F8B\u5982: 0, Unknown", onChange: e => setOpParams({ ...opParams, value: e.target.value }), value: opParams.value }) })] })), opType === 'dropna' && (_jsx(Form.Item, { label: "\u4F9D\u636E\u5217 (\u53EF\u9009\uFF0C\u7559\u7A7A\u5219\u68C0\u67E5\u6240\u6709)", children: _jsx(Select, { mode: "multiple", allowClear: true, placeholder: "\u6240\u6709\u5217", onChange: v => setOpParams({ ...opParams, subset: v }), value: opParams.subset, children: colOptions }) })), opType === 'rename' && (_jsxs(_Fragment, { children: [_jsx(Form.Item, { label: "\u539F\u5217\u540D", children: _jsx(Select, { onChange: v => setOpParams({ ...opParams, old: v }), value: opParams.old, children: colOptions }) }), _jsx(Form.Item, { label: "\u65B0\u5217\u540D", children: _jsx(Input, { onChange: e => setOpParams({ ...opParams, new: e.target.value }), value: opParams.new }) })] })), opType === 'astype' && (_jsxs(_Fragment, { children: [_jsx(Form.Item, { label: "\u76EE\u6807\u5217", children: _jsx(Select, { onChange: v => setOpParams({ ...opParams, column: v }), value: opParams.column, children: colOptions }) }), _jsx(Form.Item, { label: "\u76EE\u6807\u7C7B\u578B", children: _jsxs(Select, { onChange: v => setOpParams({ ...opParams, dtype: v }), value: opParams.dtype, children: [_jsx(Option, { value: "str", children: "\u6587\u672C (String)" }), _jsx(Option, { value: "int", children: "\u6574\u6570 (Integer)" }), _jsx(Option, { value: "float", children: "\u6D6E\u70B9\u6570 (Float)" }), _jsx(Option, { value: "bool", children: "\u5E03\u5C14\u503C (Boolean)" })] }) })] })), opType === 'drop_col' && (_jsx(Form.Item, { label: "\u9009\u62E9\u5217", children: _jsx(Select, { mode: "multiple", onChange: v => setOpParams({ ...opParams, columns: v }), value: opParams.columns, children: colOptions }) })), _jsx(Button, { type: "primary", block: true, icon: _jsx(ThunderboltOutlined, {}), onClick: handleApply, loading: processing, children: "\u7ACB\u5373\u5E94\u7528\u5E76\u53E6\u5B58" })] }));
    };
    const columnsInfoCols = [
        { title: '列名', dataIndex: 'name', key: 'name', render: (t) => _jsx("b", { children: t }) },
        { title: '类型', dataIndex: 'type', key: 'type', render: (t) => _jsx(Tag, { children: t }) },
        { title: '缺失值', dataIndex: 'nulls', key: 'nulls', render: (n) => n > 0 ? _jsx(Text, { type: "danger", children: n }) : _jsx(Text, { type: "success", children: "0" }) },
        { title: '唯一值', dataIndex: 'unique', key: 'unique' },
    ];
    // Dynamic preview columns
    const previewCols = preview ? preview.info.columns.map(c => ({
        title: c.name,
        dataIndex: c.name,
        key: c.name,
        width: 150,
        render: (text) => text === null || text === undefined ? _jsx(Text, { type: "secondary", italic: true, children: "null" }) : String(text)
    })) : [];
    return (_jsxs("div", { style: { height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }, children: [_jsx("div", { style: { padding: '16px 24px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-color)' }, children: _jsx(Title, { level: 4, style: { margin: 0 }, children: "\uD83E\uDDF9 \u6570\u636E\u6E05\u6D17\u5DE5\u574A" }) }), _jsxs("div", { style: { flex: 1, display: 'flex', overflow: 'hidden' }, children: [_jsxs("div", { style: { width: 280, borderRight: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', background: 'var(--bg-subtle)' }, children: [_jsx("div", { style: { padding: 16 }, children: _jsxs(Dragger, { showUploadList: false, customRequest: handleUpload, style: { padding: 16, background: 'var(--bg-color)' }, children: [_jsx("p", { className: "ant-upload-drag-icon", style: { marginBottom: 8 }, children: _jsx(InboxOutlined, { style: { fontSize: 24 } }) }), _jsx("p", { className: "ant-upload-text", style: { fontSize: 12 }, children: "\u4E0A\u4F20\u6587\u4EF6" })] }) }), _jsx("div", { style: { flex: 1, overflow: 'auto', padding: '0 16px 16px' }, children: _jsx(List, { size: "small", dataSource: files, renderItem: item => (_jsx(List.Item, { onClick: () => loadFile(item), className: currentFile?.path === item.path ? 'file-item-active' : 'file-item', style: {
                                            cursor: 'pointer',
                                            borderRadius: 6,
                                            padding: '8px 12px',
                                            marginBottom: 4,
                                            background: currentFile?.path === item.path ? 'var(--primary-color-bg)' : 'transparent',
                                            border: currentFile?.path === item.path ? '1px solid var(--primary-color)' : '1px solid transparent'
                                        }, children: _jsxs("div", { style: { width: '100%' }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 8 }, children: [_jsx(FileExcelOutlined, { style: { color: '#1d7324' } }), _jsx(Text, { ellipsis: true, style: { flex: 1, fontWeight: 500 }, children: item.name })] }), _jsxs("div", { style: { fontSize: 10, color: 'var(--text-secondary)', marginTop: 4, display: 'flex', justifyContent: 'space-between' }, children: [_jsxs("span", { children: [(item.size / 1024).toFixed(1), " KB"] }), _jsx("span", { children: new Date(item.mtime * 1000).toLocaleDateString() })] })] }) })) }) })] }), _jsx("div", { style: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }, children: loading ? _jsx("div", { style: { display: 'flex', justifyContent: 'center', marginTop: 100 }, children: _jsx(Spin, { size: "large" }) }) :
                            preview ? (_jsx(Tabs, { defaultActiveKey: "sample", items: [
                                    {
                                        key: 'sample',
                                        label: '数据预览 (前20行)',
                                        children: (_jsx(Table, { dataSource: preview.preview, columns: previewCols, scroll: { x: 'max-content', y: 'calc(100vh - 250px)' }, pagination: false, size: "small", bordered: true, rowKey: (r, i) => i }))
                                    },
                                    {
                                        key: 'info',
                                        label: '字段信息',
                                        children: (_jsx(Table, { dataSource: preview.info.columns, columns: columnsInfoCols, pagination: false, rowKey: "name" }))
                                    }
                                ] })) : (_jsx(EmptyState, { text: "\u8BF7\u4ECE\u5DE6\u4FA7\u9009\u62E9\u4E00\u4E2A\u6587\u4EF6\u67E5\u770B" })) }), _jsxs("div", { style: { width: 320, borderLeft: '1px solid var(--border-color)', padding: 16, background: 'var(--bg-subtle)', overflow: 'auto' }, children: [_jsx(Title, { level: 5, children: "\uD83D\uDEE0\uFE0F \u64CD\u4F5C\u9762\u677F" }), _jsx(Card, { size: "small", style: { marginTop: 16 }, children: renderOpForm() }), preview && (_jsxs("div", { style: { marginTop: 24 }, children: [_jsx(Title, { level: 5, style: { fontSize: 14 }, children: "\uD83D\uDCCA \u7EDF\u8BA1\u6982\u89C8" }), _jsxs("div", { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }, children: [_jsx(StatCard, { label: "\u603B\u884C\u6570", value: preview.info.rows }), _jsx(StatCard, { label: "\u603B\u5217\u6570", value: preview.info.cols })] })] }))] })] })] }));
}
function EmptyState({ text }) {
    return (_jsxs("div", { style: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }, children: [_jsx(InboxOutlined, { style: { fontSize: 48, marginBottom: 16, opacity: 0.5 } }), _jsx("span", { children: text })] }));
}
function StatCard({ label, value }) {
    return (_jsxs("div", { style: { background: 'var(--bg-color)', padding: 12, borderRadius: 6, border: '1px solid var(--border-color)', textAlign: 'center' }, children: [_jsx("div", { style: { fontSize: 12, color: 'var(--text-secondary)' }, children: label }), _jsx("div", { style: { fontSize: 18, fontWeight: 600, marginTop: 4 }, children: value })] }));
}
