import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card, Typography, Space, Button, message, Layout, Tree, Progress, Tag } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { fetchReport, fetchReportStatus, fetchReportPreview, fetchPaperStatus } from '../api/research';
import '../assets/markdown.css';
const { Title } = Typography;
function slugify(text) {
    return (text || '')
        .toLowerCase()
        .trim()
        .replace(/[\s]+/g, '-')
        .replace(/[^\p{L}\p{N}-]+/gu, '');
}
function buildToc(markdown) {
    const lines = (markdown || '').split(/\r?\n/);
    const items = [];
    const stack = [];
    const idCounts = {};
    const idList = [];
    let seq = 1;
    lines.forEach((line) => {
        const m = line.match(/^(#{1,6})\s+(.*)$/);
        if (!m)
            return;
        const rawLevel = m[1].length;
        const level = Math.min(rawLevel, 3); // 仅到三级，目录与锚点只处理H1-H3
        const text = m[2].trim();
        const base = slugify(text);
        let id = base;
        if (!id) {
            id = `section-${seq++}`;
        }
        if (idCounts[id] !== undefined) {
            idCounts[id] += 1;
            id = `${id}-${idCounts[id]}`;
        }
        else {
            idCounts[id] = 0;
        }
        // 仅收集H1-H3的id用于渲染顺序匹配，避免H4+打乱索引
        if (rawLevel <= 3) {
            idList.push(id);
        }
        const node = { level, text, id, children: [] };
        if (stack.length === 0) {
            items.push(node);
            stack.push(node);
            return;
        }
        // 调整栈以适配层级
        while (stack.length && stack[stack.length - 1].level >= level) {
            stack.pop();
        }
        if (stack.length === 0) {
            items.push(node);
            stack.push(node);
        }
        else {
            const parent = stack[stack.length - 1];
            parent.children = parent.children || [];
            parent.children.push(node);
            stack.push(node);
        }
    });
    return { toc: items, idList };
}
export default function ReportViewer() {
    const { jobId } = useParams();
    const [text, setText] = useState('');
    const containerRef = useRef(null);
    const [progress, setProgress] = useState(0);
    const [step, setStep] = useState('');
    const [running, setRunning] = useState(false);
    const [paperStatus, setPaperStatus] = useState(null);
    const staticPrefix = useMemo(() => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        return baseApi ? baseApi.replace(/\/api$/, '') : '';
    }, []);
    useEffect(() => {
        if (!jobId)
            return;
        let timer;
        fetchReportStatus(jobId).then((st) => {
            setProgress(st.progress || 0);
            setStep(st.step || '');
            const isRunning = st.state === 'running';
            setRunning(isRunning);
            if (isRunning) {
                timer = setInterval(async () => {
                    try {
                        const s = await fetchReportStatus(jobId);
                        setProgress(s.progress || 0);
                        setStep(s.step || '');
                        if (s.state === 'running') {
                            try {
                                const pv = await fetchReportPreview(jobId);
                                setText(pv || '');
                            }
                            catch { }
                        }
                        else {
                            clearInterval(timer);
                            setRunning(false);
                            if (s.state === 'done') {
                                const t = await fetchReport(jobId);
                                setText(t);
                            }
                        }
                    }
                    catch {
                        clearInterval(timer);
                        setRunning(false);
                    }
                }, 1000);
            }
            else {
                fetchReport(jobId).then(setText).catch(() => setText('报告获取失败'));
            }
        }).catch(() => {
            fetchReport(jobId).then(setText).catch(() => setText('报告获取失败'));
        });
        return () => { if (timer)
            clearInterval(timer); };
    }, [jobId]);
    useEffect(() => {
        if (!jobId)
            return;
        fetchPaperStatus(jobId).then(setPaperStatus).catch(() => setPaperStatus(null));
    }, [jobId]);
    const blobToDataUrl = async (blob) => {
        return await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = (e) => reject(e);
            reader.readAsDataURL(blob);
        });
    };
    const inlineImages = async (root) => {
        const imgs = Array.from(root.querySelectorAll('img'));
        for (const img of imgs) {
            const src = img.getAttribute('src') || '';
            if (!src || src.startsWith('data:'))
                continue;
            try {
                const resp = await fetch(src, { mode: 'cors' });
                if (!resp.ok)
                    continue;
                const blob = await resp.blob();
                const dataUrl = await blobToDataUrl(blob);
                img.setAttribute('src', dataUrl);
                img.setAttribute('crossorigin', 'anonymous');
            }
            catch (e) {
                // 忽略单张图片失败，继续处理其他图片
                continue;
            }
        }
    };
    const downloadMarkdown = () => {
        if (!text) {
            message.warning('暂无可下载的报告');
            return;
        }
        try {
            const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${jobId || 'unknown'}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
        catch {
            message.error('下载失败');
        }
    };
    const exportPDF = async () => {
        try {
            const el = containerRef.current;
            if (!el) {
                message.warning('暂无可导出的内容');
                return;
            }
            // 优先使用全局已加载的html2pdf，否则从CDN动态加载
            const getHtml2Pdf = async () => {
                const w = window;
                if (w.html2pdf)
                    return w.html2pdf;
                await new Promise((resolve, reject) => {
                    const s = document.createElement('script');
                    s.src = 'https://cdn.staticfile.net/html2pdf.js/0.10.2/html2pdf.bundle.min.js';
                    s.async = true;
                    s.onload = () => resolve();
                    s.onerror = () => reject(new Error('html2pdf加载失败'));
                    document.body.appendChild(s);
                });
                return window.html2pdf;
            };
            // 先将容器内图片内联为dataURL，避免跨域导致的canvas污染
            await inlineImages(el);
            const html2pdf = await getHtml2Pdf();
            const opt = {
                margin: [10, 10, 10, 10],
                filename: `report_${jobId || 'unknown'}.pdf`,
                image: { type: 'jpeg', quality: 0.95 },
                html2canvas: { scale: 2, useCORS: true, allowTaint: false, scrollY: 0 },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
                pagebreak: { mode: ['css', 'legacy'], avoid: ['.md-code', '.md-table', '.md-img', '.md-figure'] },
            };
            await html2pdf().set(opt).from(el).save();
        }
        catch (e) {
            message.error('PDF导出失败，请稍后重试');
        }
    };
    const exportDocxPlaceholder = () => {
        message.info('DOCX导出功能预留，后续版本支持');
    };
    const resolveStaticUrl = (url) => {
        if (!url)
            return '';
        return url.startsWith('/static/') ? `${staticPrefix}${url}` : url;
    };
    const { toc, idList } = useMemo(() => buildToc(text), [text]);
    const [tocCollapsed, setTocCollapsed] = useState(false);
    const headingRenderIndexRef = useRef(0);
    // 每次文本变化时重置标题渲染索引，保证id与目录顺序一致
    useEffect(() => {
        headingRenderIndexRef.current = 0;
    }, [text]);
    const scrollToId = (id) => {
        const esc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^\w-]/g, ''));
        const el = containerRef.current?.querySelector(`#${esc(id)}`);
        if (el) {
            // 获取元素相对于视口的位置
            const rect = el.getBoundingClientRect();
            // 获取当前滚动的偏移量
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            // 计算目标位置：当前滚动位置 + 元素相对位置 - 顶部导航栏高度(64px) - 额外缓冲(24px)
            const offset = scrollTop + rect.top - 64 - 24;
            window.scrollTo({
                top: offset,
                behavior: 'smooth'
            });
        }
    };
    const treeData = (nodes) => nodes.map(n => ({
        key: n.id,
        title: _jsx("a", { onClick: () => scrollToId(n.id), children: n.text }),
        children: n.children && n.children.length ? treeData(n.children) : undefined,
    }));
    return (_jsxs(Card, { children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }, children: [_jsx(Title, { level: 3, style: { margin: 0 }, children: "\u62A5\u544A\u9884\u89C8" }), _jsxs(Space, { children: [_jsx(Link, { to: "/projects", children: _jsx(Button, { children: "\u8FD4\u56DE" }) }), _jsx(Progress, { percent: progress, status: running ? 'active' : (progress >= 100 ? 'success' : 'normal') }), step && _jsx(Tag, { color: "blue", children: step }), _jsx(Link, { to: `/compose/${jobId}`, children: _jsx(Button, { children: "\u91CD\u65B0\u751F\u6210\u62A5\u544A (\u4EA4\u4E92)" }) }), _jsx(Button, { onClick: () => setTocCollapsed(v => !v), children: tocCollapsed ? '显示目录' : '隐藏目录' }), _jsx(Link, { to: `/project/${jobId}/paper`, children: _jsx(Button, { loading: paperStatus?.status === 'pending' || paperStatus?.status === 'running', children: "\u8BBA\u6587\u751F\u6210" }) }), paperStatus?.status === 'completed' && paperStatus.pdf_url && (_jsx(Button, { href: resolveStaticUrl(paperStatus.pdf_url), target: "_blank", type: "primary", children: "\u8BBA\u6587 PDF" })), paperStatus?.status === 'completed' && paperStatus.tex_url && (_jsx(Button, { href: resolveStaticUrl(paperStatus.tex_url), target: "_blank", children: "LaTeX" })), paperStatus?.status === 'completed' && paperStatus.latex_zip_url && (_jsx(Button, { href: resolveStaticUrl(paperStatus.latex_zip_url), target: "_blank", children: "LaTeX \u9879\u76EE" })), paperStatus?.status === 'failed' && _jsx(Tag, { color: "red", children: "\u8BBA\u6587\u751F\u6210\u5931\u8D25" }), _jsx(Button, { onClick: exportPDF, type: "primary", children: "\u5BFC\u51FA PDF" }), _jsx(Button, { onClick: downloadMarkdown, children: "\u4E0B\u8F7D Markdown" }), _jsx(Button, { onClick: exportDocxPlaceholder, disabled: true, children: "\u5BFC\u51FA DOCX (\u9884\u7559)" })] })] }), _jsxs(Layout, { style: { background: 'transparent', minHeight: 600 }, children: [_jsxs(Layout.Sider, { collapsible: true, collapsed: tocCollapsed, onCollapse: (v) => setTocCollapsed(v), width: 260, theme: "light", style: {
                            background: '#fff',
                            padding: 12,
                            borderRight: '1px solid #f0f0f0',
                            position: 'sticky',
                            top: 64,
                            height: 'calc(100vh - 64px)',
                            overflow: 'auto',
                            alignSelf: 'flex-start',
                        }, children: [_jsx(Title, { level: 5, style: { marginTop: 0 }, children: "\u76EE\u5F55" }), _jsx(Tree, { treeData: treeData(toc), defaultExpandAll: true })] }), _jsx(Layout.Content, { style: { padding: '0 16px' }, children: _jsx("div", { className: "md-container", ref: containerRef, children: _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], components: {
                                    h1: ({ node, children, ...props }) => {
                                        const idx = headingRenderIndexRef.current++;
                                        const id = idList[idx] || `section-${idx + 1}`;
                                        return _jsx("h1", { id: id, className: "md-h1", ...props, children: children });
                                    },
                                    h2: ({ node, children, ...props }) => {
                                        const idx = headingRenderIndexRef.current++;
                                        const id = idList[idx] || `section-${idx + 1}`;
                                        return _jsx("h2", { id: id, className: "md-h2", ...props, children: children });
                                    },
                                    h3: ({ node, children, ...props }) => {
                                        const idx = headingRenderIndexRef.current++;
                                        const id = idList[idx] || `section-${idx + 1}`;
                                        return _jsx("h3", { id: id, className: "md-h3", ...props, children: children });
                                    },
                                    p: ({ node, ...props }) => _jsx("p", { className: "md-p", ...props }),
                                    blockquote: ({ node, ...props }) => _jsx("blockquote", { className: "md-quote", ...props }),
                                    pre: ({ node, ...props }) => _jsx("pre", { className: "md-code", ...props }),
                                    code: ({ node, className, children, ...props }) => (_jsx("code", { className: className, ...props, children: children })),
                                    ul: ({ node, ...props }) => _jsx("ul", { className: "md-ul", ...props }),
                                    ol: ({ node, ...props }) => _jsx("ol", { className: "md-ol", ...props }),
                                    table: ({ node, ...props }) => (_jsx("div", { style: { overflowX: 'auto' }, children: _jsx("table", { className: "md-table", ...props }) })),
                                    img: ({ node, ...props }) => {
                                        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
                                        const prefix = baseApi.replace(/\/api$/, '');
                                        const src = (props.src || '');
                                        const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src;
                                        return (_jsx("div", { className: "md-figure", children: _jsx("img", { ...props, src: finalSrc, className: "md-img", crossOrigin: "anonymous" }) }));
                                    },
                                    a: ({ node, ...props }) => _jsx("a", { className: "md-a", target: "_blank", rel: "noreferrer", ...props }),
                                }, children: text }) }) })] })] }));
}
