import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from 'react';
import { Card, Tabs, Typography, Space, Tag, Button, Image, message, Collapse } from 'antd';
import { Link, useParams } from 'react-router-dom';
import { fetchStatus, fetchReportPreview, fetchJobPlan, fetchExcelInfo, fetchExecLogs, fetchAnalysisCode, executeJobAsync } from '../api/research';
import JsonTree from '../components/JsonTree';
import CodeViewer from '../components/CodeViewer';
import PlanPreview from '../components/PlanPreview';
import ReportViewer from './ReportViewer';
import '../assets/logs.css';
const { Title } = Typography;
export default function ProjectDetail() {
    const { jobId } = useParams();
    const [status, setStatus] = useState(null);
    const [plan, setPlan] = useState(null);
    const [excelInfo, setExcelInfo] = useState(null);
    const [execLogs, setExecLogs] = useState(null);
    const [code, setCode] = useState('');
    const [report, setReport] = useState('');
    const [codeCollapsed, setCodeCollapsed] = useState(true);
    const staticPrefix = useMemo(() => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        return baseApi ? baseApi.replace(/\/api$/, '') : '';
    }, []);
    useEffect(() => {
        if (!jobId)
            return;
        fetchStatus(jobId).then(setStatus).catch(() => setStatus(null));
        fetchJobPlan(jobId).then(setPlan).catch(() => setPlan(null));
        fetchExcelInfo(jobId).then(setExcelInfo).catch(() => setExcelInfo(null));
        fetchExecLogs(jobId).then(setExecLogs).catch(() => setExecLogs(null));
        fetchAnalysisCode(jobId).then(setCode).catch(() => setCode(''));
        fetchReportPreview(jobId).then(setReport).catch(() => setReport(''));
    }, [jobId]);
    const copyText = async (text) => {
        try {
            await navigator.clipboard.writeText(text || '');
            message.success('已复制');
        }
        catch {
            message.warning('复制失败');
        }
    };
    const CollapsiblePre = ({ text, maxLines = 16, collapsed = true }) => {
        const lines = (text || '').split(/\r?\n/);
        const needCollapse = lines.length > maxLines;
        const shown = (collapsed && needCollapse) ? lines.slice(0, maxLines).join('\n') + '\n…（已折叠）' : text;
        return _jsx("pre", { className: "log-pre", children: shown });
    };
    const plots = (status?.plots || []);
    return (_jsxs("div", { children: [_jsx(Title, { level: 3, children: "\u7814\u7A76\u9879\u76EE\u8BE6\u60C5" }), _jsxs(Space, { style: { marginBottom: 12 }, children: [_jsx(Tag, { color: status?.success ? 'green' : (status?.running ? 'orange' : 'red'), children: status?.success ? '成功' : (status?.running ? '执行中' : '未成功') }), _jsx(Link, { to: `/report/${jobId}`, children: _jsx(Button, { type: "link", children: "\u67E5\u770B\u62A5\u544A" }) }), _jsx(Link, { to: `/compose/${jobId}`, children: _jsx(Button, { type: "link", children: "\u7EC4\u5408\u62A5\u544A\u7AE0\u8282" }) })] }), _jsx(Tabs, { items: [
                    {
                        key: 'overview',
                        label: '概览',
                        children: (_jsxs(Card, { bordered: false, children: [_jsxs(Space, { wrap: true, children: [_jsxs(Tag, { children: ["Job: ", jobId] }), _jsxs(Tag, { children: ["\u6B65\u9AA4: ", status?.current_step, "/", status?.max_iters] }), _jsxs(Tag, { children: ["\u56FE\u8868: ", plots.length] })] }), !!plots?.length && (_jsx("div", { style: { display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }, children: plots.map((p) => (_jsxs("div", { style: { width: 260 }, children: [_jsx(Image, { src: `${staticPrefix}/static/jobs/${jobId}/plots/${p}`, alt: p, width: 240, height: 180, style: { objectFit: 'contain' } }), _jsx("div", { style: { fontSize: 12, marginTop: 4 }, children: p })] }, p))) }))] })),
                    },
                    {
                        key: 'plan',
                        label: '研究计划',
                        children: (_jsx(Card, { bordered: false, children: plan ? (_jsxs("div", { children: [_jsx(PlanPreview, { plan: plan }), _jsx(Collapse, { style: { marginTop: 12 }, defaultActiveKey: [], items: [{ key: 'json', label: '原始JSON', children: (_jsx(JsonTree, { data: plan, defaultCollapsed: true })) }] })] })) : (_jsx(Typography.Text, { type: "secondary", children: "\u65E0\u8BA1\u5212\u6570\u636E" })) })),
                    },
                    {
                        key: 'profile',
                        label: '数据画像',
                        children: (_jsx(Card, { bordered: false, children: excelInfo ? _jsx(JsonTree, { data: excelInfo, defaultCollapsed: true }) : _jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0Excel\u753B\u50CF" }) })),
                    },
                    {
                        key: 'code',
                        label: '分析代码',
                        children: (_jsxs(Card, { bordered: false, children: [_jsxs(Space, { style: { marginBottom: 8 }, children: [_jsx(Button, { onClick: () => copyText(code), children: "\u590D\u5236\u4EE3\u7801" }), _jsx(Button, { onClick: () => setCodeCollapsed((v) => !v), children: codeCollapsed ? '展开全部' : '收起' }), _jsx(Button, { type: "primary", onClick: async () => {
                                                if (!jobId)
                                                    return;
                                                try {
                                                    const res = await executeJobAsync(jobId);
                                                    if (res.started)
                                                        message.success('已启动后台重新执行');
                                                }
                                                catch (e) {
                                                    const msg = e?.response?.data?.detail || '重新执行失败';
                                                    message.error(msg);
                                                }
                                            }, children: "\u91CD\u65B0\u6267\u884C" }), _jsx("a", { href: `${staticPrefix}/static/jobs/${jobId}/analysis.py`, target: "_blank", rel: "noreferrer", children: "\u5728\u65B0\u7A97\u53E3\u6253\u5F00" })] }), code ? (_jsx("div", { style: { maxHeight: codeCollapsed ? undefined : 520, overflow: codeCollapsed ? undefined : 'auto' }, children: _jsx(CodeViewer, { code: code, collapsed: codeCollapsed }) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u672A\u627E\u5230\u5206\u6790\u4EE3\u7801" }))] })),
                    },
                    {
                        key: 'logs',
                        label: '执行日志',
                        children: (_jsx(Card, { bordered: false, children: Array.isArray(execLogs?.logs) && execLogs.logs.length ? (_jsx("div", { children: execLogs.logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["Step ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" }) }), _jsx(CollapsiblePre, { text: l.code, maxLines: 20 })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "stdout" }) }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10 })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "stderr" }) }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10 })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "LLM\u5EFA\u8BAE" }) }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10 })] }))] }, idx))) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0\u6267\u884C\u65E5\u5FD7" })) })),
                    },
                    {
                        key: 'report',
                        label: '报告预览',
                        children: (_jsx(Card, { bordered: false, children: _jsx(ReportViewer, {}) })),
                    },
                ] })] }));
}
