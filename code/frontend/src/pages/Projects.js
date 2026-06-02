import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Table, Tag, Button, message, Space, Image, Popconfirm, Input, Tooltip } from 'antd';
import { listJobs, deleteJob } from '../api/research';
import { resolveStaticUrl } from '../api/client';
import { Link, useSearchParams } from 'react-router-dom';
import { SearchOutlined, ExperimentOutlined, ReloadOutlined, DeleteOutlined, FileTextOutlined, AppstoreOutlined, PlayCircleOutlined } from '@ant-design/icons';
import './Projects.css';
export default function Projects() {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [params, setParams] = useSearchParams();
    // Generate a unique timestamp for this session to bypass browser cache issues (CORS on 304)
    const [cacheBuster] = useState(Date.now());
    useEffect(() => {
        setLoading(true);
        listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false));
    }, []);
    const q = (params.get('q') || '').trim().toLowerCase();
    const filtered = q ? data.filter((it) => (it.job_id || '').toLowerCase().includes(q) || (it.topic || '').toLowerCase().includes(q)) : data;
    const onSearch = (value) => {
        if (value) {
            setParams({ q: value });
        }
        else {
            setParams({});
        }
    };
    const columns = [
        {
            title: '项目名称 / 研究主题',
            dataIndex: 'job_id',
            key: 'job_id',
            width: 350,
            render: (v, r) => (_jsxs("div", { style: { display: 'flex', flexDirection: 'column' }, children: [_jsxs(Link, { to: `/project/${v}`, className: "project-name", children: [_jsx(ExperimentOutlined, { style: { marginRight: 8 } }), v] }), _jsx("div", { className: "project-topic", title: r.topic, children: r.topic || '暂未设置研究主题' })] }))
        },
        {
            title: '创建时间',
            dataIndex: 'created_ts',
            key: 'created_ts',
            width: 180,
            render: (v) => (_jsx("span", { style: { color: 'var(--text-secondary)', fontSize: 13 }, children: v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-' })),
            sorter: (a, b) => (a.created_ts || 0) - (b.created_ts || 0),
            defaultSortOrder: 'descend',
        },
        {
            title: '可视化预览',
            dataIndex: 'plots',
            key: 'preview',
            render: (plots, r) => {
                const show = Array.isArray(plots) ? plots.slice(0, 4) : [];
                if (!show.length)
                    return _jsx("span", { style: { color: 'var(--text-secondary)', fontSize: 12 }, children: "\u6682\u65E0\u56FE\u8868" });
                return (_jsx(Image.PreviewGroup, { children: _jsxs("div", { className: "preview-grid", children: [show.map((fname) => {
                                // Add timestamp to bypass 304 cache issues (which might cause CORS errors in some environments)
                                // We combine job creation time with a session-level cache buster
                                const timestamp = r.created_ts || 0;
                                const src = `${resolveStaticUrl(`/static/jobs/${r.job_id}/plots/${fname}`)}?t=${timestamp}&cb=${cacheBuster}`;
                                return (_jsx(Image, { src: src, alt: fname, width: 48, height: 36, className: "preview-img", style: { objectFit: 'cover' }, fallback: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", crossOrigin: "anonymous" }, fname));
                            }), plots.length > 4 && (_jsxs("div", { style: {
                                    width: 48, height: 36, background: 'rgba(0,0,0,0.05)', borderRadius: 6,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#666'
                                }, children: ["+", plots.length - 4] }))] }) }));
            },
        },
        {
            title: '运行状态',
            dataIndex: 'success',
            key: 'status',
            width: 150,
            render: (v, r) => (_jsxs(Space, { direction: "vertical", size: 2, children: [v === true ?
                        _jsx(Tag, { className: "status-tag status-tag-success", children: "\u8FD0\u884C\u6210\u529F" }) :
                        v === false ? _jsx(Tag, { className: "status-tag status-tag-error", children: "\u8FD0\u884C\u5931\u8D25" }) :
                            _jsx(Tag, { className: "status-tag status-tag-processing", children: "\u8FDB\u884C\u4E2D / \u672A\u77E5" }), r.report_exists && _jsx(Tag, { className: "status-tag status-tag-default", children: "\u5DF2\u751F\u6210\u62A5\u544A" })] })),
        },
        {
            title: '操作',
            key: 'action',
            width: 280,
            render: (_, r) => (_jsxs(Space, { wrap: true, size: 8, children: [_jsx(Tooltip, { title: "\u8FDB\u5165\u9879\u76EE\u8BE6\u60C5\u4E0E\u7BA1\u7406", children: _jsx(Link, { to: `/project/${r.job_id}`, children: _jsx(Button, { size: "small", type: "primary", className: "action-btn action-btn-primary", icon: _jsx(AppstoreOutlined, {}), children: "\u7BA1\u7406" }) }) }), _jsx(Tooltip, { title: "\u56DE\u5230\u5411\u5BFC\u7EE7\u7EED\u6267\u884C", children: _jsx(Link, { to: `/wizard?job_id=${r.job_id}`, children: _jsx(Button, { size: "small", className: "action-btn", icon: _jsx(PlayCircleOutlined, {}), children: "\u7EE7\u7EED" }) }) }), _jsx(Tooltip, { title: "\u67E5\u770B\u7814\u7A76\u62A5\u544A", children: _jsx(Link, { to: `/report/${r.job_id}`, children: _jsx(Button, { size: "small", className: "action-btn", icon: _jsx(FileTextOutlined, {}), disabled: !r.report_exists, children: "\u62A5\u544A" }) }) }), _jsx(Tooltip, { title: "\u6309\u7AE0\u8282\u91CD\u65B0\u751F\u6210\u62A5\u544A", children: _jsx(Link, { to: `/compose/${r.job_id}`, children: _jsx(Button, { size: "small", className: "action-btn", icon: _jsx(ReloadOutlined, {}), children: "\u91CD\u7EC4" }) }) }), _jsx(Popconfirm, { title: "\u786E\u8BA4\u5220\u9664\u8BE5\u7814\u7A76\u9879\u76EE\uFF1F", description: "\u5220\u9664\u540E\u4E0D\u53EF\u6062\u590D\uFF0C\u5305\u542B\u6240\u6709\u62A5\u544A\u4E0E\u56FE\u8868\u6587\u4EF6\u3002", okText: "\u786E\u8BA4\u5220\u9664", cancelText: "\u53D6\u6D88", okButtonProps: { danger: true }, onConfirm: async () => {
                            try {
                                const res = await deleteJob(r.job_id);
                                if (res.ok) {
                                    message.success('项目已删除');
                                    setLoading(true);
                                    listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false));
                                }
                            }
                            catch (e) {
                                const msg = e?.response?.data?.detail || '删除失败';
                                message.error(msg);
                            }
                        }, children: _jsx(Button, { size: "small", danger: true, type: "text", className: "action-btn", icon: _jsx(DeleteOutlined, {}) }) })] })),
        },
    ];
    return (_jsx("div", { className: "projects-container", children: _jsxs("div", { className: "projects-card", children: [_jsx("div", { style: { padding: '24px 24px 0 24px' }, children: _jsxs("div", { className: "projects-header", children: [_jsxs("div", { className: "projects-title", children: [_jsx(AppstoreOutlined, { style: { color: 'var(--primary-color)' } }), "\u7814\u7A76\u9879\u76EE\u5E93"] }), _jsxs("div", { style: { display: 'flex', gap: 16 }, children: [_jsx(Input, { placeholder: "\u641C\u7D22\u9879\u76EEID\u6216\u4E3B\u9898...", prefix: _jsx(SearchOutlined, { style: { color: 'var(--text-secondary)' } }), allowClear: true, value: q, onChange: (e) => onSearch(e.target.value), className: "search-input", style: { width: 280 } }), _jsx(Link, { to: "/wizard", children: _jsx(Button, { type: "primary", icon: _jsx(ExperimentOutlined, {}), size: "middle", className: "action-btn action-btn-primary", children: "\u65B0\u5EFA\u7814\u7A76" }) })] })] }) }), _jsx(Table, { className: "projects-table", rowKey: "job_id", columns: columns, dataSource: [...filtered].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0)), loading: loading, pagination: {
                        pageSize: 10,
                        showTotal: (total) => `共 ${total} 个项目`,
                        showSizeChanger: true,
                        showQuickJumper: true
                    } })] }) }));
}
