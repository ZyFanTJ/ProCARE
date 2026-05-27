import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useMemo } from 'react';
import { Typography, Space, Collapse } from 'antd';
import { ToolOutlined, RightSquareOutlined, WarningOutlined } from '@ant-design/icons';
import CodeViewer from './CodeViewer';
const { Text, Paragraph } = Typography;
const { Panel } = Collapse;
function parseLogs(rawText) {
    // 1. Strip ANSI codes
    const text = rawText.replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '');
    const lines = text.split('\n');
    const blocks = [];
    let currentBlock = null;
    let inCodeBlock = false;
    let codeLang = '';
    const commitBlock = () => {
        if (currentBlock && currentBlock.content.length > 0) {
            blocks.push({ ...currentBlock, id: `block-${blocks.length}` });
        }
    };
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        // Code block toggle
        if (line.startsWith('```')) {
            if (inCodeBlock) {
                if (currentBlock) {
                    // Remove the closing backticks line if we want to cleanly use CodeViewer
                    // But let's just keep it or slice it out
                }
                commitBlock();
                currentBlock = null;
                inCodeBlock = false;
            }
            else {
                commitBlock();
                inCodeBlock = true;
                codeLang = line.slice(3).trim();
                currentBlock = { type: 'code', content: [], language: codeLang };
            }
            continue;
        }
        if (inCodeBlock) {
            if (!currentBlock)
                currentBlock = { type: 'code', content: [], language: codeLang };
            currentBlock.content.push(line);
            continue;
        }
        // Tool/Model marker
        if (line.startsWith('> ') || line.trim().startsWith('→ ') || line.trim().startsWith('✱ ')) {
            commitBlock();
            blocks.push({ id: `block-${blocks.length}`, type: 'tool', content: [line] });
            continue;
        }
        // Action marker
        if (line.startsWith('⚙ ')) {
            commitBlock();
            currentBlock = { type: 'tool', content: [line] };
            continue;
        }
        // Command marker
        if (line.startsWith('$ ')) {
            commitBlock();
            blocks.push({ id: `block-${blocks.length}`, type: 'command', content: [line.slice(2)] });
            currentBlock = { type: 'output', content: [] };
            continue;
        }
        // Error marker
        if (line.toLowerCase().includes('error:') || line.toLowerCase().includes('exception:')) {
            if (currentBlock?.type !== 'error') {
                commitBlock();
                currentBlock = { type: 'error', content: [] };
            }
            currentBlock.content.push(line);
            continue;
        }
        // Blank lines
        if (line.trim() === '') {
            if (currentBlock && (currentBlock.type === 'tool' || currentBlock.type === 'command')) {
                commitBlock();
                currentBlock = null;
            }
            else if (currentBlock) {
                currentBlock.content.push(line);
            }
            continue;
        }
        // Default text
        if (!currentBlock) {
            currentBlock = { type: 'text', content: [line] };
        }
        else {
            currentBlock.content.push(line);
        }
    }
    commitBlock();
    // Cleanup: trim leading/trailing blank lines in blocks
    return blocks.map(b => {
        let c = [...b.content];
        while (c.length > 0 && c[0].trim() === '')
            c.shift();
        while (c.length > 0 && c[c.length - 1].trim() === '')
            c.pop();
        return { ...b, content: c };
    }).filter(b => b.content.length > 0);
}
export default function StructuredLogViewer({ log }) {
    const blocks = useMemo(() => parseLogs(log || ''), [log]);
    const bottomRef = useRef(null);
    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'auto', block: 'end' });
        }
    }, [blocks.length, log]);
    const renderBlock = (block) => {
        const textContent = block.content.join('\n');
        switch (block.type) {
            case 'tool':
                return (_jsx("div", { style: { marginBottom: 12, padding: '8px 12px', backgroundColor: '#f0f5ff', borderRadius: 6, borderLeft: '4px solid #1890ff' }, children: _jsxs(Space, { align: "start", children: [_jsx(ToolOutlined, { style: { color: '#1890ff', marginTop: 4 } }), _jsx("div", { style: { color: '#0050b3', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }, children: textContent })] }) }, block.id));
            case 'command':
                return (_jsx("div", { style: { marginBottom: 0, padding: '8px 12px', backgroundColor: '#2b2b2b', borderRadius: '6px 6px 0 0', color: '#55ff55', fontFamily: 'monospace', fontSize: 13 }, children: _jsxs(Space, { children: [_jsx(RightSquareOutlined, {}), _jsx("span", { children: textContent })] }) }, block.id));
            case 'output':
                return (_jsx("div", { style: { marginBottom: 12, padding: '8px 12px', backgroundColor: '#1e1e1e', borderRadius: '0 0 6px 6px', color: '#d4d4d4', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto' }, children: textContent }, block.id));
            case 'code':
                return (_jsx("div", { style: { marginBottom: 12 }, children: _jsx(CodeViewer, { code: textContent, language: block.language || 'python', collapsed: false }) }, block.id));
            case 'error':
                return (_jsx("div", { style: { marginBottom: 12, padding: '8px 12px', backgroundColor: '#fff2f0', borderRadius: 6, borderLeft: '4px solid #ff4d4f' }, children: _jsxs(Space, { align: "start", children: [_jsx(WarningOutlined, { style: { color: '#ff4d4f', marginTop: 4 } }), _jsx("div", { style: { color: '#cf1322', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }, children: textContent })] }) }, block.id));
            case 'text':
            default:
                return (_jsx("div", { style: { marginBottom: 12, fontSize: 14, color: '#333', lineHeight: 1.6, whiteSpace: 'pre-wrap' }, children: textContent }, block.id));
        }
    };
    return (_jsxs("div", { className: "structured-log-viewer", style: {
            backgroundColor: '#fafafa',
            padding: '16px',
            borderRadius: '8px',
            border: '1px solid #f0f0f0',
            maxHeight: '600px',
            overflowY: 'auto'
        }, children: [blocks.length === 0 && _jsx("div", { style: { color: '#999', fontStyle: 'italic' }, children: "\u7B49\u5F85\u8F93\u51FA..." }), blocks.map(renderBlock), _jsx("div", { ref: bottomRef })] }));
}
