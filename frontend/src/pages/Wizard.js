import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { Steps, Card, Form, Input, Button, Upload, message, Typography, Spin, Result, Collapse, Image, Space } from 'antd';
import { InboxOutlined, CodeOutlined, CheckCircleOutlined, CloseCircleOutlined, BulbOutlined, CopyOutlined } from '@ant-design/icons';
import { uploadExcel, streamPlan, streamRefinePlan, executeJobAsync, updatePlan, fetchStatus } from '../api/research';
import { Link } from 'react-router-dom';
import '../assets/logs.css';
import JsonTree from '../components/JsonTree';
import CodeViewer from '../components/CodeViewer';
const { Title, Paragraph } = Typography;
export default function Wizard() {
    const [current, setCurrent] = useState(0);
    const [topic, setTopic] = useState('');
    const [excelPath, setExcelPath] = useState('');
    const [excelInfo, setExcelInfo] = useState(null);
    const [excelDesc, setExcelDesc] = useState('');
    const [loading, setLoading] = useState(false);
    const [running, setRunning] = useState(false);
    const [job, setJob] = useState(null);
    const [initialPlan, setInitialPlan] = useState(null);
    const [refinedPlan, setRefinedPlan] = useState(null);
    const [planText, setPlanText] = useState('');
    const [error, setError] = useState('');
    const [logs, setLogs] = useState([]);
    const [plots, setPlots] = useState([]);
    const [collapsedStates, setCollapsedStates] = useState({});
    const copyText = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
            message.success('已复制到剪贴板');
        }
        catch {
            message.warning('复制失败，请手动选择文本');
        }
    };
    // 折叠的预格式文本组件，默认折叠，显示前N行
    const isCollapsed = (key, defaultValue = true) => (collapsedStates.hasOwnProperty(key) ? collapsedStates[key] : defaultValue);
    const toggleCollapsed = (key, defaultValue = true) => {
        setCollapsedStates(prev => ({
            ...prev,
            [key]: !(prev.hasOwnProperty(key) ? prev[key] : defaultValue),
        }));
    };
    const CollapsiblePre = ({ text, maxLines = 10, collapsed = true }) => {
        const lines = (text || '').split(/\r?\n/);
        const needCollapse = lines.length > maxLines;
        const shown = collapsed && needCollapse ? lines.slice(0, maxLines).join('\n') + '\n…（已折叠）' : text;
        return _jsx("pre", { className: "log-pre", children: shown });
    };
    const steps = [
        { title: '输入主题与上传文件' },
        { title: '生成计划' },
        { title: '生成与执行' },
        { title: '查看报告' },
    ];
    const next = () => setCurrent((c) => Math.min(c + 1, steps.length - 1));
    const prev = () => setCurrent((c) => Math.max(c - 1, 0));
    const doUpload = async ({ file, onSuccess, onError }) => {
        try {
            const f = file;
            const res = await uploadExcel(f, excelDesc);
            setExcelPath(res.excel_path);
            setExcelInfo(res.excel_info);
            if (res.duplicate) {
                message.info(`检测到相同文件，已复用（MD5: ${res.md5})`);
            }
            else {
                message.success('Excel上传与分析成功');
            }
            onSuccess && onSuccess({}, new XMLHttpRequest());
        }
        catch (e) {
            message.error(e?.response?.data?.detail || '上传失败');
            setError(e?.response?.data?.detail || '上传失败');
            onError && onError(e);
        }
    };
    const [connStatus, setConnStatus] = useState('idle');
    const [controller, setController] = useState(null);
    const appendChunkTypewriter = (t) => {
        if (!t)
            return;
        let i = 0;
        const step = Math.max(10, Math.floor(t.length / 50));
        const emit = () => {
            if (i >= t.length)
                return;
            const next = t.slice(i, i + step);
            i += step;
            setPlanText(prev => prev + next);
            try {
                const el = document.getElementById('plan-textarea');
                if (el) {
                    el.selectionStart = el.value.length;
                    el.selectionEnd = el.value.length;
                    el.scrollTop = el.scrollHeight;
                }
            }
            catch { }
            setTimeout(emit, 20);
        };
        emit();
    };
    const doPlan = async () => {
        if (!topic || !excelPath) {
            message.warning('请先填写主题并上传Excel');
            return;
        }
        setLoading(true);
        setError('');
        try {
            setPlanText('');
            setConnStatus('idle');
            const ctrl = new AbortController();
            setController(ctrl);
            const res = await streamPlan({ topic, excel_path: excelPath, excel_description: excelDesc, job_id: job?.id }, (t) => {
                appendChunkTypewriter(t);
            }, (st) => setConnStatus(st), ctrl.signal);
            if (res.job_id)
                setJob({ id: res.job_id });
            if (res.plan) {
                setInitialPlan(res.plan);
                setPlanText(JSON.stringify(res.plan, null, 2));
                message.success('研究计划生成成功');
            }
            else {
                message.warning('流式结果未解析为JSON，请手动检查');
            }
        }
        catch (e) {
            const msg = e?.response?.data?.detail || '生成计划失败';
            setError(msg);
            message.error(msg);
        }
        finally {
            setLoading(false);
            setConnStatus('idle');
            setController(null);
        }
    };
    const doRefinePlan = async () => {
        if (!job?.id) {
            message.warning('请先生成初步计划');
            return;
        }
        setLoading(true);
        setError('');
        try {
            setPlanText('');
            setConnStatus('idle');
            const ctrl = new AbortController();
            setController(ctrl);
            const res = await streamRefinePlan(job.id, (t) => {
                appendChunkTypewriter(t);
            }, (st) => setConnStatus(st), ctrl.signal);
            if (res.plan_refined) {
                setRefinedPlan(res.plan_refined);
                setPlanText(JSON.stringify(res.plan_refined, null, 2));
                message.success('细化计划生成成功');
            }
            else {
                message.warning('流式结果未解析为JSON，请手动检查');
            }
        }
        catch (e) {
            const msg = e?.response?.data?.detail || '细化计划生成失败';
            setError(msg);
            message.error(msg);
        }
        finally {
            setLoading(false);
            setConnStatus('idle');
            setController(null);
        }
    };
    const saveEditedPlan = async () => {
        if (!job?.id) {
            message.warning('请先生成或选择一个job');
            return;
        }
        try {
            const parsed = JSON.parse(planText);
            const res = await updatePlan(job.id, parsed);
            if (res.ok) {
                if (refinedPlan) {
                    setRefinedPlan(parsed);
                }
                else {
                    setInitialPlan(parsed);
                }
                message.success('计划已保存');
            }
        }
        catch (e) {
            const msg = e?.response?.data?.detail || '保存失败，请确认JSON格式正确';
            message.error(msg);
        }
    };
    const runResearch = async () => {
        if (!job?.id) {
            message.warning('请先生成研究计划');
            return;
        }
        setLoading(true);
        setRunning(true);
        setError('');
        try {
            // 启动异步执行
            const start = await executeJobAsync(job.id);
            if (start.started) {
                message.success('已开始后台执行，正在获取实时进度...');
                // 轮询状态直到完成
                const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                const prefix = baseApi.replace(/\/api$/, '');
                const timer = setInterval(async () => {
                    try {
                        const st = await fetchStatus(job.id);
                        setLogs(st.logs || []);
                        setPlots(st.plots || []);
                        // 保持在当前步骤展示实时进度
                        if (!st.running) {
                            clearInterval(timer);
                            setRunning(false);
                            setLoading(false);
                            setJob({ id: job.id, success: st.success, report: `${prefix}/static/jobs/${job.id}/report.md` });
                            const finalMsg = st.success
                                ? '执行成功'
                                : (st.message || (st.max_iters_reached ? '已达到最大重试次数，执行未成功' : '执行未成功'));
                            const notify = st.success ? message.success : message.warning;
                            notify(finalMsg);
                            setCurrent(3);
                        }
                    }
                    catch (e) {
                        clearInterval(timer);
                        setRunning(false);
                    }
                }, 1500);
            }
        }
        catch (e) {
            const msg = e?.response?.data?.detail || '执行失败';
            setError(msg);
            message.error(msg);
        }
        finally {
            // 保持loading由轮询结束控制
        }
    };
    return (_jsxs("div", { children: [_jsx(Title, { level: 3, children: "\u65B0\u5EFA\u7814\u7A76" }), _jsx(Card, { children: _jsx(Steps, { current: current, items: steps }) }), current === 0 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u8BF7\u8F93\u5165\u7814\u7A76\u4E3B\u9898\uFF0C\u5E76\u4E0A\u4F20\u6570\u636E\u6587\u4EF6\uFF0C\u4E24\u8005\u5171\u540C\u7528\u4E8E\u751F\u6210\u7814\u7A76\u8BA1\u5212\u3002" }), _jsxs(Form, { layout: "vertical", children: [_jsx(Form.Item, { label: "\u7814\u7A76\u4E3B\u9898", children: _jsx(Input.TextArea, { rows: 3, value: topic, onChange: (e) => setTopic(e.target.value), placeholder: "\u4F8B\u5982\uFF1A\u809D\u764C\u60A3\u8005\u4E94\u5E74\u751F\u5B58\u7387" }) }), _jsx(Form.Item, { label: "\u8865\u5145\u8868\u683C\u63CF\u8FF0\uFF08\u53EF\u9009\uFF09", children: _jsx(Input.TextArea, { rows: 3, value: excelDesc, onChange: (e) => setExcelDesc(e.target.value), placeholder: "\u4F8B\u5982\uFF1ASheet1\u4E3A\u60A3\u8005\u57FA\u672C\u4FE1\u606F\uFF0CSheet2\u4E3A\u968F\u8BBF\u8BB0\u5F55..." }) }), _jsx(Form.Item, { label: "\u4E0A\u4F20Excel\u6587\u4EF6", children: _jsxs(Upload.Dragger, { name: "file", customRequest: doUpload, accept: ".xlsx,.xls", maxCount: 1, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u70B9\u51FB\u6216\u62D6\u62FDExcel\u5230\u6B64\u533A\u57DF\u4E0A\u4F20" })] }) }), excelInfo && (_jsx(Collapse, { defaultActiveKey: [], items: [{
                                        key: 'excel-structure',
                                        label: 'Excel结构信息',
                                        children: (_jsx(JsonTree, { data: excelInfo, defaultCollapsed: true })),
                                    }] })), _jsx(Form.Item, { style: { marginTop: 16 }, children: _jsx(Button, { type: "primary", onClick: next, disabled: !topic || !excelPath, children: "\u4E0B\u4E00\u6B65" }) })] })] })), current === 1 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u8BF7\u751F\u6210\u7814\u7A76\u8BA1\u5212\u3002\u8BA1\u5212\u5C06\u7528\u4E8E\u6307\u5BFC\u4EE3\u7801\u751F\u6210\u4E0E\u6267\u884C\u3002" }), _jsxs(Space, { style: { marginBottom: 12 }, children: [_jsx(Button, { type: "primary", onClick: doPlan, disabled: !excelPath || !topic, children: "\u751F\u6210\u7814\u7A76\u8BA1\u5212" }), (connStatus === 'connecting' || connStatus === 'streaming') && (_jsx(Button, { danger: true, onClick: () => controller && controller.abort(), children: "\u4E2D\u65AD" })), connStatus !== 'idle' && (_jsxs(Typography.Text, { style: { marginLeft: 8 }, children: ["\u72B6\u6001\uFF1A", connStatus] }))] }), !!error && (_jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: doPlan, children: "\u91CD\u8BD5\u6B64\u6B65\u9AA4" }) })), _jsx("div", { style: { marginTop: 16 }, children: loading && _jsx(Spin, {}) }), _jsxs(Card, { type: "inner", title: "\u8BA1\u5212\uFF08\u53EF\u7F16\u8F91\uFF09", style: { marginTop: 16 }, children: [_jsx(Input.TextArea, { id: "plan-textarea", rows: 12, value: planText, onChange: (e) => setPlanText(e.target.value) }), _jsxs("div", { style: { marginTop: 12 }, children: [_jsx(Button, { type: "default", onClick: saveEditedPlan, style: { marginRight: 8 }, children: "\u4FDD\u5B58\u8BA1\u5212\u4FEE\u6539" }), _jsx(Button, { onClick: doRefinePlan, type: "primary", children: "\u6839\u636E\u5B57\u6BB5\u7406\u89E3\u751F\u6210\u7EC6\u5316\u8BA1\u5212" }), _jsx(Button, { onClick: () => setCurrent(2), style: { marginLeft: 8 }, children: "\u4E0B\u4E00\u6B65\uFF1A\u751F\u6210\u4E0E\u6267\u884C" })] })] })] })), current === 2 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u5C06\u57FA\u4E8EExcel\u7ED3\u6784\u4FE1\u606F\u5236\u5B9A\u8BA1\u5212\u5E76\u751F\u6210Python\u4EE3\u7801\uFF0C\u8FD0\u884C\u540E\u751F\u6210\u56FE\u8868\u4E0E\u62A5\u544A\u3002" }), _jsx(Button, { type: "primary", onClick: runResearch, disabled: !excelPath || !topic, children: "\u751F\u6210\u5E76\u6267\u884C\u7814\u7A76" }), _jsx("div", { style: { marginTop: 16 }, children: loading && _jsx(Spin, {}) }), !!error && (_jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: runResearch, children: "\u91CD\u8BD5\u6B64\u6B65\u9AA4" }) })), !!logs?.length && (_jsx(Card, { type: "inner", title: "\u6267\u884C\u8FDB\u5EA6\uFF08\u5B9E\u65F6\uFF09", style: { marginTop: 16 }, children: logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["Step ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CodeOutlined, {}), _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.code), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`code-${idx}`, false), children: isCollapsed(`code-${idx}`, false) ? '展开全部' : '收起' })] })] }), _jsx(CodeViewer, { code: l.code, collapsed: isCollapsed(`code-${idx}`, false) })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CheckCircleOutlined, {}), _jsx(Typography.Text, { children: "\u6267\u884C\u7ED3\u679C\uFF08stdout\uFF09" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stdout), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`stdout-${idx}`, true), children: isCollapsed(`stdout-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10, collapsed: isCollapsed(`stdout-${idx}`, true) })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CloseCircleOutlined, {}), _jsx(Typography.Text, { children: "\u9519\u8BEF\u4FE1\u606F\uFF08stderr\uFF09" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stderr), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`stderr-${idx}`, true), children: isCollapsed(`stderr-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10, collapsed: isCollapsed(`stderr-${idx}`, true) })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(BulbOutlined, {}), _jsx(Typography.Text, { children: "LLM\u4FEE\u6539\u5EFA\u8BAE" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.llm_suggestion), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`suggestion-${idx}`, true), children: isCollapsed(`suggestion-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10, collapsed: isCollapsed(`suggestion-${idx}`, true) })] }))] }, idx))) })), !!plots?.length && (_jsx(Card, { type: "inner", title: "\u56FE\u8868\u9884\u89C8\uFF08\u5B9E\u65F6\uFF09", style: { marginTop: 16 }, children: _jsx("div", { style: { display: 'flex', gap: 12, flexWrap: 'wrap' }, children: plots.map((p) => {
                                const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                                const prefix = baseApi.replace(/\/api$/, '');
                                const src = `${prefix}/static/jobs/${job.id}/plots/${p}`;
                                return (_jsxs("div", { style: { width: 260 }, children: [_jsx(Image, { src: src, alt: p, width: 240, height: 180, style: { objectFit: 'contain' } }), _jsx("div", { style: { fontSize: 12, marginTop: 4 }, children: p })] }, p));
                            }) }) }))] })), current === 3 && job && (_jsxs(Card, { style: { marginTop: 16 }, children: [job.success ? (_jsx(Result, { status: "success", title: "\u6267\u884C\u6210\u529F", subTitle: `报告路径：${job.report}`, extra: (_jsxs(Space, { children: [_jsx(Link, { to: `/report/${job.id}`, children: "\u67E5\u770B\u62A5\u544A" }), _jsx(Link, { to: `/compose/${job.id}`, children: "\u6309\u9700\u751F\u6210\u62A5\u544A\u7AE0\u8282" })] })) })) : (_jsx(Result, { status: "warning", title: "\u6267\u884C\u672A\u6210\u529F", subTitle: "\u8BF7\u67E5\u770B\u65E5\u5FD7\u6216\u91CD\u8BD5" })), !!logs?.length && (_jsx(Card, { type: "inner", title: "\u6267\u884C\u65E5\u5FD7\uFF08\u591A\u8F6E\uFF09", style: { marginTop: 16 }, children: logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["Step ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CodeOutlined, {}), _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.code), children: "\u590D\u5236" })] }), _jsx(CodeViewer, { code: l.code })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CheckCircleOutlined, {}), _jsx(Typography.Text, { children: "\u6267\u884C\u7ED3\u679C\uFF08stdout\uFF09" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stdout), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10 })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CloseCircleOutlined, {}), _jsx(Typography.Text, { children: "\u9519\u8BEF\u4FE1\u606F\uFF08stderr\uFF09" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stderr), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10 })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(BulbOutlined, {}), _jsx(Typography.Text, { children: "LLM\u4FEE\u6539\u5EFA\u8BAE" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.llm_suggestion), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10 })] }))] }, idx))) })), !!plots?.length && (_jsxs(Card, { type: "inner", title: "\u56FE\u8868\u9884\u89C8", style: { marginTop: 16 }, children: [_jsx("div", { style: { display: 'flex', gap: 12, flexWrap: 'wrap' }, children: plots.map((p) => {
                                    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                                    const prefix = baseApi.replace(/\/api$/, '');
                                    const src = `${prefix}/static/jobs/${job.id}/plots/${p}`;
                                    return (_jsxs("div", { style: { width: 260 }, children: [_jsx(Image, { src: src, alt: p, width: 240, height: 180, style: { objectFit: 'contain' } }), _jsx("div", { style: { fontSize: 12, marginTop: 4 }, children: p })] }, p));
                                }) }), _jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: () => runResearch(), type: "primary", children: "\u91CD\u65B0\u6267\u884C\u6B64\u7814\u7A76" }) })] }))] }))] }));
}
