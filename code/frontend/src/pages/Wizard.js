import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Steps, Card, Form, Input, Button, Upload, message, Typography, Spin, Result, Collapse, Image, Space, Radio, Checkbox, List, Alert } from 'antd';
import { InboxOutlined, CodeOutlined, CheckCircleOutlined, CloseCircleOutlined, BulbOutlined, CopyOutlined } from '@ant-design/icons';
import { uploadExcel, streamPlan, streamRefinePlan, updatePlan, fetchStatus, streamExecute, fetchJobPlan, fetchExcelInfo, brainstorm, deleteProfile } from '../api/research';
import { Link, useSearchParams } from 'react-router-dom';
import { resolveStaticUrl } from '../api/client';
import '../assets/logs.css';
import JsonTree from '../components/JsonTree';
import CodeViewer from '../components/CodeViewer';
import StructuredLogViewer from '../components/StructuredLogViewer';
const { Title, Paragraph } = Typography;
const statusMap = {
    idle: '未开始',
    connecting: '连接中...',
    streaming: '正在生成...',
    done: '已完成',
    interrupted: '已中断',
    error: '发生错误'
};
export default function Wizard() {
    const [current, setCurrent] = useState(0);
    const [topic, setTopic] = useState('');
    const [excelPath, setExcelPath] = useState('');
    const [excelInfo, setExcelInfo] = useState(null);
    const [excelDesc, setExcelDesc] = useState('');
    const [md5, setMd5] = useState('');
    const [profileReused, setProfileReused] = useState(false);
    const [loading, setLoading] = useState(false);
    const [running, setRunning] = useState(false);
    const [executionFailed, setExecutionFailed] = useState(false);
    const [job, setJob] = useState(null);
    const [initialPlan, setInitialPlan] = useState(null);
    const [refinedPlan, setRefinedPlan] = useState(null);
    const [planText, setPlanText] = useState('');
    const [error, setError] = useState('');
    const [logs, setLogs] = useState([]);
    const [plots, setPlots] = useState([]);
    const [collapsedStates, setCollapsedStates] = useState({});
    const [execPhase, setExecPhase] = useState('idle');
    const [streamCode, setStreamCode] = useState('');
    const [fixThought, setFixThought] = useState('');
    const [mode, setMode] = useState('instruction');
    const [hypotheses, setHypotheses] = useState([]);
    const [brainstorming, setBrainstorming] = useState(false);
    const [searchParams, setSearchParams] = useSearchParams();
    useEffect(() => {
        const jid = searchParams.get('job_id');
        if (jid) {
            loadJobState(jid);
        }
    }, []); // only run on initial load
    useEffect(() => {
        if (job?.id && searchParams.get('job_id') !== job.id) {
            setSearchParams({ job_id: job.id });
        }
    }, [job?.id, searchParams, setSearchParams]);
    const loadJobState = async (jid) => {
        setLoading(true);
        try {
            const [plan, info, status] = await Promise.all([
                fetchJobPlan(jid).catch(() => null),
                fetchExcelInfo(jid).catch(() => null),
                fetchStatus(jid).catch(() => null)
            ]);
            if (plan && info) {
                setJob({
                    id: jid,
                    success: status?.success,
                    report: status?.report_path
                });
                setTopic(plan.topic || plan.objective || '');
                setExcelInfo(info);
                setExcelPath(info.path || '');
                setExcelDesc(info.user_description || '');
                setInitialPlan(plan);
                setPlanText(JSON.stringify(plan, null, 2));
                // Restore logs and plots if available
                if (status) {
                    setLogs(status.logs || []);
                    setPlots(status.plots || []);
                    if (status.running) {
                        setRunning(true);
                        setExecPhase('execution');
                        setCurrent(2);
                    }
                    else if (status.success) {
                        setExecPhase('report');
                        setCurrent(3);
                    }
                    else if (status.logs && status.logs.length > 0) {
                        // Failed or interrupted
                        setExecPhase('execution');
                        setExecutionFailed(true);
                        setCurrent(2);
                    }
                    else {
                        // Just planned but not executed
                        setCurrent(1);
                    }
                }
                else {
                    setCurrent(1);
                }
                message.success('已恢复任务状态');
            }
            else {
                message.error('无法加载任务信息');
            }
        }
        catch (e) {
            console.error(e);
            message.error('加载任务失败');
        }
        finally {
            setLoading(false);
        }
    };
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
        setLoading(true);
        try {
            const f = file;
            const res = await uploadExcel(f, excelDesc);
            setExcelPath(res.excel_path);
            setExcelInfo(res.excel_info);
            setMd5(res.md5 || '');
            setProfileReused(!!res.profile_reused);
            if (res.job_id) {
                setJob({ id: res.job_id });
            }
            if (res.profile_reused) {
                message.success(`已加载缓存画像 (MD5: ${res.md5?.slice(0, 8)})`);
            }
            else if (res.duplicate) {
                message.info(`检测到相同文件，已复用路径 (MD5: ${res.md5?.slice(0, 8)})`);
            }
            else {
                message.success('Excel上传与分析成功');
            }
            onSuccess && onSuccess(res, new XMLHttpRequest());
        }
        catch (e) {
            message.error(e?.response?.data?.detail || '上传失败');
            setError(e?.response?.data?.detail || '上传失败');
            onError && onError(e);
        }
        finally {
            setLoading(false);
        }
    };
    const [connStatus, setConnStatus] = useState('idle');
    const [controller, setController] = useState(null);
    const appendChunkTypewriter = (t) => {
        if (!t)
            return;
        setPlanText(prev => prev + t);
        // Optional: auto-scroll to bottom
        try {
            const el = document.getElementById('plan-textarea');
            if (el) {
                el.selectionStart = el.value.length;
                el.selectionEnd = el.value.length;
                el.scrollTop = el.scrollHeight;
            }
        }
        catch { }
    };
    const doBrainstorm = async () => {
        if (!job?.id) {
            message.warning('请先上传Excel文件');
            return;
        }
        setBrainstorming(true);
        try {
            const res = await brainstorm(job.id, topic);
            setHypotheses(res.hypotheses || []);
            message.success(`生成了 ${res.hypotheses?.length || 0} 条假设`);
        }
        catch (e) {
            message.error(e.message || '生成假设失败');
        }
        finally {
            setBrainstorming(false);
        }
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
            const res = await streamPlan({ topic, excel_path: excelPath, excel_description: excelDesc, job_id: job?.id, mode }, (t) => {
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
        setExecutionFailed(false);
        setError('');
        setLogs([]);
        setPlots([]);
        setStreamCode('');
        setFixThought('');
        setExecPhase('idle');
        try {
            const ctrl = new AbortController();
            setController(ctrl);
            await streamExecute(job.id, (event) => {
                if (event.type === 'phase') {
                    setExecPhase(event.phase);
                }
                else if (event.type === 'code_chunk') {
                    setStreamCode(prev => prev + event.content);
                }
                else if (event.type === 'exec_result') {
                    setLogs(prev => [...prev, event.log]);
                }
                else if (event.type === 'plots') {
                    setPlots(event.plots);
                }
                else if (event.type === 'llm_fix_chunk') {
                    setFixThought(prev => prev + event.chunk);
                }
                else if (event.type === 'llm_suggestion') {
                    setFixThought('');
                    setLogs(prev => {
                        const newLogs = [...prev];
                        if (newLogs.length > 0) {
                            newLogs[newLogs.length - 1].llm_suggestion = event.suggestion || (newLogs[newLogs.length - 1].llm_suggestion);
                        }
                        return newLogs;
                    });
                }
                else if (event.type === 'report_ready') {
                    setJob(prev => prev ? ({ ...prev, report: event.report_path }) : null);
                }
                else if (event.type === 'success') {
                    setJob(prev => prev ? ({ ...prev, success: true }) : null);
                    message.success('执行成功');
                    setCurrent(3);
                }
                else if (event.type === 'error') {
                    setError(event.error);
                    message.error(event.error);
                    setExecutionFailed(true);
                }
            }, (st) => {
                if (st === 'done' || st === 'error' || st === 'interrupted') {
                    setRunning(false);
                    setLoading(false);
                    setController(null);
                }
            }, ctrl.signal);
        }
        catch (e) {
            const msg = e?.response?.data?.detail || '执行失败';
            setError(msg);
            message.error(msg);
            setExecutionFailed(true);
            setRunning(false);
            setLoading(false);
        }
    };
    return (_jsxs("div", { children: [_jsx(Title, { level: 3, children: "\u65B0\u5EFA\u7814\u7A76" }), _jsx(Card, { children: _jsx(Steps, { current: current, items: steps }) }), current === 0 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u8BF7\u8F93\u5165\u7814\u7A76\u4E3B\u9898\uFF0C\u5E76\u4E0A\u4F20\u6570\u636E\u6587\u4EF6\uFF0C\u4E24\u8005\u5171\u540C\u7528\u4E8E\u751F\u6210\u7814\u7A76\u8BA1\u5212\u3002" }), _jsxs(Form, { layout: "vertical", children: [_jsx(Form.Item, { label: "\u7814\u7A76\u6A21\u5F0F", children: _jsxs(Radio.Group, { value: mode, onChange: e => setMode(e.target.value), children: [_jsx(Radio.Button, { value: "instruction", children: "\u6307\u4EE4\u6A21\u5F0F" }), _jsx(Radio.Button, { value: "discovery", children: "\u53D1\u73B0\u6A21\u5F0F" })] }) }), mode === 'instruction' ? (_jsx(Form.Item, { label: "\u7814\u7A76\u4E3B\u9898", children: _jsx(Input.TextArea, { rows: 3, value: topic, onChange: (e) => setTopic(e.target.value), placeholder: "\u4F8B\u5982\uFF1A\u809D\u764C\u60A3\u8005\u4E94\u5E74\u751F\u5B58\u7387" }) })) : (_jsxs(_Fragment, { children: [_jsx(Form.Item, { label: "\u7814\u7A76\u65B9\u5411\uFF08\u53EF\u9009\uFF09", children: _jsx(Input.TextArea, { rows: 2, value: topic, onChange: (e) => setTopic(e.target.value), placeholder: "\u4F8B\u5982\uFF1A\u5FC3\u8840\u7BA1\u75BE\u75C5\u98CE\u9669\u56E0\u7D20\uFF08\u7559\u7A7A\u5219\u5B8C\u5168\u7531AI\u63A2\u7D22\uFF09" }) }), _jsxs(Form.Item, { children: [_jsx(Button, { type: "dashed", icon: _jsx(BulbOutlined, {}), onClick: doBrainstorm, loading: brainstorming, disabled: !excelInfo, children: "AI \u5934\u8111\u98CE\u66B4\uFF1A\u751F\u6210\u7814\u7A76\u5047\u8BBE" }), !excelInfo && _jsx(Typography.Text, { type: "secondary", style: { marginLeft: 8 }, children: "(\u8BF7\u5148\u4E0A\u4F20Excel)" })] }), hypotheses.length > 0 && (_jsxs("div", { style: { marginBottom: 16, border: '1px solid #f0f0f0', padding: 12, borderRadius: 4, background: '#fafafa' }, children: [_jsx("div", { style: { marginBottom: 8 }, children: _jsx(Typography.Text, { strong: true, children: "\u751F\u6210\u7684\u5047\u8BBE\uFF08\u52FE\u9009\u4EE5\u7EC4\u5408\u4E3A\u4E3B\u9898\uFF09\uFF1A" }) }), _jsx(List, { size: "small", dataSource: hypotheses, renderItem: (item) => (_jsx(List.Item, { children: _jsx(Checkbox, { onChange: (e) => {
                                                            if (e.target.checked) {
                                                                const newTopic = topic ? `${topic}；${item}` : item;
                                                                setTopic(newTopic);
                                                            }
                                                        }, children: item }) })) }), _jsx("div", { style: { marginTop: 8 }, children: _jsx(Button, { type: "link", size: "small", onClick: () => setMode('instruction'), children: "\u5207\u6362\u56DE\u6307\u4EE4\u6A21\u5F0F\u7EE7\u7EED" }) })] }))] })), _jsx(Form.Item, { label: "\u8865\u5145\u8868\u683C\u63CF\u8FF0\uFF08\u53EF\u9009\uFF09", children: _jsx(Input.TextArea, { rows: 3, value: excelDesc, onChange: (e) => setExcelDesc(e.target.value), placeholder: "\u4F8B\u5982\uFF1ASheet1\u4E3A\u60A3\u8005\u57FA\u672C\u4FE1\u606F\uFF0CSheet2\u4E3A\u968F\u8BBF\u8BB0\u5F55..." }) }), _jsx(Form.Item, { label: "\u4E0A\u4F20Excel\u6587\u4EF6", children: _jsxs(Upload.Dragger, { name: "file", customRequest: doUpload, accept: ".xlsx,.xls", maxCount: 1, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u70B9\u51FB\u6216\u62D6\u62FDExcel\u5230\u6B64\u533A\u57DF\u4E0A\u4F20" })] }) }), profileReused && (_jsx("div", { style: { marginBottom: 24 }, children: _jsx(Alert, { message: "\u5DF2\u52A0\u8F7D\u7F13\u5B58\u7684\u753B\u50CF\u4FE1\u606F", description: "\u7CFB\u7EDF\u68C0\u6D4B\u5230\u76F8\u540C\u6587\u4EF6\u5E76\u590D\u7528\u4E86\u5386\u53F2\u5206\u6790\u7ED3\u679C\uFF08\u542B\u8BE6\u7EC6\u753B\u50CF\uFF09\u3002\u5982\u9700\u91CD\u65B0\u5206\u6790\uFF0C\u8BF7\u6E05\u9664\u7F13\u5B58\u3002", type: "success", showIcon: true, action: _jsx(Button, { size: "small", danger: true, onClick: async () => {
                                            if (!md5)
                                                return;
                                            try {
                                                await deleteProfile(md5);
                                                setProfileReused(false);
                                                setExcelInfo(null);
                                                setExcelPath('');
                                                setMd5('');
                                                message.success('缓存已清除，请重新上传文件');
                                            }
                                            catch (e) {
                                                message.error('清除失败');
                                            }
                                        }, children: "\u6E05\u9664\u7F13\u5B58" }) }) })), excelInfo && (_jsx(Collapse, { defaultActiveKey: [], items: [{
                                        key: 'excel-structure',
                                        label: 'Excel 结构信息',
                                        children: (_jsx(JsonTree, { data: excelInfo, defaultCollapsed: true })),
                                    }] })), _jsx(Form.Item, { style: { marginTop: 16 }, children: _jsx(Button, { type: "primary", onClick: next, disabled: !topic || !excelPath, children: "\u4E0B\u4E00\u6B65" }) })] })] })), current === 1 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u8BF7\u751F\u6210\u7814\u7A76\u8BA1\u5212\u3002\u8BA1\u5212\u5C06\u7528\u4E8E\u6307\u5BFC\u4EE3\u7801\u751F\u6210\u4E0E\u6267\u884C\u3002" }), _jsxs(Space, { style: { marginBottom: 12 }, children: [_jsx(Button, { type: "primary", onClick: doPlan, disabled: !excelPath || !topic, children: "\u751F\u6210\u7814\u7A76\u8BA1\u5212" }), (connStatus === 'connecting' || connStatus === 'streaming') && (_jsx(Button, { danger: true, onClick: () => controller && controller.abort(), children: "\u4E2D\u65AD" })), connStatus !== 'idle' && (_jsxs(Typography.Text, { style: { marginLeft: 8 }, children: ["\u72B6\u6001\uFF1A", statusMap[connStatus] || connStatus] }))] }), !!error && (_jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: doPlan, children: "\u91CD\u8BD5\u6B64\u6B65\u9AA4" }) })), _jsx("div", { style: { marginTop: 16 }, children: loading && _jsx(Spin, {}) }), _jsxs(Card, { type: "inner", title: "\u8BA1\u5212\uFF08\u53EF\u7F16\u8F91\uFF09", style: { marginTop: 16 }, children: [_jsx(Input.TextArea, { id: "plan-textarea", rows: 12, value: planText, onChange: (e) => setPlanText(e.target.value) }), _jsxs("div", { style: { marginTop: 12 }, children: [_jsx(Button, { type: "default", onClick: saveEditedPlan, style: { marginRight: 8 }, children: "\u4FDD\u5B58\u8BA1\u5212\u4FEE\u6539" }), _jsx(Button, { onClick: doRefinePlan, type: "primary", children: "\u6839\u636E\u5B57\u6BB5\u7406\u89E3\u751F\u6210\u7EC6\u5316\u8BA1\u5212" }), _jsx(Button, { onClick: () => setCurrent(2), style: { marginLeft: 8 }, children: "\u4E0B\u4E00\u6B65\uFF1A\u751F\u6210\u4E0E\u6267\u884C" })] })] })] })), current === 2 && (_jsxs(Card, { style: { marginTop: 16 }, children: [_jsx(Paragraph, { children: "\u5C06\u57FA\u4E8EExcel\u7ED3\u6784\u4FE1\u606F\u5236\u5B9A\u8BA1\u5212\u5E76\u751F\u6210Python\u4EE3\u7801\uFF0C\u8FD0\u884C\u540E\u751F\u6210\u56FE\u8868\u4E0E\u62A5\u544A\u3002" }), _jsxs(Space, { children: [_jsx(Button, { type: "primary", onClick: runResearch, disabled: !excelPath || !topic, loading: running, children: running ? '正在执行...' : (executionFailed ? '重试执行' : '生成并执行研究') }), _jsx(Button, { onClick: () => setCurrent(1), disabled: running, children: "\u8FD4\u56DE\u4FEE\u6539\u8BA1\u5212" }), executionFailed && _jsx(Typography.Text, { type: "danger", children: "\u6267\u884C\u5931\u8D25\uFF0C\u8BF7\u68C0\u67E5\u4E0B\u65B9\u65E5\u5FD7\u5E76\u91CD\u8BD5" })] }), _jsx("div", { style: { marginTop: 16 }, children: loading && _jsx(Spin, { tip: "\u6B63\u5728\u6267\u884C..." }) }), !!error && (_jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: runResearch, children: "\u91CD\u8BD5\u6B64\u6B65\u9AA4" }) })), (execPhase === 'code_generation' || execPhase === 'opencode_init' || execPhase === 'validation' || (execPhase === 'execution' && !logs.length)) && streamCode && (_jsx(Card, { type: "inner", title: execPhase === 'opencode_init' || execPhase === 'validation' ? "OpenCode 运行进度" : "正在生成代码...", style: { marginTop: 16 }, children: execPhase === 'opencode_init' || execPhase === 'validation' ? (_jsx(StructuredLogViewer, { log: streamCode })) : (_jsx(CodeViewer, { code: streamCode })) })), !!fixThought && (_jsx(Card, { type: "inner", title: "LLM\u6B63\u5728\u601D\u8003\u4FEE\u590D\u65B9\u6848...", style: { marginTop: 16, borderColor: '#1890ff' }, children: _jsx("pre", { className: "log-pre", children: fixThought }) })), !!logs?.length && (_jsx(Card, { type: "inner", title: "\u6267\u884C\u8FDB\u5EA6\uFF08\u5B9E\u65F6\uFF09", style: { marginTop: 16 }, children: logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["\u6B65\u9AA4 ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CodeOutlined, {}), _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.code), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`code-${idx}`, false), children: isCollapsed(`code-${idx}`, false) ? '展开全部' : '收起' })] })] }), _jsx(CodeViewer, { code: l.code, collapsed: isCollapsed(`code-${idx}`, false) })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CheckCircleOutlined, {}), _jsx(Typography.Text, { children: "\u6267\u884C\u7ED3\u679C\uFF08stdout\uFF09" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stdout), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`stdout-${idx}`, true), children: isCollapsed(`stdout-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10, collapsed: isCollapsed(`stdout-${idx}`, true) })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CloseCircleOutlined, {}), _jsx(Typography.Text, { children: "\u9519\u8BEF\u4FE1\u606F\uFF08stderr\uFF09" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stderr), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`stderr-${idx}`, true), children: isCollapsed(`stderr-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10, collapsed: isCollapsed(`stderr-${idx}`, true) })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(BulbOutlined, {}), _jsx(Typography.Text, { children: "LLM\u4FEE\u6539\u5EFA\u8BAE" })] }), _jsxs(Space, { children: [_jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.llm_suggestion), children: "\u590D\u5236" }), _jsx(Button, { type: "link", onClick: () => toggleCollapsed(`suggestion-${idx}`, true), children: isCollapsed(`suggestion-${idx}`, true) ? '展开全部' : '收起' })] })] }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10, collapsed: isCollapsed(`suggestion-${idx}`, true) })] }))] }, idx))) })), !!plots?.length && (_jsx(Card, { type: "inner", title: "\u56FE\u8868\u9884\u89C8\uFF08\u5B9E\u65F6\uFF09", style: { marginTop: 16 }, children: _jsx("div", { style: { display: 'flex', gap: 12, flexWrap: 'wrap' }, children: plots.map((p) => {
                                const src = resolveStaticUrl(`/static/jobs/${job.id}/plots/${p}`);
                                return (_jsxs("div", { style: { width: 260 }, children: [_jsx(Image, { src: src, alt: p, width: 240, height: 180, style: { objectFit: 'contain' } }), _jsx("div", { style: { fontSize: 12, marginTop: 4 }, children: p })] }, p));
                            }) }) }))] })), current === 3 && job && (_jsxs(Card, { style: { marginTop: 16 }, children: [job.success ? (_jsx(Result, { status: "success", title: "\u6267\u884C\u6210\u529F", subTitle: job.report ? `报告已生成` : '执行已完成，请继续生成报告', extra: (_jsxs(Space, { children: [job.report && (_jsx(Link, { to: `/report/${job.id}`, children: _jsx(Button, { type: "primary", children: "\u67E5\u770B\u62A5\u544A" }) })), _jsx(Link, { to: `/compose/${job.id}`, children: _jsx(Button, { type: job.report ? 'default' : 'primary', children: job.report ? '按需修改报告' : '生成报告' }) })] })) })) : (_jsx(Result, { status: "warning", title: "\u6267\u884C\u672A\u6210\u529F", subTitle: "\u8BF7\u67E5\u770B\u65E5\u5FD7\u6216\u91CD\u8BD5" })), !!streamCode && (!logs || logs.length === 0) && (_jsx(Card, { type: "inner", title: "OpenCode \u5B8C\u6574\u6267\u884C\u65E5\u5FD7", style: { marginTop: 16 }, children: _jsx(StructuredLogViewer, { log: streamCode }) })), logs && logs.length > 0 && (_jsx(Card, { type: "inner", title: "\u6267\u884C\u65E5\u5FD7\uFF08\u591A\u8F6E\uFF09", style: { marginTop: 16 }, children: logs.map((l, idx) => (_jsxs(Card, { style: { marginBottom: 12 }, children: [_jsx(Space, { align: "center", style: { marginBottom: 8 }, children: _jsxs(Typography.Text, { strong: true, children: ["Step ", l.step] }) }), l.code && (_jsxs("div", { className: "log-block log-code", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CodeOutlined, {}), _jsx(Typography.Text, { children: "LLM\u751F\u6210\u4EE3\u7801" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.code), children: "\u590D\u5236" })] }), _jsx(CodeViewer, { code: l.code })] })), l.stdout && (_jsxs("div", { className: "log-block log-stdout", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CheckCircleOutlined, {}), _jsx(Typography.Text, { children: "\u6267\u884C\u7ED3\u679C\uFF08stdout\uFF09" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stdout), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.stdout, maxLines: 10 })] })), l.stderr && (_jsxs("div", { className: "log-block log-stderr", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(CloseCircleOutlined, {}), _jsx(Typography.Text, { children: "\u9519\u8BEF\u4FE1\u606F\uFF08stderr\uFF09" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.stderr), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.stderr, maxLines: 10 })] })), l.llm_suggestion && (_jsxs("div", { className: "log-block log-suggestion", children: [_jsxs("div", { className: "log-block__header", children: [_jsxs(Space, { children: [_jsx(BulbOutlined, {}), _jsx(Typography.Text, { children: "LLM\u4FEE\u6539\u5EFA\u8BAE" })] }), _jsx(Button, { type: "link", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(l.llm_suggestion), children: "\u590D\u5236" })] }), _jsx(CollapsiblePre, { text: l.llm_suggestion, maxLines: 10 })] }))] }, idx))) })), !!plots?.length && (_jsxs(Card, { type: "inner", title: "\u56FE\u8868\u9884\u89C8", style: { marginTop: 16 }, children: [_jsx("div", { style: { display: 'flex', gap: 12, flexWrap: 'wrap' }, children: plots.map((p) => {
                                    const src = resolveStaticUrl(`/static/jobs/${job.id}/plots/${p}`);
                                    return (_jsxs("div", { style: { width: 260 }, children: [_jsx(Image, { src: src, alt: p, width: 240, height: 180, style: { objectFit: 'contain' } }), _jsx("div", { style: { fontSize: 12, marginTop: 4 }, children: p })] }, p));
                                }) }), _jsx("div", { style: { marginTop: 12 }, children: _jsx(Button, { onClick: () => runResearch(), type: "primary", children: "\u91CD\u65B0\u6267\u884C\u6B64\u7814\u7A76" }) })] }))] }))] }));
}
