import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from 'react';
import { Card, Table, Empty, Button, message } from 'antd';
import { listReports, listJobs, executeJobAsync } from '../api/research';
import { Link } from 'react-router-dom';
export default function Reports() {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [plotsByJob, setPlotsByJob] = useState({});
    useEffect(() => {
        setLoading(true);
        Promise.all([listReports(), listJobs()])
            .then(([r, j]) => {
            const reports = r.reports || [];
            const jobs = (j.jobs || []);
            const map = {};
            jobs.forEach((it) => { map[it.job_id] = Array.isArray(it.plots) ? it.plots : []; });
            setPlotsByJob(map);
            setData(reports);
        })
            .finally(() => setLoading(false));
    }, []);
    // 解析静态资源前缀，确保在开发模式下也能正确加载图片
    const staticPrefix = useMemo(() => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        // 后端将API挂载在 /api，静态资源在根域名下，需去掉 /api
        return baseApi ? baseApi.replace(/\/api$/, '') : '';
    }, []);
    const columns = [
        { title: 'Job ID', dataIndex: 'job_id', key: 'job_id', render: (v) => _jsx(Link, { to: `/report/${v}`, children: v }) },
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
            dataIndex: 'preview',
            key: 'preview',
            render: (_, r) => {
                const jobId = r.job_id;
                const plots = plotsByJob[jobId] || [];
                const show = plots.slice(0, 3);
                if (!show.length)
                    return _jsx(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "\u65E0\u56FE\u8868" });
                return (_jsx("div", { style: { display: 'flex', gap: 8 }, children: show.map((fname) => {
                        const src = `${staticPrefix}/static/jobs/${jobId}/plots/${fname}`;
                        return (_jsx("img", { src: src, alt: fname, style: { width: 80, height: 60, objectFit: 'cover', borderRadius: 6, border: '1px solid #eee' }, crossOrigin: "anonymous" }, fname));
                    }) }));
            },
        },
        { title: '报告', dataIndex: 'report_url', key: 'report_url', render: (_, r) => _jsx(Link, { to: `/report/${r.job_id}`, children: "\u67E5\u770B\u62A5\u544A" }) },
        {
            title: '操作',
            key: 'action',
            render: (_, r) => (_jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx(Link, { to: `/compose/${r.job_id}`, children: _jsx(Button, { size: "small", children: "\u91CD\u65B0\u751F\u6210\u62A5\u544A" }) }), _jsx(Button, { size: "small", type: "primary", onClick: async () => {
                            try {
                                const res = await executeJobAsync(r.job_id);
                                if (res.started)
                                    message.success('已启动后台重新执行');
                            }
                            catch (e) {
                                const msg = e?.response?.data?.detail || '重新执行失败';
                                message.error(msg);
                            }
                        }, children: "\u91CD\u65B0\u6267\u884C" })] })),
        },
    ];
    return (_jsx(Card, { title: "\u62A5\u544A\u4E2D\u5FC3", children: _jsx(Table, { rowKey: "job_id", columns: columns, dataSource: [...data].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0)), loading: loading, pagination: { pageSize: 10 } }) }));
}
