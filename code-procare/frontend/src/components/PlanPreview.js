import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from 'react';
import { Card, List, Space, Tag, Typography } from 'antd';
function stepTitle(s, i) {
    const name = (s && typeof s === 'object') ? (s.name || s.step || s.type || `步骤 ${i + 1}`) : `步骤 ${i + 1}`;
    return String(name);
}
function stepMeta(s) {
    const m = [];
    const target = s.target || s.sheet || s.table || '';
    if (target)
        m.push({ label: '目标', value: String(target) });
    const cols = s.columns || s.fields || s.features || s.concepts || [];
    if (Array.isArray(cols) && cols.length)
        m.push({ label: '字段', value: cols.slice(0, 8).join(', ') });
    const filt = s.filters || s.where || s.criteria || '';
    if (filt && typeof filt === 'string')
        m.push({ label: '筛选', value: filt });
    const out = s.output || s.artifact || s.save || '';
    if (out)
        m.push({ label: '输出', value: String(out) });
    const model = s.model || s.analysis || s.method || '';
    if (model)
        m.push({ label: '方法', value: String(model) });
    return m;
}
function StepItem({ s, i }) {
    const title = stepTitle(s, i);
    const desc = (s && typeof s === 'object') ? (s.description || s.desc || '') : (typeof s === 'string' ? s : '');
    const meta = (s && typeof s === 'object') ? stepMeta(s) : [];
    const extraTags = [];
    if (s && typeof s === 'object') {
        const target = s.target || s.sheet || '';
        if (target)
            extraTags.push(String(target));
        const kind = s.kind || s.type || '';
        if (kind)
            extraTags.push(String(kind));
    }
    return (_jsxs(Card, { size: "small", style: { marginBottom: 8 }, children: [_jsx(Space, { style: { justifyContent: 'space-between', width: '100%' }, children: _jsxs(Space, { children: [_jsx(Tag, { color: "green", children: i + 1 }), _jsx(Typography.Text, { strong: true, children: title }), extraTags.map((t, idx) => (_jsx(Tag, { color: "geekblue", children: t }, idx)))] }) }), desc && _jsx("div", { style: { marginTop: 6 }, children: _jsx(Typography.Text, { children: desc }) }), !!meta.length && (_jsx(List, { size: "small", dataSource: meta, renderItem: (item) => (_jsx(List.Item, { children: _jsxs(Space, { children: [_jsxs(Typography.Text, { type: "secondary", children: [item.label, ":"] }), _jsx(Typography.Text, { children: item.value })] }) })) }))] }));
}
export default function PlanPreview({ plan }) {
    const objective = String(plan?.objective || plan?.topic || '');
    const steps = Array.isArray(plan?.steps) ? plan.steps : [];
    const artifacts = plan?.artifacts || {};
    const hasArtifacts = artifacts && typeof artifacts === 'object';
    const artList = useMemo(() => {
        const arr = [];
        Object.entries(artifacts || {}).forEach(([k, v]) => arr.push({ k, v: String(v) }));
        return arr;
    }, [artifacts]);
    return (_jsxs("div", { children: [!!objective && (_jsxs(Card, { size: "small", style: { marginBottom: 12 }, children: [_jsx(Typography.Text, { strong: true, children: "\u7814\u7A76\u76EE\u6807" }), _jsx("div", { style: { marginTop: 6 }, children: _jsx(Typography.Text, { children: objective }) })] })), _jsx(Card, { size: "small", title: "\u6B65\u9AA4", children: steps.length ? steps.map((s, i) => (_jsx(StepItem, { s: s, i: i }, i))) : _jsx(Typography.Text, { type: "secondary", children: "\u65E0\u6B65\u9AA4" }) }), hasArtifacts && (_jsx(Card, { size: "small", title: "\u4EA7\u51FA", style: { marginTop: 12 }, children: _jsx(List, { size: "small", dataSource: artList, renderItem: (it) => (_jsx(List.Item, { children: _jsxs(Space, { children: [_jsxs(Typography.Text, { type: "secondary", children: [it.k, ":"] }), _jsx(Typography.Text, { children: it.v })] }) })) }) }))] }));
}
