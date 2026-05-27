import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Typography, Checkbox, Button, Space, message, Tag, theme, Tooltip, Empty, Popconfirm } from 'antd';
import { SaveOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, EyeOutlined, CheckCircleOutlined, ReloadOutlined, AppstoreOutlined } from '@ant-design/icons';
import styles from './Templates.module.css';
const { Title, Text } = Typography;
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
    const { token } = theme.useToken();
    const isDark = token.colorBgBase === '#0f172a' || token.colorTextBase === '#f1f5f9';
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
        saveTemplate();
        message.info('模板已应用。后续生成报告将参考所选章节。');
    };
    const resetTemplate = () => {
        const defaults = CANDIDATE_SECTIONS.filter(s => s.default).map(s => s.id);
        setSelected(defaults);
        setOrder(defaults);
        message.info('已重置为默认模板');
    };
    const selectedSet = new Set(selected);
    const orderedSelected = order.filter(id => selectedSet.has(id));
    const grouped = CANDIDATE_SECTIONS.reduce((acc, s) => {
        const k = s.category || '其他';
        acc[k] = acc[k] || [];
        acc[k].push(s);
        return acc;
    }, {});
    // Order categories to keep "核心" first
    const sortedCategories = Object.keys(grouped).sort((a, b) => {
        if (a === '核心')
            return -1;
        if (b === '核心')
            return 1;
        return a.localeCompare(b);
    });
    return (_jsxs("div", { className: styles.container, children: [_jsxs("div", { className: styles.selectionPanel, children: [_jsxs("div", { className: styles.panelHeader, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10 }, children: [_jsx(AppstoreOutlined, { style: { fontSize: 20, color: 'var(--tpl-accent)' } }), _jsx("h2", { className: styles.title, children: "\u6A21\u677F\u7AE0\u8282\u9009\u62E9" })] }), _jsx(Tooltip, { title: "\u91CD\u7F6E\u9ED8\u8BA4", children: _jsx(Button, { type: "text", icon: _jsx(ReloadOutlined, { style: { color: 'var(--tpl-text-secondary)' } }), onClick: resetTemplate }) })] }), _jsx("div", { className: styles.scrollArea, children: sortedCategories.map(cat => (_jsxs("div", { className: styles.categoryGroup, children: [_jsx("div", { className: styles.categoryTitle, children: cat }), grouped[cat].map(item => {
                                    const checked = selectedSet.has(item.id);
                                    return (_jsxs("div", { className: `${styles.sectionItem} ${checked ? styles.active : ''}`, onClick: () => toggle(item.id, !checked), children: [_jsx(Checkbox, { checked: checked, style: { pointerEvents: 'none' } }), _jsxs("div", { className: styles.sectionInfo, children: [_jsx("div", { className: styles.sectionTitle, children: item.title }), item.desc && _jsx("div", { className: styles.sectionDesc, children: item.desc })] })] }, item.id));
                                })] }, cat))) })] }), _jsxs("div", { className: styles.previewPanel, children: [_jsxs("div", { className: styles.toolbar, children: [_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10 }, children: [_jsx(EyeOutlined, { style: { fontSize: 20, color: 'var(--tpl-accent)' } }), _jsx("h2", { className: styles.title, style: { fontSize: 16 }, children: "\u6587\u6863\u9884\u89C8" }), _jsxs(Tag, { color: isDark ? "cyan" : "blue", style: { marginLeft: 10 }, children: [orderedSelected.length, " \u4E2A\u7AE0\u8282"] })] }), _jsxs(Space, { children: [_jsx(Button, { icon: _jsx(SaveOutlined, {}), onClick: saveTemplate, children: "\u4FDD\u5B58\u8349\u7A3F" }), _jsx(Button, { type: "primary", icon: _jsx(CheckCircleOutlined, {}), onClick: applyTemplate, children: "\u5E94\u7528\u6A21\u677F" })] })] }), _jsx("div", { className: styles.paperPreview, children: _jsxs("div", { className: styles.paper, children: [_jsxs("div", { className: styles.paperHeader, children: [_jsx("div", { className: styles.paperTitle, children: "\u7814\u7A76\u62A5\u544A\u6A21\u677F" }), _jsxs("div", { className: styles.paperMeta, children: ["\u751F\u6210\u7ED3\u6784\u9884\u89C8 \u2022 ", new Date().toLocaleDateString()] })] }), orderedSelected.length === 0 ? (_jsx(Empty, { description: "\u672A\u9009\u62E9\u4EFB\u4F55\u7AE0\u8282", image: Empty.PRESENTED_IMAGE_SIMPLE })) : (orderedSelected.map((id, index) => {
                                    const item = CANDIDATE_SECTIONS.find(s => s.id === id);
                                    if (!item)
                                        return null;
                                    return (_jsxs("div", { className: styles.previewItem, children: [_jsx("div", { className: styles.previewIndex, children: String(index + 1).padStart(2, '0') }), _jsxs("div", { className: styles.previewContent, children: [_jsx("div", { className: styles.previewTitle, children: item.title }), _jsx("div", { className: styles.previewDesc, children: item.desc })] }), _jsxs("div", { className: styles.previewActions, children: [_jsx(Button, { size: "small", icon: _jsx(ArrowUpOutlined, {}), disabled: index === 0, onClick: () => move(id, 'up') }), _jsx(Button, { size: "small", icon: _jsx(ArrowDownOutlined, {}), disabled: index === orderedSelected.length - 1, onClick: () => move(id, 'down') }), _jsx(Popconfirm, { title: "\u786E\u8BA4\u79FB\u9664\u8BE5\u7AE0\u8282\uFF1F", onConfirm: () => toggle(id, false), children: _jsx(Button, { size: "small", danger: true, icon: _jsx(DeleteOutlined, {}) }) })] })] }, id));
                                })), _jsx("div", { style: { textAlign: 'center', marginTop: 40, color: 'var(--tpl-text-secondary)', fontSize: 12 }, children: "--- \u6587\u6863\u7ED3\u6784\u7ED3\u675F ---" })] }) })] })] }));
}
