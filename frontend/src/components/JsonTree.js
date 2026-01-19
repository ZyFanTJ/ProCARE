import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo, useState } from 'react';
function isObject(v) { return v && typeof v === 'object' && !Array.isArray(v); }
function isArray(v) { return Array.isArray(v); }
function summarize(value) {
    try {
        if (isArray(value))
            return `[${value.length}]`;
        if (isObject(value))
            return `{${Object.keys(value).length}}`;
        if (typeof value === 'string')
            return JSON.stringify(value.length > 40 ? value.slice(0, 40) + '…' : value);
        if (value === null)
            return 'null';
        return String(value);
    }
    catch {
        return '';
    }
}
export default function JsonTree({ data, defaultCollapsed = true }) {
    const rootKey = 'root';
    const [open, setOpen] = useState({});
    const toggle = (path) => setOpen((prev) => ({ ...prev, [path]: !prev[path] }));
    const renderNode = (key, value, path, depth) => {
        const collapsible = isObject(value) || isArray(value);
        const opened = open[path] ?? !defaultCollapsed;
        const pad = { paddingLeft: depth * 12 };
        const label = (_jsxs("span", { children: [_jsx("span", { style: { color: '#9ca3af' }, children: key }), _jsx("span", { style: { color: '#6b7280' }, children: ": " }), !collapsible && _jsx("span", { style: { color: typeof value === 'string' ? '#22d3ee' : '#93c5fd' }, children: summarize(value) }), collapsible && _jsx("span", { style: { color: '#a3a3a3' }, children: summarize(value) })] }));
        return (_jsxs("div", { style: pad, children: [collapsible ? (_jsxs("div", { style: { cursor: 'pointer', userSelect: 'none' }, onClick: () => toggle(path), children: [_jsx("span", { style: { display: 'inline-block', width: 14 }, children: opened ? '▾' : '▸' }), label] })) : (_jsx("div", { children: label })), collapsible && opened && (_jsx("div", { children: isArray(value)
                        ? value.map((v, i) => renderNode(`[${i}]`, v, `${path}[${i}]`, depth + 1))
                        : Object.entries(value || {}).map(([k, v]) => renderNode(k, v, `${path}.${k}`, depth + 1)) }))] }, path));
    };
    const tree = useMemo(() => {
        return renderNode(rootKey, data, rootKey, 0);
    }, [data, open, defaultCollapsed]);
    return (_jsx("div", { style: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', fontSize: 13, background: '#0b1220', color: '#e5e7eb', borderRadius: 8, padding: 8 }, children: tree }));
}
