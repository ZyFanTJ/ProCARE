import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Button, Card, Typography, Space, message, Spin, Input } from 'antd';
import { fetchSectionsMeta, generateSection as generateSectionApi } from '../api/research';
export default function ReportGenerator() {
    const [selectedSections, setSelectedSections] = useState([]);
    const [generated, setGenerated] = useState({});
    const [loading, setLoading] = useState({});
    const [templateLoaded, setTemplateLoaded] = useState(false);
    const [jobId, setJobId] = useState('');
    const [metaSections, setMetaSections] = useState([]);
    useEffect(() => {
        const init = async () => {
            try {
                const meta = await fetchSectionsMeta();
                const secs = meta.sections || [];
                setMetaSections(secs);
                const saved = localStorage.getItem('rws_report_template');
                if (saved) {
                    const { selected, order } = JSON.parse(saved);
                    const defaultIds = secs.filter((s) => s.default).map((s) => s.id);
                    const ordered = (order || defaultIds).filter((id) => (selected || defaultIds).includes(id));
                    setSelectedSections(ordered);
                }
                else {
                    const defaults = secs.filter((s) => s.default).map((s) => s.id);
                    setSelectedSections(defaults);
                }
            }
            catch { }
            setTemplateLoaded(true);
        };
        init();
    }, []);
    const generateOneSection = async (sectionId) => {
        if (!jobId) {
            message.error('请先输入Job ID');
            return;
        }
        setLoading(prev => ({ ...prev, [sectionId]: true }));
        try {
            const res = await generateSectionApi(jobId, sectionId);
            setGenerated(prev => ({ ...prev, [sectionId]: res.content }));
            message.success(`${sectionId} 生成成功`);
        }
        catch (error) {
            message.error(`${sectionId} 生成失败`);
        }
        setLoading(prev => ({ ...prev, [sectionId]: false }));
    };
    if (!templateLoaded)
        return _jsx(Spin, {});
    return (_jsxs("div", { children: [_jsx(Typography.Title, { level: 3, children: "\u62A5\u544A\u751F\u6210\u754C\u9762" }), _jsxs(Card, { children: [_jsx(Typography.Paragraph, { children: "\u9009\u62E9\u6A21\u677F\u540E\uFF0C\u53EF\u9010\u7AE0\u8282\u624B\u52A8\u751F\u6210\u5185\u5BB9\u3002" }), _jsx(Input, { placeholder: "\u8F93\u5165Job ID", value: jobId, onChange: e => setJobId(e.target.value), style: { marginBottom: 16 } }), _jsx(Space, { direction: "vertical", style: { width: '100%' }, children: selectedSections.map((id) => {
                            const section = metaSections.find((s) => s.id === id);
                            return (_jsx(Card, { title: section?.title || id, extra: _jsx(Button, { onClick: () => generateOneSection(id), loading: loading[id], children: "\u751F\u6210" }), children: generated[id] ? _jsx("div", { children: generated[id] }) : _jsx(Typography.Text, { type: "secondary", children: "\u672A\u751F\u6210" }) }, id));
                        }) })] })] }));
}
