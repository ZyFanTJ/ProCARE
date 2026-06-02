import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Tabs, Typography, Space, Tag, Button, Image, message, Collapse, Table, Descriptions, Divider } from 'antd';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { fetchStatus, fetchReportPreview, fetchJobPlan, fetchExcelInfo, fetchExecLogs, fetchAnalysisCode, executeJobAsync, streamRunCode } from '../api/research';
import { resolveStaticUrl } from '../api/client';
import JsonTree from '../components/JsonTree';
import CodeViewer from '../components/CodeViewer';
import PlanPreview from '../components/PlanPreview';
import ReportViewer from './ReportViewer';
import '../assets/logs.css';
const { Title } = Typography;
export default function ProjectDetail() {
    const { jobId } = useParams();
    const navigate = useNavigate();
    const [status, setStatus] = useState(null);
    const [plan, setPlan] = useState(null);
    const [excelInfo, setExcelInfo] = useState(null);
    const [execLogs, setExecLogs] = useState(null);
    const [code, setCode] = useState('');
    const [report, setReport] = useState('');
    const [codeCollapsed, setCodeCollapsed] = useState(true);
    const [terminalLogs, setTerminalLogs] = useState([]);
    const [terminalStatus, setTerminalStatus] = useState('idle');
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
    const handleRunCode = async () => {
        if (!jobId)
            return;
        setTerminalLogs([]);
        setTerminalStatus('connecting');
        await streamRunCode(jobId, (chunk) => {
            setTerminalLogs(prev => [...prev, chunk]);
        }, (status) => {
            setTerminalStatus(status);
        });
    };
    const plots = (status?.plots || []);
    const rateTag = (v, mode) => {
        if (typeof v !== 'number' || Number.isNaN(v))
            return _jsx(Tag, { children: "-" });
        const pct = v * 100;
        const color = mode === 'missing'
            ? (pct >= 30 ? 'red' : pct >= 10 ? 'orange' : 'green')
            : (pct >= 90 ? 'green' : pct >= 60 ? 'blue' : 'orange');
        return _jsxs(Tag, { color: color, children: [pct.toFixed(1), "%"] });
    };
    const renderKeyValueTags = (entries, emptyText) => {
        if (!entries.length)
            return _jsx(Typography.Text, { type: "secondary", children: emptyText });
        return (_jsx(Space, { wrap: true, children: entries.map(([k, v]) => (_jsxs(Tag, { children: [k, ": ", String(v)] }, `${k}-${v}`))) }));
    };
    const renderListTags = (items, emptyText) => {
        if (!items.length)
            return _jsx(Typography.Text, { type: "secondary", children: emptyText });
        return (_jsx(Space, { wrap: true, children: items.map((v) => (_jsx(Tag, { children: String(v) }, String(v)))) }));
    };
    const renderSheetProfile = (sheetName, sheetProfile, fallbackColumns) => {
        const dtypes = sheetProfile?.dtypes || {};
        const missing = sheetProfile?.missing_rate || {};
        const unique = sheetProfile?.unique_rate || {};
        const samples = sheetProfile?.samples || {};
        const topValues = sheetProfile?.top_values || {};
        const columnNames = Array.isArray(fallbackColumns) && fallbackColumns.length
            ? fallbackColumns
            : Object.keys(dtypes);
        const rows = columnNames.map((col) => ({
            key: col,
            name: col,
            dtype: dtypes[col] || '-',
            missing: missing[col],
            unique: unique[col],
            samples: Array.isArray(samples[col]) ? samples[col] : [],
            topValues: Array.isArray(topValues[col]) ? topValues[col] : [],
        }));
        const dtypeCounts = Object.values(dtypes).reduce((acc, v) => {
            const k = String(v || 'unknown');
            acc[k] = (acc[k] || 0) + 1;
            return acc;
        }, {});
        const dtypeTags = Object.entries(dtypeCounts).map(([k, v]) => `${k}: ${v}`);
        const candidateKeys = Array.isArray(sheetProfile?.candidate_keys) ? sheetProfile.candidate_keys : [];
        const knowledge = sheetProfile?.knowledge || {};
        const variableRoles = Object.entries(knowledge?.variable_roles || {});
        const ontologyMapping = Object.entries(knowledge?.ontology_mapping || {});
        const plausibility = Object.entries(knowledge?.plausibility || {});
        const studyDesign = knowledge?.study_design || '';
        const summary = sheetProfile?.llm_summary || '';
        return (_jsxs("div", { children: [_jsx(Descriptions, { size: "small", column: 2, items: [
                        { key: 'dtype', label: '类型分布', children: dtypeTags.length ? renderListTags(dtypeTags, '暂无') : _jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0" }) },
                        { key: 'keys', label: '候选主键', children: renderListTags(candidateKeys, '无候选主键') },
                        { key: 'summary', label: '摘要', children: summary ? _jsx(Typography.Text, { children: summary }) : _jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0\u6458\u8981" }) },
                        { key: 'study', label: '研究角色', children: studyDesign ? _jsx(Typography.Text, { children: studyDesign }) : _jsx(Typography.Text, { type: "secondary", children: "\u672A\u77E5" }) },
                    ] }), _jsx(Divider, { style: { margin: '12px 0' } }), _jsx(Table, { size: "small", pagination: false, rowKey: "key", dataSource: rows, columns: [
                        { title: '字段', dataIndex: 'name', key: 'name', width: 180, render: (v) => _jsx("span", { style: { fontFamily: 'var(--font-mono)' }, children: v }) },
                        { title: '类型', dataIndex: 'dtype', key: 'dtype', width: 120, render: (v) => _jsx(Tag, { color: "blue", children: v }) },
                        { title: '缺失率', dataIndex: 'missing', key: 'missing', width: 100, render: (v) => rateTag(v, 'missing') },
                        { title: '唯一率', dataIndex: 'unique', key: 'unique', width: 100, render: (v) => rateTag(v, 'unique') },
                        {
                            title: '示例值',
                            dataIndex: 'samples',
                            key: 'samples',
                            render: (v) => (_jsx("div", { style: { maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, title: (v || []).join(', '), children: (v || []).join(', ') || '-' }))
                        },
                        {
                            title: '高频值',
                            dataIndex: 'topValues',
                            key: 'topValues',
                            render: (v) => (_jsx("div", { style: { maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, title: (v || []).join(', '), children: (v || []).join(', ') || '-' }))
                        },
                    ] }), _jsx(Divider, { style: { margin: '12px 0' } }), _jsx(Collapse, { defaultActiveKey: [], items: [
                        {
                            key: 'knowledge',
                            label: '知识画像',
                            children: (_jsxs(Space, { direction: "vertical", size: 12, style: { width: '100%' }, children: [_jsxs("div", { children: [_jsx(Typography.Text, { strong: true, children: "\u53D8\u91CF\u89D2\u8272" }), _jsx("div", { style: { marginTop: 6 }, children: renderKeyValueTags(variableRoles, '暂无角色映射') })] }), _jsxs("div", { children: [_jsx(Typography.Text, { strong: true, children: "\u6982\u5FF5\u6620\u5C04" }), _jsx("div", { style: { marginTop: 6 }, children: renderKeyValueTags(ontologyMapping, '暂无映射') })] }), _jsxs("div", { children: [_jsx(Typography.Text, { strong: true, children: "\u5408\u7406\u6027\u68C0\u67E5" }), _jsx("div", { style: { marginTop: 6 }, children: renderKeyValueTags(plausibility, '暂无检查结果') })] })] }))
                        }
                    ] })] }));
    };
    const renderExcelProfile = () => {
        if (!excelInfo)
            return _jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0Excel\u753B\u50CF" });
        const sheets = Array.isArray(excelInfo?.sheets) ? excelInfo.sheets : Object.keys(excelInfo?.profile || {});
        const columnsMap = excelInfo?.columns || {};
        const totalColumns = sheets.reduce((sum, s) => sum + (Array.isArray(columnsMap?.[s]) ? columnsMap[s].length : 0), 0);
        const description = excelInfo?.description || '';
        const path = excelInfo?.path || '';
        const profile = excelInfo?.profile || {};
        return (_jsxs("div", { children: [_jsx(Descriptions, { size: "small", column: 2, items: [
                        { key: 'sheets', label: 'Sheet数', children: sheets.length || '-' },
                        { key: 'columns', label: '字段总数', children: totalColumns || '-' },
                        { key: 'path', label: '数据路径', children: path ? _jsx(Typography.Text, { children: path }) : _jsx(Typography.Text, { type: "secondary", children: "\u672A\u77E5" }) },
                        { key: 'desc', label: '描述', children: description ? _jsx(Typography.Text, { children: description }) : _jsx(Typography.Text, { type: "secondary", children: "\u65E0\u63CF\u8FF0" }) },
                    ] }), _jsx(Divider, { style: { margin: '12px 0' } }), sheets.length ? (_jsx(Collapse, { defaultActiveKey: sheets.slice(0, 1), items: sheets.map((s) => ({
                        key: s,
                        label: s,
                        children: renderSheetProfile(s, profile?.[s], columnsMap?.[s] || []),
                    })) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u672A\u627E\u5230Sheet" })), _jsx(Collapse, { style: { marginTop: 12 }, defaultActiveKey: [], items: [
                        { key: 'json', label: '原始JSON', children: (_jsx(JsonTree, { data: excelInfo, defaultCollapsed: true })) }
                    ] })] }));
    };
    return (_jsxs("div", { children: [_jsx(Title, { level: 3, children: "\u7814\u7A76\u9879\u76EE\u8BE6\u60C5" }), _jsxs(Space, { style: { marginBottom: 12 }, wrap: true, children: [_jsx(Tag, { color: status?.success ? 'green' : (status?.running ? 'orange' : 'red'), children: status?.success ? '成功' : (status?.running ? '执行中' : '未成功') }), _jsx(Link, { to: `/report/${jobId}`, children: _jsx(Button, { type: "link", children: "\u67E5\u770B\u62A5\u544A" }) }), _jsx(Link, { to: `/compose/${jobId}`, children: _jsx(Button, { type: "link", children: "\u7EC4\u5408\u62A5\u544A\u7AE0\u8282" }) }), _jsx(Link, { to: `/project/${jobId}/paper`, children: _jsx(Button, { type: "link", children: "\u8BBA\u6587\u751F\u6210" }) })] }), _jsx(Tabs, { onTabClick: (key) => {
                    if (key === 'paper-generation' && jobId)
                        navigate(`/project/${jobId}/paper`);
                }, items: [
                    {
                        key: 'overview',
                        label: '概览',
                        children: (_jsxs(Card, { bordered: false, children: [_jsxs(Space, { wrap: true, children: [_jsxs(Tag, { children: ["Job: ", jobId] }), _jsxs(Tag, { children: ["\u6B65\u9AA4: ", status?.current_step, "/", status?.max_iters] }), _jsxs(Tag, { children: ["\u56FE\u8868: ", plots.length] })] }), !!plots?.length && (_jsx("div", { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginTop: 12 }, children: plots.map((p) => (_jsxs("div", { style: { border: '1px solid var(--border-color)', borderRadius: 8, padding: 12, background: 'var(--bg-component)' }, children: [_jsx("div", { style: { width: '100%', height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-app)', borderRadius: 4, overflow: 'hidden' }, children: _jsx(Image, { src: resolveStaticUrl(`/static/jobs/${jobId}/plots/${p}`), alt: p, style: { maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' } }) }), _jsx("div", { style: { fontSize: 13, marginTop: 8, fontWeight: 500, color: 'var(--text-primary)', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, title: p, children: p })] }, p))) }))] })),
                    },
                    {
                        key: 'plan',
                        label: '研究计划',
                        children: (_jsx(Card, { bordered: false, children: plan ? (_jsxs("div", { children: [_jsx(PlanPreview, { plan: plan }), _jsx(Collapse, { style: { marginTop: 12 }, defaultActiveKey: [], items: [{ key: 'json', label: '原始JSON', children: (_jsx(JsonTree, { data: plan, defaultCollapsed: true })) }] })] })) : (_jsx(Typography.Text, { type: "secondary", children: "\u65E0\u8BA1\u5212\u6570\u636E" })) })),
                    },
                    {
                        key: 'profile',
                        label: '数据画像',
                        children: (_jsx(Card, { bordered: false, children: renderExcelProfile() })),
                    },
                    {
                        key: 'code',
                        label: '分析代码',
                        children: (_jsxs(Card, { bordered: false, children: [_jsxs(Space, { style: { marginBottom: 8 }, wrap: true, children: [_jsx(Button, { onClick: () => copyText(code), children: "\u590D\u5236\u4EE3\u7801" }), _jsx(Button, { onClick: () => setCodeCollapsed((v) => !v), children: codeCollapsed ? '展开全部' : '收起' }), _jsx(Button, { onClick: handleRunCode, loading: terminalStatus === 'streaming' || terminalStatus === 'connecting', children: "\u8FD0\u884C\u5F53\u524D\u4EE3\u7801" }), _jsx(Button, { type: "primary", onClick: async () => {
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
                                            }, children: "\u91CD\u65B0\u6267\u884C" }), _jsx("a", { href: resolveStaticUrl(`/static/jobs/${jobId}/analysis.py`), target: "_blank", rel: "noreferrer", children: "\u5728\u65B0\u7A97\u53E3\u6253\u5F00" })] }), code ? (_jsx("div", { style: { maxHeight: codeCollapsed ? undefined : 520, overflow: codeCollapsed ? undefined : 'auto' }, children: _jsx(CodeViewer, { code: code, collapsed: codeCollapsed }) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u672A\u627E\u5230\u5206\u6790\u4EE3\u7801" })), (terminalLogs.length > 0 || terminalStatus === 'streaming' || terminalStatus === 'connecting') && (_jsxs("div", { style: { marginTop: 16, background: '#1e1e1e', padding: 12, borderRadius: 8, color: '#d4d4d4', fontFamily: 'monospace', maxHeight: 300, overflow: 'auto' }, children: [_jsxs("div", { style: { marginBottom: 8, borderBottom: '1px solid #333', paddingBottom: 4, display: 'flex', justifyContent: 'space-between' }, children: [_jsx("span", { children: "\u7EC8\u7AEF\u8F93\u51FA" }), _jsx("span", { style: { fontSize: 12, opacity: 0.7 }, children: terminalStatus })] }), _jsx("pre", { style: { margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12 }, children: terminalLogs.join('') })] }))] })),
                    },
                    {
                        key: 'logs',
                        label: '执行日志',
                        children: (_jsx(Card, { bordered: false, children: Array.isArray(execLogs?.logs) && execLogs.logs.length ? (_jsx("div", { children: execLogs.logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["\u6B65\u9AA4 ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" }) }), _jsx(CollapsiblePre, { text: l.code, maxLines: 20 })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "stdout" }) }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10 })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "stderr" }) }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10 })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsx("div", { className: "log-block__header", children: _jsx(Typography.Text, { children: "LLM\u5EFA\u8BAE" }) }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10 })] }))] }, idx))) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u6682\u65E0\u6267\u884C\u65E5\u5FD7" })) })),
                    },
                    {
                        key: 'report',
                        label: '报告预览',
                        children: (_jsx(Card, { bordered: false, children: _jsx(ReportViewer, {}) })),
                    },
                    {
                        key: 'paper-generation',
                        label: '论文生成',
                        children: (_jsx(Card, { bordered: false, children: _jsx(Button, { type: "primary", onClick: () => jobId && navigate(`/project/${jobId}/paper`), children: "\u8FDB\u5165\u8BBA\u6587\u751F\u6210" }) })),
                    },
                ] })] }));
}
