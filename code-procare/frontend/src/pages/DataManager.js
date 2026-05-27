import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Card, Table, Typography, Space, Button, Modal, Descriptions, Tag, Tabs, Empty, Drawer, Popconfirm, message, Badge, Upload, Form, Input } from 'antd';
import { DeleteOutlined, EyeOutlined, FileExcelOutlined, ReloadOutlined, DatabaseOutlined, ProjectOutlined, UploadOutlined, InboxOutlined } from '@ant-design/icons';
import { fetchProfiles, fetchProfileDetail, deleteProfile, uploadExcel, analyzeProfile, previewSheetData, listUploads } from '../api/research';
import JsonTree from '../components/JsonTree';
const { Title, Text, Paragraph } = Typography;
function SheetPreview({ md5, sheet }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    useEffect(() => {
        loadData();
    }, [md5, sheet]);
    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await previewSheetData(md5, sheet);
            setData(res);
        }
        catch (e) {
            setError(e?.response?.data?.detail || '加载预览数据失败');
        }
        finally {
            setLoading(false);
        }
    };
    if (loading)
        return _jsx("div", { style: { padding: 20, textAlign: 'center' }, children: "\u52A0\u8F7D\u9884\u89C8\u6570\u636E\u4E2D..." });
    if (error)
        return _jsx("div", { style: { color: 'red', padding: 20 }, children: error });
    if (!data)
        return _jsx(Empty, { description: "\u6682\u65E0\u9884\u89C8\u6570\u636E" });
    const columns = data.columns.map(c => ({
        title: c,
        dataIndex: c,
        key: c,
        render: (text) => _jsx(Text, { ellipsis: { tooltip: true }, style: { maxWidth: 200 }, children: text !== null ? String(text) : _jsx(Text, { type: "secondary", italic: true, children: "null" }) })
    }));
    return (_jsx(Table, { size: "small", dataSource: data.data, columns: columns, scroll: { x: 'max-content' }, pagination: false, rowKey: (r, i) => i }));
}
export default function DataManager() {
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [detailVisible, setDetailVisible] = useState(false);
    const [currentProfile, setCurrentProfile] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    // Upload modal states
    const [uploadVisible, setUploadVisible] = useState(false);
    const [uploadLoading, setUploadLoading] = useState(false);
    const [form] = Form.useForm();
    // Files tab states
    const [files, setFiles] = useState([]);
    const [filesLoading, setFilesLoading] = useState(false);
    const loadProfiles = async () => {
        setLoading(true);
        try {
            const data = await fetchProfiles();
            setProfiles(data);
        }
        catch (e) {
            message.error('加载画像列表失败');
        }
        finally {
            setLoading(false);
        }
    };
    const loadFiles = async () => {
        setFilesLoading(true);
        try {
            const res = await listUploads();
            setFiles(res.files || []);
        }
        catch (e) {
            message.error('加载文件列表失败');
        }
        finally {
            setFilesLoading(false);
        }
    };
    useEffect(() => {
        loadProfiles();
        loadFiles();
    }, []);
    const prefixUrl = (u) => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        const prefix = baseApi.replace(/\/api$/, '');
        return `${prefix}${u}`;
    };
    const handleUploadSubmit = async () => {
        try {
            const values = await form.validateFields();
            const file = values.file?.[0]?.originFileObj;
            if (!file) {
                message.error('请选择文件');
                return;
            }
            setUploadLoading(true);
            try {
                const res = await uploadExcel(file, values.description);
                if (res.profile_reused) {
                    message.success(`检测到已有画像 (MD5: ${res.md5?.slice(0, 8)})，已复用`);
                }
                else {
                    message.success('上传并生成画像成功');
                }
                setUploadVisible(false);
                form.resetFields();
                loadProfiles();
                loadFiles();
            }
            catch (e) {
                message.error(e?.response?.data?.detail || '上传失败');
            }
            finally {
                setUploadLoading(false);
            }
        }
        catch (e) {
            // validation failed
        }
    };
    const normFile = (e) => {
        if (Array.isArray(e)) {
            return e;
        }
        return e?.fileList;
    };
    const handleView = async (md5) => {
        setDetailLoading(true);
        setDetailVisible(true);
        try {
            const data = await fetchProfileDetail(md5);
            setCurrentProfile(data);
        }
        catch (e) {
            message.error('加载详情失败');
            setDetailVisible(false);
        }
        finally {
            setDetailLoading(false);
        }
    };
    const handleDelete = async (md5) => {
        try {
            await deleteProfile(md5);
            message.success('删除成功');
            loadProfiles();
        }
        catch (e) {
            message.error('删除失败');
        }
    };
    const handleAnalyze = async () => {
        if (!currentProfile?.md5)
            return;
        setAnalyzing(true);
        // Keep loading message with duration 0 so it stays until updated or destroyed
        message.loading({ content: 'AI 正在深度分析数据语义...', key: 'analyzing', duration: 0 });
        try {
            await analyzeProfile(currentProfile.md5, (msg) => {
                if (msg.status === 'processing') {
                    // Update the loading message content
                    message.loading({ content: msg.message || 'AI 分析中...', key: 'analyzing', duration: 0 });
                }
                else if (msg.status === 'completed') {
                    // Success message replaces the loading one
                    message.success({ content: 'AI 画像分析完成', key: 'analyzing' });
                    if (msg.profile) {
                        setCurrentProfile(msg.profile);
                    }
                    loadProfiles();
                }
                else if (msg.status === 'error') {
                    message.error({ content: msg.message || '分析失败', key: 'analyzing' });
                }
            });
        }
        catch (e) {
            console.error(e);
            message.error({ content: e.message || '分析失败', key: 'analyzing' });
        }
        finally {
            setAnalyzing(false);
        }
    };
    const filesColumns = [
        { title: '文件名', dataIndex: 'name', key: 'name' },
        { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
        { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v) => v ? new Date(v * 1000).toLocaleString() : '-' },
        { title: '操作', key: 'action', render: (_, r) => r.url ? _jsx("a", { href: prefixUrl(r.url), target: "_blank", children: "\u4E0B\u8F7D/\u9884\u89C8" }) : '-' },
    ];
    const columns = [
        {
            title: '文件名',
            dataIndex: 'path',
            key: 'path',
            render: (path) => {
                const name = path.split(/[/\\]/).pop();
                return (_jsxs(Space, { children: [_jsx(FileExcelOutlined, { style: { color: '#1890ff' } }), _jsx(Text, { strong: true, children: name })] }));
            }
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
            ellipsis: true,
            render: (text) => text || _jsx(Text, { type: "secondary", children: "\u65E0\u63CF\u8FF0" })
        },
        {
            title: '表单数量',
            dataIndex: 'sheet_count',
            key: 'sheet_count',
            render: (count) => _jsxs(Tag, { color: "blue", children: [count, " \u4E2A\u8868"] })
        },
        {
            title: '画像覆盖',
            dataIndex: 'profile_count',
            key: 'profile_count',
            render: (count, record) => {
                const percent = record.sheet_count > 0 ? Math.round(count / record.sheet_count * 100) : 0;
                return _jsx(Badge, { count: `${percent}%`, style: { backgroundColor: percent === 100 ? '#52c41a' : '#faad14' } });
            }
        },
        {
            title: '更新时间',
            dataIndex: 'updated_at',
            key: 'updated_at',
            render: (t) => new Date(t).toLocaleString()
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (_jsxs(Space, { size: "middle", children: [_jsx(Button, { type: "link", icon: _jsx(EyeOutlined, {}), onClick: () => handleView(record.md5), children: "\u67E5\u770B\u8BE6\u60C5" }), _jsx(Popconfirm, { title: "\u786E\u5B9A\u5220\u9664\u6B64\u7F13\u5B58\u753B\u50CF\u5417\uFF1F", onConfirm: () => handleDelete(record.md5), children: _jsx(Button, { type: "link", danger: true, icon: _jsx(DeleteOutlined, {}), children: "\u5220\u9664" }) })] }))
        }
    ];
    // 渲染Sheet详情
    const renderSheetProfile = (sheetName, profile) => {
        if (!profile)
            return _jsx(Empty, { description: "\u6682\u65E0\u8BE5Sheet\u7684\u8BE6\u7EC6\u753B\u50CF" });
        const { high_structural, low_structural, high_knowledge, low_knowledge, ambiguity_flags } = profile.heterogeneous_profile || {};
        const legacy = !profile.heterogeneous_profile;
        if (legacy) {
            // Fallback for legacy profile structure
            return _jsx(JsonTree, { data: profile, defaultCollapsed: false });
        }
        const aiReady = !!(high_knowledge && Object.keys(high_knowledge).length > 0);
        const dtypes = low_structural?.dtypes || {};
        const missing = low_structural?.missing_rate || {};
        const unique = low_structural?.unique_rate || {};
        const fieldColumns = [
            { title: '字段名', dataIndex: 'name', key: 'name', width: 150, fixed: 'left' },
            { title: '类型', dataIndex: 'type', key: 'type', render: (t) => _jsx(Tag, { color: t === 'object' ? 'orange' : t === 'int64' ? 'blue' : 'cyan', children: t }) },
            { title: '缺失率', dataIndex: 'missing', key: 'missing', render: (v) => _jsxs(Text, { type: v > 0.5 ? 'danger' : v > 0 ? 'warning' : 'secondary', children: [(v * 100).toFixed(1), "%"] }) },
            { title: '唯一率', dataIndex: 'unique', key: 'unique', render: (v) => `${(v * 100).toFixed(1)}%` },
            { title: '语义映射 (LLM)', dataIndex: 'mapping', key: 'mapping', render: (v) => v ? _jsx(Tag, { color: "purple", children: v }) : _jsx(Text, { type: "secondary", children: "-" }) },
            { title: '校验', dataIndex: 'validation', key: 'validation', render: (v) => !aiReady ? _jsx(Text, { type: "secondary", children: "-" }) : (v && v.includes('Ambiguous') ? _jsx(Badge, { status: "warning", text: v }) : _jsx(Text, { type: "success", children: "OK" })) }
        ];
        const fieldData = Object.keys(dtypes).map(k => ({
            key: k,
            name: k,
            type: dtypes[k],
            missing: missing[k],
            unique: unique[k],
            mapping: low_knowledge?.ontology_mapping?.[k],
            validation: low_knowledge?.validation_status?.[k]
        }));
        return (_jsxs("div", { style: { height: 'calc(100vh - 200px)', overflow: 'auto' }, children: [_jsxs("div", { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }, children: [_jsx(Card, { size: "small", title: _jsxs(Space, { children: [_jsx(ProjectOutlined, {}), _jsx("span", { children: "\u7814\u7A76\u8BBE\u8BA1\u89D2\u8272" })] }), style: { background: '#f9f9f9' }, children: !aiReady ? _jsx(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "\u5F85 AI \u5206\u6790 (\u8BF7\u70B9\u51FB\u53F3\u4E0A\u89D2\u6267\u884C)" }) : (_jsxs(_Fragment, { children: [_jsx(Paragraph, { children: high_knowledge?.study_design_schema || '未识别' }), _jsxs(Space, { direction: "vertical", style: { width: '100%' }, children: [_jsxs("div", { children: [_jsx(Text, { strong: true, children: "\u66B4\u9732\u56E0\u7D20 (Exposure):" }), " ", high_knowledge?.variable_roles?.exposure?.join(', ') || '-'] }), _jsxs("div", { children: [_jsx(Text, { strong: true, children: "\u7ED3\u5C40\u53D8\u91CF (Outcome):" }), " ", high_knowledge?.variable_roles?.outcome?.join(', ') || '-'] }), _jsxs("div", { children: [_jsx(Text, { strong: true, children: "\u534F\u53D8\u91CF (Covariate):" }), " ", high_knowledge?.variable_roles?.covariate?.join(', ') || '-'] })] })] })) }), _jsx(Card, { size: "small", title: _jsxs(Space, { children: [_jsx(DatabaseOutlined, {}), _jsx("span", { children: "\u6570\u636E\u8D28\u91CF\u6982\u89C8" })] }), style: { background: '#f9f9f9' }, children: _jsxs(Descriptions, { column: 1, size: "small", children: [_jsx(Descriptions.Item, { label: "\u884C\u6570", children: high_structural?.rows }), _jsx(Descriptions.Item, { label: "\u5217\u6570", children: high_structural?.columns }), _jsx(Descriptions.Item, { label: "\u5019\u9009\u4E3B\u952E", children: high_structural?.candidate_keys?.join(', ') || '无' }), _jsx(Descriptions.Item, { label: "\u7591\u4F3C\u95EE\u9898\u5B57\u6BB5", children: ambiguity_flags?.length ? _jsx(Text, { type: "danger", children: ambiguity_flags.join(', ') }) : _jsx(Text, { type: "success", children: "\u65E0\u660E\u663E\u5F02\u5E38" }) })] }) })] }), _jsx(Table, { dataSource: fieldData, columns: fieldColumns, pagination: false, size: "small", scroll: { y: 400 }, bordered: true })] }));
    };
    return (_jsxs("div", { style: { padding: 24 }, children: [_jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 16 }, children: [_jsxs("div", { children: [_jsx(Title, { level: 3, children: "\u6570\u636E\u8D44\u4EA7\u7BA1\u7406" }), _jsx(Paragraph, { type: "secondary", children: "\u7BA1\u7406\u6240\u6709\u5DF2\u5206\u6790\u7684 Excel \u6570\u636E\u753B\u50CF\uFF0C\u5305\u62EC\u7ED3\u6784\u7EDF\u8BA1\u4E0E AI \u751F\u6210\u7684\u8BED\u4E49\u77E5\u8BC6\u3002" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "primary", icon: _jsx(UploadOutlined, {}), onClick: () => setUploadVisible(true), children: "\u4E0A\u4F20\u65B0\u6570\u636E" }), _jsx(Button, { icon: _jsx(ReloadOutlined, {}), onClick: loadProfiles, children: "\u5237\u65B0\u5217\u8868" })] })] }), _jsx(Card, { children: _jsx(Tabs, { defaultActiveKey: "profiles", items: [
                        {
                            key: 'profiles',
                            label: '数据画像 (Profiles)',
                            children: (_jsx(Table, { loading: loading, dataSource: profiles, columns: columns, rowKey: "md5", pagination: { pageSize: 10 } }))
                        },
                        {
                            key: 'files',
                            label: '原始文件',
                            children: (_jsx(Table, { rowKey: "name", columns: filesColumns, dataSource: files, loading: filesLoading, pagination: { pageSize: 10 } }))
                        }
                    ] }) }), _jsx(Drawer, { title: "\u6570\u636E\u753B\u50CF\u8BE6\u60C5", width: "80%", open: detailVisible, onClose: () => setDetailVisible(false), destroyOnClose: true, extra: _jsx(Button, { type: "primary", icon: _jsx(DatabaseOutlined, {}), loading: analyzing, onClick: handleAnalyze, children: "\u6267\u884C AI \u6DF1\u5EA6\u753B\u50CF" }), children: detailLoading ? _jsx("div", { style: { textAlign: 'center', padding: 50 }, children: "\u52A0\u8F7D\u4E2D..." }) : (currentProfile && (_jsxs("div", { children: [_jsxs(Descriptions, { title: "\u57FA\u7840\u4FE1\u606F", bordered: true, size: "small", column: 2, children: [_jsx(Descriptions.Item, { label: "\u6587\u4EF6\u540D", children: currentProfile.path?.split(/[/\\]/).pop() }), _jsx(Descriptions.Item, { label: "MD5", children: currentProfile.md5 }), _jsx(Descriptions.Item, { label: "\u5B8C\u6574\u8DEF\u5F84", span: 2, children: currentProfile.path }), _jsx(Descriptions.Item, { label: "\u63CF\u8FF0", span: 2, children: currentProfile.description || '-' })] }), _jsxs("div", { style: { marginTop: 24, height: 'calc(100vh - 250px)', display: 'flex', flexDirection: 'column' }, children: [_jsx(Title, { level: 5, style: { marginBottom: 16 }, children: "\u5DE5\u4F5C\u8868\u753B\u50CF" }), _jsx(Tabs, { tabPosition: "left", style: { height: '100%' }, items: (currentProfile.sheets || []).map((sheet) => ({
                                        key: sheet,
                                        label: (_jsxs("span", { children: [sheet, currentProfile.profile?.[sheet] && _jsx(Badge, { status: "success", style: { marginLeft: 8 } })] })),
                                        children: (_jsx("div", { style: { height: '100%', overflowY: 'auto', paddingRight: 16 }, children: _jsx(Tabs, { type: "card", items: [
                                                    {
                                                        key: 'profile',
                                                        label: '画像信息',
                                                        children: renderSheetProfile(sheet, currentProfile.profile?.[sheet])
                                                    },
                                                    {
                                                        key: 'preview',
                                                        label: '数据预览',
                                                        children: _jsx(SheetPreview, { md5: currentProfile.md5, sheet: sheet })
                                                    }
                                                ] }) }))
                                    })) })] })] }))) }), _jsx(Modal, { title: "\u4E0A\u4F20\u65B0\u6570\u636E", open: uploadVisible, onCancel: () => setUploadVisible(false), onOk: form.submit, confirmLoading: uploadLoading, okText: "\u4E0A\u4F20\u5E76\u5206\u6790", cancelText: "\u53D6\u6D88", children: _jsxs(Form, { form: form, layout: "vertical", onFinish: handleUploadSubmit, children: [_jsx(Form.Item, { label: "\u6587\u4EF6\u63CF\u8FF0", name: "description", children: _jsx(Input.TextArea, { rows: 3, placeholder: "\u7B80\u8981\u63CF\u8FF0\u6570\u636E\u6765\u6E90\u3001\u7528\u9014\u7B49\u4FE1\u606F" }) }), _jsx(Form.Item, { label: "Excel \u6587\u4EF6", name: "file", valuePropName: "fileList", getValueFromEvent: normFile, rules: [{ required: true, message: '请选择文件' }], children: _jsxs(Upload.Dragger, { accept: ".xlsx,.xls", maxCount: 1, beforeUpload: () => false, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u70B9\u51FB\u6216\u62D6\u62FD\u6587\u4EF6\u5230\u6B64\u533A\u57DF\u4E0A\u4F20" })] }) })] }) })] }));
}
