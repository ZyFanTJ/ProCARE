import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Checkbox, Input, Button, Space, message, List, Tag, Progress } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { composeReport, fetchSectionsMeta, composeReportAsync, fetchReportStatus, fetchReportSections, generateSection, saveReport } from '../api/research';
export default function ReportComposer() {
    const { jobId } = useParams();
    const [options, setOptions] = useState([]);
    const [selected, setSelected] = useState([]);
    const [order, setOrder] = useState([]);
    const [overrides, setOverrides] = useState({});
    const [md, setMd] = useState('');
    const [mdSections, setMdSections] = useState([]);
    const [collapsed, setCollapsed] = useState(new Set());
    const [liveSectionContent, setLiveSectionContent] = useState({});
    const [draggingId, setDraggingId] = useState(null);
    const [loading, setLoading] = useState(false);
    const [running, setRunning] = useState(false);
    const [progress, setProgress] = useState(0);
    const [currentStep, setCurrentStep] = useState('');
    const [existing, setExisting] = useState(new Set());
    const [useExisting, setUseExisting] = useState(true);
    const [existingList, setExistingList] = useState([]);
    const [generating, setGenerating] = useState(new Set());
    useEffect(() => {
        fetchSectionsMeta().then((r) => {
            const secs = r.sections || [];
            setOptions(secs);
            const defaults = secs.filter((s) => s.default).map((s) => s.id);
            setSelected(defaults);
            setOrder(defaults);
        }).catch(() => { });
        if (jobId) {
            fetchReportSections(jobId).then((r) => {
                const secs = (r.sections || []);
                setExisting(new Set(secs.map((x) => x.id)));
                setExistingList(secs);
                if (secs.length) {
                    const ids = secs.map((x) => x.id);
                    setSelected(ids);
                    setOrder(ids);
                }
            }).catch(() => { });
        }
    }, []);
    const onGenerate = async (save) => {
        if (!jobId)
            return;
        setLoading(true);
        try {
            const { content, saved } = await composeReport(jobId, order.filter((id) => selected.includes(id)), overrides, !!save, useExisting);
            setMd(content || '');
            if (saved)
                message.success('报告已保存');
            else
                message.success('已生成预览');
        }
        catch (e) {
            message.error('生成失败');
        }
        finally {
            setLoading(false);
        }
    };
    const generateOne = async (sid) => {
        if (!jobId)
            return;
        setGenerating((prev) => { const n = new Set(prev); n.add(sid); return n; });
        try {
            const baseApi = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
            const url = `${baseApi}/generate_section_stream`;
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
                body: JSON.stringify({ job_id: jobId, section_id: sid, ...(overrides[sid] || {}) }),
            });
            if (!resp.ok || !resp.body) {
                message.error('章节生成失败');
                setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n; });
                return;
            }
            message.success(`${sid} 开始流式生成`);
            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let acc = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done)
                    break;
                const chunk = decoder.decode(value);
                acc += chunk.replace(/JOB_ID:[^\n]*\n?/, '');
                setLiveSectionContent((prev) => ({ ...prev, [sid]: acc }));
            }
            // 流式结束后，刷新列表并静默重新组装
            try {
                const r = await fetchReportSections(jobId);
                const secs = (r.sections || []);
                setExisting(new Set(secs.map((x) => x.id)));
                setExistingList(secs);
            }
            catch { }
            await assemblePreviewClient(true);
            message.success(`${sid} 流式生成完成`);
            setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n; });
        }
        catch {
            message.error('章节生成失败');
            setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n; });
        }
    };
    const streamRenderSection = async (sid, full) => {
        return new Promise((resolve) => {
            const total = full.length;
            let i = 0;
            const step = Math.max(10, Math.floor(total / 200)); // 约200步完成
            const interval = 20;
            const timer = setInterval(() => {
                i = Math.min(total, i + step);
                setLiveSectionContent((prev) => ({ ...prev, [sid]: full.slice(0, i) }));
                if (i >= total) {
                    clearInterval(timer);
                    resolve();
                }
            }, interval);
        });
    };
    const assemblePreviewClient = async (silent) => {
        if (!jobId)
            return;
        const selectedIds = order.filter((id) => selected.includes(id));
        const pathById = {};
        existingList.forEach((x) => { pathById[x.id] = x.path; });
        const contents = [];
        const sectionBlocks = [];
        for (const sid of selectedIds) {
            let content = '';
            const path = pathById[sid];
            if (useExisting && path) {
                try {
                    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                    const prefix = baseApi ? baseApi.replace(/\/api$/, '') : '';
                    const url = `${prefix}/static/jobs/${jobId}/${path}`;
                    const resp = await fetch(url);
                    if (resp.ok)
                        content = await resp.text();
                }
                catch { }
            }
            if (content)
                contents.push(content);
            if (content) {
                const secMeta = options.find((o) => o.id === sid);
                sectionBlocks.push({ id: sid, title: secMeta?.title || sid, content });
            }
        }
        setMd(contents.join('\n'));
        setMdSections(sectionBlocks);
        if (!silent)
            message.success('已在前端完成组装预览');
    };
    const composeSectionLive = async (jid, sid, ov) => {
        const res = await generateSection(jid, sid, ov);
        return res.content || '';
    };
    const exportReport = async () => {
        if (!jobId)
            return;
        const parts = mdSections.length ? mdSections.map((b) => b.content) : [md];
        const content = parts.join('\n');
        try {
            const r = await saveReport(jobId, content);
            if (r.ok)
                message.success('已保存到job目录: report.md');
            else
                message.error('保存失败');
        }
        catch {
            message.error('保存失败');
        }
    };
    const updateOverride = (sid, field, v) => {
        setOverrides((prev) => ({ ...prev, [sid]: { ...(prev[sid] || {}), [field]: v } }));
    };
    const toggle = (ids) => {
        const prev = new Set(selected);
        const next = new Set(ids);
        setSelected(Array.from(next));
        setOrder((o) => {
            const base = o.filter((id) => next.has(id));
            const appended = ids.filter((id) => !base.includes(id));
            return [...base, ...appended];
        });
        // 选择变更后，静默重新组装预览
        assemblePreviewClient(true);
    };
    const move = (id, dir) => {
        setOrder((prev) => {
            const idx = prev.indexOf(id);
            if (idx < 0)
                return prev;
            const arr = [...prev];
            const sw = dir === 'up' ? idx - 1 : idx + 1;
            if (sw < 0 || sw >= arr.length)
                return prev;
            const t = arr[sw];
            arr[sw] = arr[idx];
            arr[idx] = t;
            // 移动完成后触发静默预览
            setTimeout(() => assemblePreviewClient(true), 0);
            return arr;
        });
    };
    const onDragStart = (id) => setDraggingId(id);
    const onDragOver = (e) => { e.preventDefault(); };
    const onDrop = (targetId) => {
        if (!draggingId || draggingId === targetId)
            return;
        setOrder((prev) => {
            const arr = prev.filter((x) => x !== draggingId);
            const idx = arr.indexOf(targetId);
            const left = arr.slice(0, idx);
            const right = arr.slice(idx);
            const next = [...left, draggingId, ...right];
            return next;
        });
        setDraggingId(null);
    };
    // 监听顺序变化，实时静默组装预览，确保首次拖动立即生效
    useEffect(() => {
        assemblePreviewClient(true);
    }, [order]);
    const startAsync = async () => {
        if (!jobId)
            return;
        setRunning(true);
        setProgress(0);
        setCurrentStep('');
        try {
            const started = await composeReportAsync(jobId, order.filter((id) => selected.includes(id)), overrides, useExisting);
            if (started.started) {
                const timer = setInterval(async () => {
                    try {
                        const st = await fetchReportStatus(jobId);
                        setProgress(st.progress || 0);
                        setCurrentStep(st.step || '');
                        if (st.state === 'running') {
                            await assemblePreviewClient(true);
                        }
                        else {
                            clearInterval(timer);
                            setRunning(false);
                            if (st.state === 'done')
                                message.success('组合完成');
                        }
                    }
                    catch {
                        clearInterval(timer);
                        setRunning(false);
                    }
                }, 1000);
            }
        }
        catch {
            setRunning(false);
            message.error('后台组合启动失败');
        }
    };
    return (_jsxs("div", { style: { display: 'grid', gridTemplateColumns: '380px 1fr', gap: 16 }, children: [_jsx(Card, { title: `交互生成报告 (${jobId})`, style: { height: 'calc(100vh - 160px)', overflow: 'auto' }, children: _jsxs(Space, { direction: "vertical", size: 12, style: { width: '100%' }, children: [_jsx(Checkbox.Group, { options: options.map((o) => ({ label: `${o.title}${o.category ? '（' + o.category + '）' : ''}`, value: o.id })), value: selected, onChange: (v) => toggle(v) }), _jsx(List, { dataSource: order.filter((id) => selected.includes(id)), renderItem: (id, i) => {
                                const sec = options.find((o) => o.id === id);
                                return (_jsx(List.Item, { draggable: true, onDragStart: () => onDragStart(id), onDragOver: onDragOver, onDrop: () => onDrop(id), children: _jsxs(Space, { style: { width: '100%', justifyContent: 'space-between' }, children: [_jsxs(Space, { children: [_jsx(Tag, { color: "green", children: i + 1 }), _jsx("span", { children: sec?.title || id }), existing.has(id) && _jsx(Tag, { color: "geekblue", children: "\u5DF2\u6709" })] }), _jsxs(Space, { children: [_jsx(Button, { size: "small", onClick: () => move(id, 'up'), children: "\u4E0A\u79FB" }), _jsx(Button, { size: "small", onClick: () => move(id, 'down'), children: "\u4E0B\u79FB" })] })] }) }));
                            } }), order.filter((id) => selected.includes(id)).map((sid) => {
                            const sec = options.find((o) => o.id === sid);
                            return (_jsx(Card, { size: "small", title: sec?.title || sid, extra: _jsx(Button, { size: "small", onClick: () => generateOne(sid), disabled: generating.has(sid), loading: generating.has(sid), children: "\u751F\u6210\u8BE5\u7AE0\u8282" }), children: _jsxs(Space, { direction: "vertical", style: { width: '100%' }, children: [_jsx(Input.TextArea, { rows: 3, placeholder: "\u4EBA\u5DE5\u8865\u5145", value: overrides[sid]?.human_note || '', onChange: (e) => updateOverride(sid, 'human_note', e.target.value) }), _jsx(Input.TextArea, { rows: 3, placeholder: "\u6307\u5BFC\u5EFA\u8BAE\uFF08\u5C06\u5F71\u54CD\u751F\u6210\u98CE\u683C\u4E0E\u91CD\u70B9\uFF09", value: overrides[sid]?.guidelines || '', onChange: (e) => updateOverride(sid, 'guidelines', e.target.value) })] }) }, sid));
                        }), _jsxs(Space, { children: [_jsx(Button, { type: "primary", onClick: () => assemblePreviewClient(false), children: "\u5237\u65B0\u6E32\u67D3" }), _jsx(Button, { onClick: () => exportReport(), children: "\u5BFC\u51FA\u62A5\u544A" })] })] }) }), _jsxs(Card, { title: "\u9884\u89C8", style: { height: 'calc(100vh - 160px)', overflow: 'auto' }, children: [_jsxs(Space, { style: { marginBottom: 12 }, children: [_jsx(Progress, { percent: progress, status: running ? 'active' : (progress >= 100 ? 'success' : 'normal') }), currentStep && _jsx(Tag, { color: "blue", children: currentStep }), _jsx(Button, { onClick: startAsync, disabled: running, children: "\u540E\u53F0\u7EC4\u5408" })] }), _jsx("div", { style: { display: 'flex', flexDirection: 'column', gap: 16 }, children: mdSections.length ? mdSections.map((blk) => (_jsxs("div", { style: { border: '1px solid #1d39c4', boxShadow: '0 2px 10px rgba(29,57,196,0.08)', borderRadius: 10, padding: 12, background: '#fff' }, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }, children: [_jsx("div", { style: { fontWeight: 600, fontSize: 16, color: '#1d39c4' }, children: blk.title }), _jsxs(Space, { children: [_jsx(Button, { size: "small", onClick: () => setCollapsed((prev) => {
                                                        const n = new Set(prev);
                                                        if (n.has(blk.id))
                                                            n.delete(blk.id);
                                                        else
                                                            n.add(blk.id);
                                                        return n;
                                                    }), children: collapsed.has(blk.id) ? '展开' : '折叠' }), _jsx(Button, { size: "small", type: "primary", onClick: () => generateOne(blk.id), disabled: generating.has(blk.id), loading: generating.has(blk.id), children: "\u91CD\u65B0\u751F\u6210" })] })] }), !collapsed.has(blk.id) && (_jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], components: {
                                        img: ({ node, ...props }) => {
                                            const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                                            const prefix = baseApi ? baseApi.replace(/\/api$/, '') : '';
                                            const src = (props.src || '');
                                            const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src;
                                            return (_jsx("img", { ...props, src: finalSrc, style: { maxWidth: '75%', height: 'auto', display: 'block', margin: '12px 0', objectFit: 'contain' }, crossOrigin: "anonymous" }));
                                        },
                                        pre: ({ node, ...props }) => (_jsx("pre", { ...props, style: { overflowX: 'auto', background: '#fafafa', padding: 8, borderRadius: 6 } })),
                                        code: ({ node, className, children, ...props }) => (_jsx("code", { ...props, style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, className: className, children: children })),
                                        table: ({ node, ...props }) => (_jsx("div", { style: { overflowX: 'auto' }, children: _jsx("table", { ...props, style: { width: '100%', borderCollapse: 'collapse' } }) })),
                                        th: ({ node, ...props }) => _jsx("th", { style: { border: '1px solid #ddd', padding: '6px 10px', background: '#fafafa' }, ...props }),
                                        td: ({ node, ...props }) => _jsx("td", { style: { border: '1px solid #ddd', padding: '6px 10px' }, ...props }),
                                        a: ({ node, ...props }) => _jsx("a", { target: "_blank", rel: "noreferrer", ...props }),
                                    }, children: liveSectionContent[blk.id] ?? blk.content }))] }, blk.id))) : (_jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], components: {
                                img: ({ node, ...props }) => {
                                    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                                    const prefix = baseApi ? baseApi.replace(/\/api$/, '') : '';
                                    const src = (props.src || '');
                                    const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src;
                                    return _jsx("img", { ...props, src: finalSrc, style: { maxWidth: '100%', height: 'auto', display: 'block', margin: '12px 0' }, crossOrigin: "anonymous" });
                                },
                                pre: ({ node, ...props }) => (_jsx("pre", { ...props, style: { overflowX: 'auto', background: '#fafafa', padding: 8, borderRadius: 6 } })),
                                code: ({ node, className, children, ...props }) => (_jsx("code", { ...props, style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word' }, className: className, children: children })),
                                table: ({ node, ...props }) => (_jsx("div", { style: { overflowX: 'auto' }, children: _jsx("table", { ...props, style: { width: '100%', borderCollapse: 'collapse' } }) })),
                                th: ({ node, ...props }) => _jsx("th", { style: { border: '1px solid #ddd', padding: '6px 10px', background: '#fafafa' }, ...props }),
                                td: ({ node, ...props }) => _jsx("td", { style: { border: '1px solid #ddd', padding: '6px 10px' }, ...props }),
                                a: ({ node, ...props }) => _jsx("a", { target: "_blank", rel: "noreferrer", ...props }),
                            }, children: md })) })] })] }));
}
