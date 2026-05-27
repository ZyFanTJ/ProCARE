import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function highlightPython(code) {
    // Strip ANSI escape codes first to prevent them from interfering with highlighting or display
    let cleanCode = code.replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '');
    // 极简Python高亮：关键词、字符串、注释
    const keywords = ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'import', 'from', 'as', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'None', 'True', 'False'];
    const kwRe = new RegExp(`\\b(${keywords.join('|')})\\b`, 'g');
    // 先转义，后按顺序替换
    let html = escapeHtml(cleanCode);
    // 字符串
    html = html.replace(/([rRbBuUfF]?)("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"\\\n]*(?:\\.[^"\\\n]*)*"|'[^'\\\n]*(?:\\.[^'\\\n]*)*')/g, (_m, p1, p2) => `<span class="cv-str">${escapeHtml(p1 + p2)}</span>`);
    // 注释
    html = html.replace(/(#.*)$/gm, '<span class="cv-cmt">$1</span>');
    // 关键词
    html = html.replace(kwRe, '<span class="cv-kw">$1</span>');
    // 数字
    html = html.replace(/\b\d+(?:\.\d+)?\b/g, '<span class="cv-num">$&</span>');
    return html;
}
export default function CodeViewer({ code, language = 'python', collapsed = false, maxLines = 40, showLineNumbers = true }) {
    const lines = (code || '').split(/\r?\n/);
    const needCollapse = lines.length > maxLines;
    const shownLines = (collapsed && needCollapse) ? lines.slice(0, maxLines) : lines;
    const highlighted = highlightPython(shownLines.join('\n'));
    return (_jsx("div", { className: "code-viewer", children: _jsxs("div", { className: "code-viewer__inner", children: [showLineNumbers && (_jsx("div", { className: "code-viewer__gutter", children: shownLines.map((_, i) => (_jsx("div", { className: "code-viewer__ln", children: i + 1 }, i))) })), _jsx("pre", { className: "code-viewer__content", dangerouslySetInnerHTML: { __html: highlighted + ((collapsed && needCollapse) ? '\n…（已折叠）' : '') } })] }) }));
}
