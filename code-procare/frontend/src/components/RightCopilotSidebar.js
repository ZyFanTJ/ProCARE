import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { api } from '../api/client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Button, Collapse, Input, Space, Tag, Typography, Tooltip, Image, App } from 'antd';
import { CloseOutlined, CopyOutlined, PauseCircleOutlined, RobotOutlined, SendOutlined, ThunderboltOutlined, PictureOutlined, DeleteOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { assistantChatStream, fetchAssistantGuide } from '../api/assistant';
import '../assets/copilotSidebar.css';
function resolvePageKey(pathname) {
    if (pathname.startsWith('/dashboard'))
        return 'dashboard';
    if (pathname === '/' || pathname.startsWith('/wizard'))
        return 'wizard';
    if (pathname.startsWith('/compose'))
        return 'report-composer';
    if (pathname.startsWith('/report'))
        return 'report-viewer';
    if (pathname.startsWith('/projects'))
        return 'projects';
    if (pathname.startsWith('/data-manager'))
        return 'data-manager';
    if (pathname.startsWith('/templates'))
        return 'templates';
    if (pathname.startsWith('/settings'))
        return 'settings';
    return 'unknown';
}
function resolveJobId(pathname, search) {
    const m1 = pathname.match(/^\/report\/([^\/]+)/);
    if (m1)
        return m1[1];
    const m2 = pathname.match(/^\/compose\/([^\/]+)/);
    if (m2)
        return m2[1];
    const m3 = pathname.match(/^\/project\/([^\/]+)/);
    if (m3)
        return m3[1];
    if (search) {
        const params = new URLSearchParams(search);
        const jid = params.get('job_id');
        if (jid)
            return jid;
    }
    return undefined;
}
export default function RightCopilotSidebar(props) {
    const { message } = App.useApp();
    const { open, onToggle, width = 420, handleWidth = 56 } = props;
    const location = useLocation();
    const navigate = useNavigate();
    const pageKey = useMemo(() => resolvePageKey(location.pathname), [location.pathname]);
    const jobId = useMemo(() => resolveJobId(location.pathname, location.search), [location.pathname, location.search]);
    const chatRef = useRef(null);
    const [guide, setGuide] = useState('');
    const [loadingGuide, setLoadingGuide] = useState(false);
    const [messages, setMessages] = useState(() => {
        try {
            const raw = localStorage.getItem(`copilot_sidebar_chat_global`);
            return raw ? JSON.parse(raw) : [];
        }
        catch {
            return [];
        }
    });
    const [input, setInput] = useState('');
    const [images, setImages] = useState([]);
    const fileInputRef = useRef(null);
    const [status, setStatus] = useState('idle');
    const [controller, setController] = useState(null);
    const statusRef = useRef(status);
    useEffect(() => { statusRef.current = status; }, [status]);
    const accRef = useRef('');
    const pendingRef = useRef('');
    const actionExecutedRef = useRef(false);
    const typingTimerRef = useRef(null);
    useEffect(() => {
        // try { const raw = localStorage.getItem(`copilot_sidebar_chat_${pageKey}`); setMessages(raw ? JSON.parse(raw) : []) } catch { setMessages([]) }
    }, [pageKey]);
    useEffect(() => {
        localStorage.setItem(`copilot_sidebar_chat_global`, JSON.stringify(messages));
        try {
            const el = chatRef.current;
            if (el)
                el.scrollTop = el.scrollHeight;
        }
        catch { }
    }, [messages]);
    useEffect(() => {
        if (!open)
            return;
        setLoadingGuide(true);
        fetchAssistantGuide(pageKey).then((r) => setGuide(r.text || '')).catch(() => setGuide('')).finally(() => setLoadingGuide(false));
    }, [open, pageKey]);
    // Polling for job status to provide proactive notifications
    const lastStatusRef = useRef(null);
    useEffect(() => {
        if (!jobId || !open)
            return;
        let isMounted = true;
        const poll = async () => {
            try {
                const res = await api.get(`/status/${jobId}`);
                const st = res.data;
                const last = lastStatusRef.current;
                if (last) {
                    // Check for completion
                    if (last.running && !st.running) {
                        const msg = st.success ? '✅ Execution finished successfully!' : '❌ Execution failed.';
                        setMessages(prev => [...prev, { role: 'assistant', content: `${msg} You can check the results now.` }]);
                    }
                    // Check for report ready
                    if (!last.report_ready && st.report_ready) {
                        setMessages(prev => [...prev, { role: 'assistant', content: '📊 Report is ready! Click the Report Viewer to see it.' }]);
                    }
                    // Check for step increment
                    if (st.running && st.current_step > last.current_step) {
                        setMessages(prev => [...prev, { role: 'assistant', content: `✅ Step ${last.current_step + 1} completed. Proceeding to step ${st.current_step + 1}...` }]);
                    }
                }
                lastStatusRef.current = st;
            }
            catch { }
            if (isMounted)
                setTimeout(poll, 3000);
        };
        poll();
        return () => { isMounted = false; };
    }, [jobId, open]);
    const abort = () => { if (controller)
        controller.abort(); };
    const resetChat = () => { setMessages([]); localStorage.removeItem(`copilot_sidebar_chat_global`); };
    const copyText = async (text) => { try {
        await navigator.clipboard.writeText(text || '');
        message.success('已复制');
    }
    catch { } };
    const handleFileSelect = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            Array.from(e.target.files).forEach(file => {
                const reader = new FileReader();
                reader.onload = (evt) => {
                    if (evt.target?.result) {
                        setImages(prev => [...prev, evt.target.result]);
                    }
                };
                reader.readAsDataURL(file);
            });
            e.target.value = '';
        }
    };
    const handlePaste = (e) => {
        const items = e.clipboardData.items;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                e.preventDefault();
                const blob = items[i].getAsFile();
                if (blob) {
                    const reader = new FileReader();
                    reader.onload = (evt) => {
                        if (evt.target?.result) {
                            setImages(prev => [...prev, evt.target.result]);
                        }
                    };
                    reader.readAsDataURL(blob);
                }
            }
        }
    };
    const removeImage = (index) => {
        setImages(prev => prev.filter((_, i) => i !== index));
    };
    const send = async () => {
        const content = input.trim();
        if ((!content && images.length === 0) || status === 'streaming')
            return;
        const next = [...messages, { role: 'user', content, images: images.length > 0 ? images : undefined }];
        setMessages(next);
        setInput('');
        setImages([]);
        const ctl = new AbortController();
        setController(ctl);
        setStatus('connecting');
        setMessages((prev) => [...prev, Object.assign({ role: 'assistant', content: '' }, { __streaming: true })]);
        accRef.current = '';
        pendingRef.current = '';
        actionExecutedRef.current = false;
        // Try to get page context
        let context = undefined;
        try {
            const rawCtx = localStorage.getItem('copilot_active_context');
            if (rawCtx) {
                context = JSON.parse(rawCtx);
            }
        }
        catch { }
        await assistantChatStream({ page_key: pageKey, pathname: location.pathname, job_id: jobId, messages: next, context }, (t) => {
            setStatus('streaming');
            pendingRef.current += (t || '');
            if (!typingTimerRef.current) {
                typingTimerRef.current = window.setInterval(() => {
                    const step = Math.max(2, Math.min(24, Math.ceil(pendingRef.current.length / 40)));
                    if (pendingRef.current.length > 0) {
                        const emit = pendingRef.current.slice(0, step);
                        pendingRef.current = pendingRef.current.slice(step);
                        accRef.current = accRef.current + emit;
                        // Parse and execute frontend actions
                        let displayContent = accRef.current;
                        // 1. Frontend Actions
                        const actionRegex = /<frontend_action\s+type="([^"]+)"\s+path="([^"]+)"\s*\/>/g;
                        let match;
                        while ((match = actionRegex.exec(accRef.current)) !== null) {
                            if (!actionExecutedRef.current) {
                                const [fullTag, type, path] = match;
                                if (type === 'navigate') {
                                    actionExecutedRef.current = true; // Only execute once per stream
                                    navigate(path);
                                    message.success('正在跳转...');
                                }
                            }
                            displayContent = displayContent.replace(match[0], '');
                        }
                        // 2. Server Actions
                        const serverActionRegex = /<server_action\s+type="([^"]+)"\s+job_id="([^"]+)">([\s\S]*?)<\/server_action>/g;
                        let smatch;
                        while ((smatch = serverActionRegex.exec(accRef.current)) !== null) {
                            if (!actionExecutedRef.current) {
                                const [fullTag, type, jid, payloadStr] = smatch;
                                if (type === 'update_plan') {
                                    actionExecutedRef.current = true;
                                    try {
                                        const payload = JSON.parse(payloadStr);
                                        api.post('/plan/update', { job_id: jid, plan: payload.plan })
                                            .then(() => message.success('Plan updated successfully'))
                                            .catch(() => message.error('Failed to update plan'));
                                    }
                                    catch (e) {
                                        console.error(e);
                                    }
                                }
                            }
                            displayContent = displayContent.replace(smatch[0], '');
                        }
                        const last = { role: 'assistant', content: displayContent };
                        setMessages((prev) => {
                            const arr = [...prev];
                            const idx = [...arr].reverse().findIndex((m) => m.__streaming);
                            const realIdx = idx >= 0 ? arr.length - 1 - idx : -1;
                            if (realIdx >= 0) {
                                arr[realIdx] = last;
                                arr[realIdx].__streaming = true;
                                return arr;
                            }
                            return [...arr, Object.assign(last, { __streaming: true })];
                        });
                    }
                    if (pendingRef.current.length === 0 && statusRef.current !== 'streaming') {
                        if (typingTimerRef.current) {
                            clearInterval(typingTimerRef.current);
                            typingTimerRef.current = null;
                        }
                        // Final cleanup of tags
                        setMessages((prev) => prev.map((m) => {
                            const content = m.content || '';
                            const clean = content.replace(/<frontend_action\s+[^>]*\/>/g, '').replace(/<server_action\s+[^>]*>[\s\S]*?<\/server_action>/g, '');
                            return { role: m.role, content: clean };
                        }));
                    }
                }, 20);
            }
        }, (st) => setStatus(st), ctl.signal).catch(() => setStatus('error'));
        setController(null);
        if (!typingTimerRef.current) {
            // Final cleanup in case of fast completion
            setMessages((prev) => prev.map((m) => {
                const content = m.content || '';
                const clean = content.replace(/<frontend_action\s+[^>]*\/>/g, '').replace(/<server_action\s+[^>]*>[\s\S]*?<\/server_action>/g, '');
                return { role: m.role, content: clean };
            }));
        }
    };
    const quickPrompts = [
        '我应该如何新建一个研究项目？',
        '我现在所在页面能做什么？',
        '如何上传数据并生成报告？',
        '如何解释当前页面的字段/按钮含义？',
    ];
    return (_jsxs("div", { className: `copilot-sider ${open ? 'copilot-sider--open' : 'copilot-sider--collapsed'}`, style: {
            ['--copilot-sider-width']: `${width}px`,
            ['--copilot-handle-width']: `${handleWidth}px`,
        }, "aria-label": "Copilot Sidebar", children: [!open && (_jsxs("div", { className: "copilot-collapsed-strip", onClick: onToggle, title: "\u5C55\u5F00 Copilot", children: [_jsx("div", { className: "copilot-collapsed-icon", children: _jsx(RobotOutlined, { style: { fontSize: 24, color: 'var(--copilot-accent)' } }) }), _jsx("div", { className: "copilot-collapsed-text", children: "AI ASSISTANT" })] })), _jsxs("div", { className: "copilot-sider__inner", style: { display: open ? 'flex' : 'none' }, children: [_jsxs("div", { className: "copilot-sider__top", children: [_jsxs("div", { className: "copilot-sider__title", children: [_jsxs(Space, { size: 8, children: [_jsx("span", { className: "copilot-sider__badge", children: _jsx(ThunderboltOutlined, {}) }), _jsx("span", { children: "Copilot" })] }), _jsxs(Space, { size: 6, children: [status !== 'idle' && _jsx(Tag, { className: "copilot-status", color: status === 'error' ? 'red' : (status === 'done' ? 'green' : 'gold'), children: status }), _jsx(Tooltip, { title: "\u6E05\u7A7A\u5BF9\u8BDD", children: _jsx(Button, { size: "small", type: "text", icon: _jsx(DeleteOutlined, {}), onClick: resetChat }) }), _jsx(Button, { size: "small", type: "text", icon: _jsx(CloseOutlined, {}), onClick: onToggle })] })] }), _jsx("div", { className: "copilot-sider__meta", children: _jsxs(Space, { size: 6, wrap: true, children: [_jsx(Tag, { color: "cyan", children: pageKey }), !!jobId && _jsxs(Tag, { color: "blue", children: ["job: ", jobId] }), _jsx(Tag, { className: "copilot-path", color: "default", children: location.pathname })] }) }), _jsx(Collapse, { size: "small", bordered: false, defaultActiveKey: guide ? ['guide'] : [], className: "copilot-collapse", items: [
                                    {
                                        key: 'guide',
                                        label: '本页指南',
                                        children: (_jsxs("div", { children: [loadingGuide ? (_jsx(Typography.Text, { type: "secondary", children: "\u52A0\u8F7D\u4E2D\u2026" })) : (_jsx(Typography.Paragraph, { className: "copilot-guide", children: guide || '还没有针对本页的指南。你可以直接提问：如何使用本页功能、每个按钮的含义、推荐流程等。' })), _jsx("div", { className: "copilot-quick", children: quickPrompts.map((t) => (_jsx("button", { className: "copilot-chip", onClick: () => setInput(t), children: t }, t))) })] })),
                                    }
                                ] })] }), _jsxs("div", { className: "copilot-sider__chat", ref: chatRef, children: [messages.length === 0 && (_jsxs("div", { className: "copilot-empty", children: [_jsxs("div", { className: "copilot-empty__logo", children: [_jsx("div", { className: "copilot-logo-pulse" }), _jsx(RobotOutlined, { style: { fontSize: 32, color: '#fff' } })] }), _jsx("div", { className: "copilot-empty__title", children: "Research Copilot" }), _jsx("div", { className: "copilot-empty__desc", children: "\u6211\u662F\u60A8\u7684\u79D1\u7814\u52A9\u624B\u3002\u6211\u53EF\u4EE5\u534F\u52A9\u60A8\u5206\u6790\u6570\u636E\u3001\u64B0\u5199\u62A5\u544A\u6216\u89E3\u7B54\u9879\u76EE\u7591\u95EE\u3002" }), _jsx("div", { className: "copilot-suggestions", children: quickPrompts.map((t, i) => (_jsxs("div", { className: "copilot-suggestion-card", onClick: () => setInput(t), children: [_jsx("div", { className: "copilot-suggestion-icon", children: _jsx(ThunderboltOutlined, {}) }), _jsx("div", { className: "copilot-suggestion-text", children: t })] }, i))) })] })), messages.map((m, i) => (_jsxs("div", { className: `copilot-row ${m.role === 'user' ? 'copilot-row--user' : 'copilot-row--assistant'}`, children: [m.role === 'assistant' && (_jsx("div", { className: "copilot-avatar-container", children: _jsx(Avatar, { size: 32, icon: _jsx(RobotOutlined, {}), className: "copilot-avatar" }) })), _jsxs("div", { className: `copilot-msg ${m.role === 'user' ? 'copilot-msg--user' : 'copilot-msg--assistant'}`, children: [m.role === 'assistant' && _jsx("div", { className: "copilot-msg__header", children: "AI Assistant" }), _jsxs("div", { className: "copilot-msg__content", children: [_jsx(ReactMarkdown, { children: m.content }), m.images && m.images.length > 0 && (_jsx("div", { style: { marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }, children: m.images.map((img, idx) => (_jsx(Image, { src: img, width: 100, style: { borderRadius: 4, objectFit: 'cover' } }, idx))) }))] }), m.role === 'assistant' && (_jsx("div", { className: "copilot-msg__actions", children: _jsx(Tooltip, { title: "\u590D\u5236\u5185\u5BB9", children: _jsx(Button, { size: "small", type: "text", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(m.content) }) }) }))] })] }, i))), status === 'streaming' || status === 'connecting' ? (_jsxs("div", { className: "copilot-row copilot-row--assistant", children: [_jsx("div", { className: "copilot-avatar-container", children: _jsx(Avatar, { size: 32, icon: _jsx(RobotOutlined, {}), className: "copilot-avatar copilot-avatar--thinking" }) }), _jsx("div", { className: "copilot-msg copilot-msg--assistant copilot-msg--thinking", children: _jsxs("div", { className: "typing-indicator", children: [_jsx("span", {}), _jsx("span", {}), _jsx("span", {})] }) })] })) : null] }), _jsxs("div", { className: "copilot-sider__input", children: [_jsxs("div", { className: "copilot-input-container", children: [images.length > 0 && (_jsx("div", { className: "copilot-image-preview", children: images.map((img, i) => (_jsxs("div", { className: "copilot-image-item", children: [_jsx(Image, { src: img, width: 48, height: 48, style: { objectFit: 'cover' }, preview: false }), _jsx("div", { className: "copilot-image-remove", onClick: () => removeImage(i), children: _jsx(CloseOutlined, {}) })] }, i))) })), _jsxs("div", { className: "copilot-input-wrapper", children: [_jsx(Input.TextArea, { rows: 1, value: input, onChange: (e) => setInput(e.target.value), onPaste: handlePaste, placeholder: "\u8F93\u5165\u6307\u4EE4\u6216\u63D0\u95EE...", autoSize: { minRows: 1, maxRows: 4 }, onPressEnter: (e) => { if (!e.shiftKey) {
                                                    e.preventDefault();
                                                    send();
                                                } }, className: "copilot-textarea" }), _jsxs("div", { className: "copilot-input-actions", children: [_jsx("input", { type: "file", accept: "image/*", multiple: true, ref: fileInputRef, style: { display: 'none' }, onChange: handleFileSelect }), _jsx(Tooltip, { title: "\u4E0A\u4F20\u56FE\u7247", children: _jsx(Button, { type: "text", shape: "circle", icon: _jsx(PictureOutlined, {}), onClick: () => fileInputRef.current?.click() }) }), _jsx(Button, { type: "primary", shape: "circle", icon: status === 'connecting' || status === 'streaming' ? _jsx(PauseCircleOutlined, {}) : _jsx(SendOutlined, {}), onClick: status === 'connecting' || status === 'streaming' ? abort : send, disabled: (!input.trim() && images.length === 0) && status !== 'streaming' && status !== 'connecting', className: "copilot-send-btn" })] })] })] }), _jsx("div", { className: "copilot-footer-text", children: "AI \u751F\u6210\u5185\u5BB9\u4EC5\u4F9B\u53C2\u8003\uFF0C\u8BF7\u6838\u5B9E\u91CD\u8981\u4FE1\u606F\u3002" })] })] })] }));
}
