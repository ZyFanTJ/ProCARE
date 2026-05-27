import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, Button, Input, Space, Tag, Typography, Spin, Avatar } from 'antd';
import { RobotOutlined, CloseOutlined, SendOutlined, PauseCircleOutlined, ReloadOutlined, UserOutlined, CopyOutlined, PictureOutlined } from '@ant-design/icons';
import { useLocation } from 'react-router-dom';
import { fetchAssistantGuide, assistantChatStream } from '../api/assistant';
import ReactMarkdown from 'react-markdown';
import '../assets/copilot.css';
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
    if (pathname.startsWith('/files'))
        return 'files';
    if (pathname.startsWith('/templates'))
        return 'templates';
    if (pathname.startsWith('/settings'))
        return 'settings';
    return 'unknown';
}
function resolveJobId(pathname) {
    const m1 = pathname.match(/^\/report\/([^\/]+)/);
    if (m1)
        return m1[1];
    const m2 = pathname.match(/^\/compose\/([^\/]+)/);
    if (m2)
        return m2[1];
    return undefined;
}
export default function CoPilot() {
    const location = useLocation();
    const pageKey = useMemo(() => resolvePageKey(location.pathname), [location.pathname]);
    const jobId = useMemo(() => resolveJobId(location.pathname), [location.pathname]);
    const [open, setOpen] = useState(() => {
        try {
            const s = localStorage.getItem('copilot_open');
            return s ? JSON.parse(s) : true;
        }
        catch {
            return true;
        }
    });
    const [pos, setPos] = useState(() => {
        try {
            const raw = localStorage.getItem('copilot_pos');
            if (raw)
                return JSON.parse(raw);
        }
        catch { }
        return { x: window.innerWidth - 380 - 16, y: Math.max(64, Math.floor(window.innerHeight * 0.3)) };
    });
    const [dragging, setDragging] = useState(false);
    const dragRef = useRef(null);
    const dragKindRef = useRef(null);
    const dragStartRef = useRef(null);
    const didDragRef = useRef(false);
    const panelRef = useRef(null);
    const chatRef = useRef(null);
    const [fabDocked, setFabDocked] = useState(() => {
        try {
            const s = localStorage.getItem('copilot_fab_docked');
            return s ? JSON.parse(s) : true;
        }
        catch {
            return true;
        }
    });
    const [guide, setGuide] = useState('');
    const [loadingGuide, setLoadingGuide] = useState(false);
    const [messages, setMessages] = useState(() => {
        try {
            const raw = localStorage.getItem(`copilot_chat_${pageKey}`);
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
    const typingTimerRef = useRef(null);
    useEffect(() => {
        localStorage.setItem('copilot_open', JSON.stringify(open));
    }, [open]);
    useEffect(() => {
        localStorage.setItem('copilot_pos', JSON.stringify(pos));
    }, [pos]);
    useEffect(() => {
        localStorage.setItem('copilot_fab_docked', JSON.stringify(fabDocked));
    }, [fabDocked]);
    useEffect(() => {
        try {
            const raw = localStorage.getItem(`copilot_chat_${pageKey}`);
            setMessages(raw ? JSON.parse(raw) : []);
        }
        catch {
            setMessages([]);
        }
    }, [pageKey]);
    useEffect(() => {
        localStorage.setItem(`copilot_chat_${pageKey}`, JSON.stringify(messages));
        // 滚动到底部
        try {
            const el = chatRef.current;
            if (el)
                el.scrollTop = el.scrollHeight;
        }
        catch { }
    }, [messages, pageKey]);
    useEffect(() => {
        if (!open)
            return;
        setLoadingGuide(true);
        fetchAssistantGuide(pageKey).then((r) => setGuide(r.text || '')).catch(() => setGuide('')).finally(() => setLoadingGuide(false));
    }, [open, pageKey]);
    useEffect(() => {
        const onMove = (e) => {
            if (!dragging || !dragRef.current)
                return;
            const { ox, oy, w, h } = dragRef.current;
            if (dragStartRef.current) {
                const dx = Math.abs(e.clientX - dragStartRef.current.sx);
                const dy = Math.abs(e.clientY - dragStartRef.current.sy);
                if (!didDragRef.current && (dx > 3 || dy > 3))
                    didDragRef.current = true;
            }
            const nx = Math.min(Math.max(0, e.clientX - ox), Math.max(0, window.innerWidth - w));
            const ny = Math.min(Math.max(0, e.clientY - oy), Math.max(0, window.innerHeight - h));
            setPos({ x: nx, y: ny });
        };
        const onUp = () => { setDragging(false); dragRef.current = null; };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
    }, [dragging]);
    const startDrag = (e) => {
        setDragging(true);
        dragKindRef.current = 'panel';
        dragStartRef.current = { sx: e.clientX, sy: e.clientY };
        didDragRef.current = false;
        const rect = panelRef.current ? panelRef.current.getBoundingClientRect() : { left: 0, top: 0, width: 360, height: 300 };
        const w = rect.width || 360;
        const h = rect.height || 300;
        dragRef.current = { ox: e.clientX - rect.left, oy: e.clientY - rect.top, w, h };
    };
    const onPanelMouseDown = (e) => {
        const el = e.target;
        const inHeader = !!el.closest('.ant-card-head') || !!el.closest('.copilot-header');
        if (inHeader)
            startDrag(e);
    };
    const startFabDrag = (e) => {
        setDragging(true);
        setFabDocked(false);
        dragKindRef.current = 'fab';
        dragStartRef.current = { sx: e.clientX, sy: e.clientY };
        didDragRef.current = false;
        const rect = e.currentTarget.getBoundingClientRect();
        const w = rect.width || 56;
        const h = rect.height || 56;
        dragRef.current = { ox: e.clientX - rect.left, oy: e.clientY - rect.top, w, h };
    };
    const onFabClick = () => {
        if (dragKindRef.current === 'fab' && didDragRef.current) {
            didDragRef.current = false;
            dragKindRef.current = null;
            return;
        }
        didDragRef.current = false;
        dragKindRef.current = null;
        setOpen(true);
    };
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
            // Clear input so same file can be selected again
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
        const next = [...messages, { role: 'user', content, images: images.length > 0 ? [...images] : undefined }];
        setMessages(next);
        setInput('');
        setImages([]);
        const ctl = new AbortController();
        setController(ctl);
        setStatus('connecting');
        // 预置一条空的助手消息用于流式更新
        setMessages((prev) => [...prev, Object.assign({ role: 'assistant', content: '' }, { __streaming: true })]);
        accRef.current = '';
        pendingRef.current = '';
        await assistantChatStream({ page_key: pageKey, pathname: location.pathname, job_id: jobId, messages: next }, (t) => {
            setStatus('streaming');
            pendingRef.current += (t || '');
            if (!typingTimerRef.current) {
                typingTimerRef.current = window.setInterval(() => {
                    const step = Math.max(2, Math.min(24, Math.ceil(pendingRef.current.length / 40)));
                    if (pendingRef.current.length > 0) {
                        const emit = pendingRef.current.slice(0, step);
                        pendingRef.current = pendingRef.current.slice(step);
                        accRef.current = accRef.current + emit;
                        const last = { role: 'assistant', content: accRef.current };
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
                        setMessages((prev) => prev.map((m) => ({ role: m.role, content: m.content })));
                    }
                }, 20);
            }
        }, (st) => setStatus(st), ctl.signal).catch(() => setStatus('error'));
        setController(null);
        if (!typingTimerRef.current) {
            setMessages((prev) => prev.map((m) => ({ role: m.role, content: m.content })));
        }
    };
    const abort = () => { if (controller)
        controller.abort(); };
    const resetChat = () => { setMessages([]); localStorage.removeItem(`copilot_chat_${pageKey}`); };
    const copyText = async (text) => {
        try {
            await navigator.clipboard.writeText(text || '');
        }
        catch { }
    };
    return (_jsxs("div", { children: [!open && (_jsx("div", { className: `copilot-fab ${fabDocked ? 'copilot-fab--docked' : ''}`, style: fabDocked ? undefined : { left: pos.x, top: pos.y }, onMouseDown: startFabDrag, children: _jsxs("div", { className: "copilot-fab__bot", onClick: onFabClick, "aria-label": "Copilot", children: [_jsx("span", { className: "copilot-fab__eyes" }), _jsx("span", { className: "copilot-fab__ring" }), _jsx("span", { className: "copilot-fab__pulse" }), _jsx(RobotOutlined, {})] }) })), open && (_jsx("div", { ref: panelRef, className: "copilot-panel", style: { left: Math.min(Math.max(8, pos.x), Math.max(8, (typeof window !== 'undefined' ? window.innerWidth : 0) - (panelRef.current?.offsetWidth || 360) - 8)), top: Math.min(Math.max(64, pos.y), Math.max(64, (typeof window !== 'undefined' ? window.innerHeight : 0) - (panelRef.current?.offsetHeight || 300) - 8)) }, onMouseDown: onPanelMouseDown, children: _jsx(Card, { className: "sci-fi-card", size: "small", title: _jsxs("div", { className: "copilot-header", onMouseDown: startDrag, onDoubleClick: () => setOpen(false), style: { cursor: dragging ? 'grabbing' : 'grab', width: '100%', display: 'flex', alignItems: 'center', gap: 8 }, children: [_jsx(RobotOutlined, { style: { color: 'var(--neon-cyan)' } }), _jsx("span", { children: "Copilot" })] }), extra: _jsxs(Space, { children: [_jsx(Tag, { color: "cyan", children: pageKey }), _jsx(Button, { type: "text", icon: _jsx(CloseOutlined, {}), onClick: () => setOpen(false) })] }), children: _jsxs("div", { style: { display: 'flex', flexDirection: 'column', gap: 8 }, children: [_jsxs(Space, { size: 4, wrap: true, children: [!!jobId && _jsxs(Tag, { color: "blue", children: ["job: ", jobId] }), _jsx(Tag, { color: "default", children: location.pathname }), status !== 'idle' && _jsx(Tag, { color: status === 'error' ? 'red' : (status === 'done' ? 'green' : 'orange'), children: status })] }), _jsx("div", { className: "copilot-guide", children: loadingGuide ? _jsx(Spin, {}) : (guide ? _jsx(Typography.Paragraph, { style: { color: 'var(--text-starlight)' }, children: guide }) : _jsx(Typography.Text, { type: "secondary", children: "\u672A\u52A0\u8F7D\u6307\u5357" })) }), _jsx("div", { className: "copilot-chat", ref: chatRef, children: messages.map((m, i) => (_jsxs("div", { className: m.role === 'user' ? 'copilot-row copilot-row--user' : 'copilot-row copilot-row--assistant', children: [m.role === 'assistant' && _jsx(Avatar, { className: "copilot-avatar", size: 28, icon: _jsx(RobotOutlined, {}) }), _jsxs("div", { className: m.role === 'user' ? 'copilot-msg copilot-msg--user' : 'copilot-msg copilot-msg--assistant', children: [m.images && m.images.length > 0 && (_jsx("div", { className: "image-container", children: m.images.map((img, i) => (_jsx("img", { src: img, alt: "upload" }, i))) })), _jsx(ReactMarkdown, { children: m.content }), m.role === 'assistant' && (_jsx("div", { className: "copilot-msg__actions", children: _jsx(Button, { size: "small", type: "text", icon: _jsx(CopyOutlined, {}), onClick: () => copyText(m.content), children: "\u590D\u5236" }) }))] }), m.role === 'user' && _jsx(Avatar, { className: "copilot-avatar", size: 28, icon: _jsx(UserOutlined, {}) })] }, i))) }), _jsxs("div", { className: "copilot-input", children: [images.length > 0 && (_jsx("div", { className: "copilot-image-preview", children: images.map((img, i) => (_jsxs("div", { className: "copilot-image-preview__item", children: [_jsx("img", { src: img, alt: "preview" }), _jsx("div", { onClick: () => removeImage(i), className: "copilot-image-preview__remove", children: _jsx(CloseOutlined, { style: { fontSize: 10 } }) })] }, i))) })), _jsx(Input.TextArea, { rows: 2, value: input, onChange: (e) => setInput(e.target.value), placeholder: "Shift+Enter \u6362\u884C\uFF0CEnter \u53D1\u9001\uFF0CCtrl+V \u7C98\u8D34\u56FE\u7247", onPressEnter: (e) => { if (!e.shiftKey) {
                                            e.preventDefault();
                                            send();
                                        } }, onPaste: handlePaste }), _jsxs("div", { className: "copilot-input__actions", children: [_jsx("input", { type: "file", accept: "image/*", multiple: true, ref: fileInputRef, style: { display: 'none' }, onChange: handleFileSelect }), _jsx(Button, { icon: _jsx(PictureOutlined, {}), onClick: () => fileInputRef.current?.click() }), _jsx(Button, { type: "primary", icon: _jsx(SendOutlined, {}), onClick: send, disabled: (!input.trim() && images.length === 0) || status === 'streaming', children: "\u53D1\u9001" }), (status === 'connecting' || status === 'streaming') && _jsx(Button, { danger: true, icon: _jsx(PauseCircleOutlined, {}), onClick: abort, children: "\u4E2D\u65AD" }), _jsx(Button, { icon: _jsx(ReloadOutlined, {}), onClick: resetChat, children: "\u91CD\u7F6E" })] })] })] }) }) }))] }));
}
