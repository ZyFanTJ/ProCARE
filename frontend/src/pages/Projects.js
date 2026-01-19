import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from 'react';
import { Card, Table, Tag, Button, message, Empty, Space, Image, Popconfirm } from 'antd';
import { listJobs, deleteJob } from '../api/research';
import { Link, useSearchParams } from 'react-router-dom';
export default function Projects() {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [params] = useSearchParams();
    useEffect(() => {
        setLoading(true);
        listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false));
    }, []);
    const staticPrefix = useMemo(() => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        return baseApi ? baseApi.replace(/\/api$/, '') : '';
    }, []);
    const q = (params.get('q') || '').trim().toLowerCase();
    const filtered = q ? data.filter((it) => (it.job_id || '').toLowerCase().includes(q) || (it.topic || '').toLowerCase().includes(q)) : data;
    const columns = [
        { title: '项目', dataIndex: 'job_id', key: 'job_id', render: (v, r) => (_jsxs(Space, { direction: "vertical", size: 2, children: [_jsx(Link, { to: `/project/${v}`, children: v }), _jsx("div", { style: { color: '#999' }, children: r.topic || '未设置主题' })] })) },
        {
            title: '创建时间',
            dataIndex: 'created_ts',
            key: 'created_ts',
            render: (v) => v ? new Date(v * 1000).toLocaleString() : '-',
            sorter: (a, b) => (a.created_ts || 0) - (b.created_ts || 0),
            defaultSortOrder: 'descend',
        },
        {
            title: '预览',
            dataIndex: 'plots',
            key: 'preview',
            render: (plots, r) => {
                const show = Array.isArray(plots) ? plots.slice(0, 3) : [];
                if (!show.length)
                    return _jsx(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "\u65E0\u56FE\u8868" });
                return (_jsx(Image.PreviewGroup, { children: _jsx("div", { style: { display: 'flex', gap: 8 }, children: show.map((fname) => {
                            const src = `${staticPrefix}/static/jobs/${r.job_id}/plots/${fname}`;
                            return (_jsx(Image, { src: src, alt: fname, width: 80, height: 60, style: { objectFit: 'cover', borderRadius: 6, border: '1px solid #eee' }, crossOrigin: "anonymous" }, fname));
                        }) }) }));
            },
        },
        {
            title: '状态',
            dataIndex: 'success',
            key: 'status',
            render: (v, r) => (_jsxs(Space, { children: [v === true ? _jsx(Tag, { color: "green", children: "\u6210\u529F" }) : v === false ? _jsx(Tag, { color: "red", children: "\u5931\u8D25" }) : _jsx(Tag, { children: "\u672A\u77E5" }), r.report_exists ? _jsx(Tag, { color: "blue", children: "\u62A5\u544A\u5DF2\u751F\u6210" }) : _jsx(Tag, { children: "\u62A5\u544A\u672A\u751F\u6210" })] })),
        },
        {
            title: '操作',
            key: 'action',
            render: (_, r) => (_jsxs(Space, { children: [_jsx(Link, { to: `/project/${r.job_id}`, children: _jsx(Button, { size: "small", type: "primary", children: "\u7BA1\u7406\u4E0E\u67E5\u770B" }) }), _jsx(Link, { to: `/report/${r.job_id}`, children: _jsx(Button, { size: "small", children: "\u67E5\u770B\u62A5\u544A" }) }), _jsx(Link, { to: `/compose/${r.job_id}`, children: _jsx(Button, { size: "small", type: "default", children: "\u6309\u7AE0\u8282\u91CD\u65B0\u751F\u6210" }) }), _jsx(Popconfirm, { title: "\u786E\u8BA4\u5220\u9664\u8BE5\u7814\u7A76\u9879\u76EE\uFF1F", description: "\u5220\u9664\u540E\u4E0D\u53EF\u6062\u590D\uFF0C\u5305\u542B\u62A5\u544A\u4E0E\u56FE\u8868\u6587\u4EF6\u3002", okText: "\u5220\u9664", cancelText: "\u53D6\u6D88", onConfirm: async () => {
                            try {
                                const res = await deleteJob(r.job_id);
                                if (res.ok) {
                                    message.success('已删除');
                                    setLoading(true);
                                    listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false));
                                }
                            }
                            catch (e) {
                                const msg = e?.response?.data?.detail || '删除失败';
                                message.error(msg);
                            }
                        }, children: _jsx(Button, { size: "small", danger: true, children: "\u5220\u9664" }) })] })),
        },
    ];
    return (_jsx(Card, { title: "\u7814\u7A76\u9879\u76EE", extra: q ? _jsxs(Tag, { color: "blue", children: ["\u641C\u7D22\uFF1A", q] }) : undefined, children: _jsx(Table, { rowKey: "job_id", columns: columns, dataSource: [...filtered].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0)), loading: loading, pagination: { pageSize: 10 } }) }));
}
