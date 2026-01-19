import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Typography, Checkbox, List, Button, Space, message, Tag } from 'antd';
export const CANDIDATE_SECTIONS = [
    { id: 'abstract', title: '摘要', desc: '研究目的、数据来源与主要结论', default: true, category: '核心' },
    { id: 'background', title: '背景与目标', desc: '研究背景、动机与目标', default: true, category: '核心' },
    { id: 'data', title: '数据说明', desc: '数据结构与字段画像', default: true, category: '核心' },
    { id: 'methods', title: '方法', desc: '数据清洗、匹配、统计与可视化方法', default: true, category: '核心' },
    { id: 'results', title: '结果', desc: '按图表逐项描述与解读', default: true, category: '核心' },
    { id: 'discussion', title: '讨论', desc: '解释现象与机制，比较既往研究', default: true, category: '核心' },
    { id: 'limitations', title: '局限性', desc: '数据质量、偏倚与方法约束', default: true, category: '核心' },
    { id: 'outlook', title: '展望', desc: '后续研究方向与方法升级', default: true, category: '核心' },
    { id: 'conclusion', title: '结论', desc: '主要发现与意义', default: true, category: '核心' },
    { id: 'appendix', title: '附录（可复现性）', desc: '代码、图表列表与日志摘要', default: true, category: '核心' },
    { id: 'cohort', title: '研究对象与纳入排除标准', desc: '研究人群定义与筛选', category: '方法扩展' },
    { id: 'ethics', title: '伦理声明', desc: '伦理审查与合规说明', category: '规范' },
    { id: 'sap', title: '统计分析计划（SAP）', desc: '分析步骤与统计设定', category: '方法扩展' },
    { id: 'sensitivity', title: '敏感性分析', desc: '不同设定的稳健性验证', category: '方法扩展' },
    { id: 'subgroups', title: '子群分析', desc: '分层比较与交互作用', category: '方法扩展' },
    { id: 'missing', title: '缺失值处理策略', desc: '缺失机制与处理方法', category: '数据质量' },
    { id: 'bias', title: '偏倚控制', desc: '选择/信息/混杂偏倚控制', category: '方法扩展' },
    { id: 'dq', title: '数据质量评估', desc: '一致性、完整性与可信度', category: '数据质量' },
    { id: 'references', title: '参考文献', desc: '文献引用与DOI/PMID', category: '规范' },
    { id: 'acks', title: '致谢', desc: '贡献与支持单位', category: '规范' },
];
const STORAGE_KEY = 'rws_report_template';
export default function Templates() {
    const [selected, setSelected] = useState([]);
    const [order, setOrder] = useState([]);
    useEffect(() => {
        // 载入历史模板或默认模板
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                const obj = JSON.parse(saved);
                setSelected(obj.selected || []);
                setOrder(obj.order || []);
            }
            catch { }
        }
        else {
            const defaults = CANDIDATE_SECTIONS.filter(s => s.default).map(s => s.id);
            setSelected(defaults);
            setOrder(defaults);
        }
    }, []);
    const toggle = (id, checked) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (checked)
                next.add(id);
            else
                next.delete(id);
            const arr = Array.from(next);
            // 同步顺序（新增时追加到末尾）
            setOrder(o => checked ? (o.includes(id) ? o : [...o, id]) : o.filter(x => x !== id));
            return arr;
        });
    };
    const move = (id, dir) => {
        setOrder(prev => {
            const idx = prev.indexOf(id);
            if (idx < 0)
                return prev;
            const arr = [...prev];
            const swapWith = dir === 'up' ? idx - 1 : idx + 1;
            if (swapWith < 0 || swapWith >= arr.length)
                return prev;
            const tmp = arr[swapWith];
            arr[swapWith] = arr[idx];
            arr[idx] = tmp;
            return arr;
        });
    };
    const saveTemplate = () => {
        const payload = { selected, order };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        message.success('模板已保存');
    };
    const applyTemplate = () => {
        // 此处预留与后端的集成：可在执行前发送选中的章节集合，驱动报告生成策略
        // 目前先保存到本地，供后续流程读取
        saveTemplate();
        message.info('模板已应用。后续生成报告将参考所选章节（需后端集成）。');
    };
    const selectedSet = new Set(selected);
    const orderedSelected = order.filter(id => selectedSet.has(id));
    const grouped = CANDIDATE_SECTIONS.reduce((acc, s) => {
        const k = s.category || '其他';
        acc[k] = acc[k] || [];
        acc[k].push(s);
        return acc;
    }, {});
    return (_jsxs("div", { children: [_jsx(Typography.Title, { level: 3, children: "\u6A21\u677F\u7BA1\u7406" }), _jsxs(Card, { children: [_jsx(Typography.Paragraph, { children: "\u8BF7\u9009\u62E9\u9700\u8981\u751F\u6210\u7684\u62A5\u544A\u7AE0\u8282\u3002\u7CFB\u7EDF\u5C06\u6839\u636E\u6240\u9009\u7AE0\u8282\u7EC4\u7EC7\u5927\u6A21\u578B\u9010\u6B65\u586B\u5145\u5185\u5BB9\u3002\u4F60\u53EF\u4EE5\u4FDD\u5B58\u5E76\u5E94\u7528\u6B64\u6A21\u677F\uFF0C\u7528\u4E8E\u540E\u7EED\u62A5\u544A\u751F\u6210\u3002" }), _jsxs(Space, { style: { marginBottom: 12 }, children: [_jsx(Button, { onClick: () => { setSelected(CANDIDATE_SECTIONS.map(s => s.id)); setOrder(CANDIDATE_SECTIONS.map(s => s.id)); }, children: "\u5168\u9009" }), _jsx(Button, { onClick: () => { setSelected([]); setOrder([]); }, children: "\u6E05\u7A7A" }), _jsx(Button, { type: "primary", onClick: saveTemplate, children: "\u4FDD\u5B58\u6A21\u677F" }), _jsx(Button, { onClick: applyTemplate, children: "\u5E94\u7528\u5230\u62A5\u544A\u751F\u6210\uFF08\u9884\u7559\uFF09" })] }), Object.keys(grouped).map((cat) => (_jsx(Card, { type: "inner", title: _jsxs("span", { children: [cat, " ", _jsxs(Tag, { color: "blue", children: [grouped[cat].length, "\u9879"] })] }), style: { marginBottom: 12 }, children: _jsx(List, { dataSource: grouped[cat], renderItem: (item) => {
                                const checked = selectedSet.has(item.id);
                                const pos = order.indexOf(item.id);
                                return (_jsx(List.Item, { children: _jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 12, width: '100%' }, children: [_jsxs(Checkbox, { checked: checked, onChange: (e) => toggle(item.id, e.target.checked), children: [_jsx(Typography.Text, { strong: true, children: item.title }), item.desc && _jsx(Typography.Text, { type: "secondary", style: { marginLeft: 8 }, children: item.desc })] }), checked && (_jsxs(Space, { children: [_jsx(Button, { size: "small", onClick: () => move(item.id, 'up'), disabled: pos <= 0, children: "\u4E0A\u79FB" }), _jsx(Button, { size: "small", onClick: () => move(item.id, 'down'), disabled: pos < 0 || pos >= order.length - 1, children: "\u4E0B\u79FB" }), _jsxs(Tag, { children: ["\u987A\u5E8F: ", pos + 1] })] }))] }) }));
                            } }) }, cat))), _jsx(Card, { type: "inner", title: "\u5DF2\u9009\u62E9\u7684\u7AE0\u8282\u987A\u5E8F\u9884\u89C8", style: { marginTop: 12 }, children: orderedSelected.length ? (_jsx(Space, { wrap: true, children: orderedSelected.map((id, i) => {
                                const s = CANDIDATE_SECTIONS.find(x => x.id === id);
                                return _jsxs(Tag, { color: "green", children: [i + 1, ". ", s?.title || id] }, id);
                            }) })) : (_jsx(Typography.Text, { type: "secondary", children: "\u5C1A\u672A\u9009\u62E9\u4EFB\u4F55\u7AE0\u8282" })) })] })] }));
}
