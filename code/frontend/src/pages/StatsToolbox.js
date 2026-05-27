import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useMemo, useRef } from 'react';
import { Typography, Button, Select, Form, Input, Row, Col, Divider, Space, Drawer, message, Spin, Empty, Tag, Tabs } from 'antd';
import { ExperimentOutlined, BarChartOutlined, HeatMapOutlined, LineChartOutlined, PlayCircleOutlined, CodeOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { listJobs, fetchExcelInfo, streamSandboxCode } from '../api/research';
import Editor from '@monaco-editor/react';
import './StatsToolbox.css';
const { Title, Paragraph, Text } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;
// --- Constants & Config ---
const TOOLS = [
    {
        id: 'ttest',
        category: '假设检验',
        name: '独立样本 T 检验',
        icon: _jsx(ExperimentOutlined, {}),
        color: '#00b96b',
        description: '比较两个独立组的均值以确定它们是否显著不同。',
        params: [
            { name: 'group_col', label: '分组列', type: 'column', required: true, tooltip: '定义组的分类列（例如：治疗组/对照组）' },
            { name: 'value_col', label: '数值列', type: 'column', required: true, tooltip: '用于比较均值的数值列' },
        ],
        codeTemplate: (config) => `
import pandas as pd
import scipy.stats as stats
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 确保图表目录存在
os.makedirs(r"{plots_dir}", exist_ok=True)

# 加载数据
df = pd.read_excel(r"{excel_path}")

# 配置
group_col = "${config.group_col}"
value_col = "${config.value_col}"

# 数据准备
groups = df[group_col].unique()
if len(groups) != 2:
    print(f"错误：分组列必须恰好有2个唯一值。发现 {len(groups)} 个: {groups}")
else:
    g1 = df[df[group_col] == groups[0]][value_col]
    g2 = df[df[group_col] == groups[1]][value_col]
    
    # T 检验
    t_stat, p_val = stats.ttest_ind(g1, g2, nan_policy='omit')
    
    print(f"{value_col} 按 {group_col} 分组的 T 检验结果:")
    print(f"  组 '{groups[0]}': 均值 = {g1.mean():.4f}, N = {len(g1)}")
    print(f"  组 '{groups[1]}': 均值 = {g2.mean():.4f}, N = {len(g2)}")
    print(f"  T 统计量: {t_stat:.4f}")
    print(f"  P 值: {p_val:.4e}")
    
    # 可视化
    plt.figure(figsize=(10, 6))
    sns.boxplot(x=group_col, y=value_col, data=df, palette="viridis")
    sns.stripplot(x=group_col, y=value_col, data=df, color='black', size=4, alpha=0.5)
    plt.title(f'T 检验: {value_col} 按 {group_col}\\nP 值: {p_val:.4e}')
    plt.grid(True, alpha=0.3)
    
    # 保存图表
    plot_path = f"ttest_{group_col}_vs_{value_col}.png"
    plt.savefig(os.path.join(r"{plots_dir}", plot_path))
    print(f"已保存图表: {os.path.join(r'{plots_dir}', plot_path)}")
`
    },
    {
        id: 'anova',
        category: '假设检验',
        name: '单因素方差分析',
        icon: _jsx(BarChartOutlined, {}),
        color: '#722ed1',
        description: '比较三个或更多独立组的均值。',
        params: [
            { name: 'group_col', label: '分组列', type: 'column', required: true, tooltip: '包含3个或更多组的分类列' },
            { name: 'value_col', label: '数值列', type: 'column', required: true, tooltip: '用于比较的数值列' },
        ],
        codeTemplate: (config) => `
import pandas as pd
import scipy.stats as stats
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 确保图表目录存在
os.makedirs(r"{plots_dir}", exist_ok=True)

# 加载数据
df = pd.read_excel(r"{excel_path}")

# 配置
group_col = "${config.group_col}"
value_col = "${config.value_col}"

# 数据准备
groups = [d[value_col].dropna() for g, d in df.groupby(group_col)]
group_names = df[group_col].unique()

# 方差分析
f_stat, p_val = stats.f_oneway(*groups)

print(f"{value_col} 按 {group_col} 分组的单因素方差分析结果:")
print(f"  F 统计量: {f_stat:.4f}")
print(f"  P 值: {p_val:.4e}")

# 可视化
plt.figure(figsize=(12, 6))
sns.violinplot(x=group_col, y=value_col, data=df, palette="mako", inner="quartile")
sns.stripplot(x=group_col, y=value_col, data=df, color='white', size=3, alpha=0.5)
plt.title(f'方差分析: {value_col} 按 {group_col}\\nP 值: {p_val:.4e}')
plt.grid(True, alpha=0.3)

# 保存图表
plot_path = f"anova_{group_col}_vs_{value_col}.png"
plt.savefig(os.path.join(r"{plots_dir}", plot_path))
print(f"已保存图表: {os.path.join(r'{plots_dir}', plot_path)}")
`
    },
    {
        id: 'correlation',
        category: '探索性分析',
        name: '相关矩阵',
        icon: _jsx(HeatMapOutlined, {}),
        color: '#fa8c16',
        description: '分析多个数值变量之间的关系。',
        params: [
            { name: 'columns', label: '列', type: 'multi-column', required: true, tooltip: '选择用于相关分析的数值列' },
        ],
        codeTemplate: (config) => `
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

# 确保图表目录存在
os.makedirs(r"{plots_dir}", exist_ok=True)

# 加载数据
df = pd.read_excel(r"{excel_path}")

# 配置
cols = ${JSON.stringify(config.columns)}

# 相关性计算
corr_matrix = df[cols].corr()

print("相关矩阵:")
print(corr_matrix)

# 可视化
plt.figure(figsize=(10, 8))
mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
sns.heatmap(corr_matrix, mask=mask, annot=True, cmap='coolwarm', vmin=-1, vmax=1, center=0, square=True, linewidths=.5)
plt.title('相关矩阵')

# 保存图表
plot_path = "correlation_matrix.png"
plt.savefig(os.path.join(r"{plots_dir}", plot_path))
print(f"已保存图表: {os.path.join(r'{plots_dir}', plot_path)}")
`
    },
    {
        id: 'regression',
        category: '建模',
        name: '线性回归',
        icon: _jsx(LineChartOutlined, {}),
        color: '#eb2f96',
        description: '两个变量之间的简单线性回归。',
        params: [
            { name: 'x_col', label: 'X (自变量)', type: 'column', required: true, tooltip: '预测变量' },
            { name: 'y_col', label: 'Y (因变量)', type: 'column', required: true, tooltip: '响应变量' },
        ],
        codeTemplate: (config) => `
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 确保图表目录存在
os.makedirs(r"{plots_dir}", exist_ok=True)

# 加载数据
df = pd.read_excel(r"{excel_path}")

# 配置
x_col = "${config.x_col}"
y_col = "${config.y_col}"

# 数据准备
data = df[[x_col, y_col]].dropna()
X = data[x_col]
y = data[y_col]
X_const = sm.add_constant(X)

# 回归分析
model = sm.OLS(y, X_const).fit()
print(model.summary())

# 可视化
plt.figure(figsize=(10, 6))
sns.regplot(x=x_col, y=y_col, data=data, line_kws={"color": "red"})
plt.title(f'线性回归: {y_col} vs {x_col}\\nR2: {model.rsquared:.4f}')
plt.grid(True, alpha=0.3)

# 保存图表
plot_path = f"regression_{x_col}_vs_{y_col}.png"
plt.savefig(os.path.join(r"{plots_dir}", plot_path))
print(f"已保存图表: {os.path.join(r'{plots_dir}', plot_path)}")
`
    }
];
export default function StatsToolbox() {
    // State
    const [jobs, setJobs] = useState([]);
    const [selectedJobId, setSelectedJobId] = useState(null);
    const [excelInfo, setExcelInfo] = useState(null);
    const [selectedTool, setSelectedTool] = useState(null);
    const [config, setConfig] = useState({});
    const [generatedCode, setGeneratedCode] = useState('');
    const [running, setRunning] = useState(false);
    const [logs, setLogs] = useState([]);
    const [plots, setPlots] = useState([]);
    const [drawerVisible, setDrawerVisible] = useState(false);
    const [activeTab, setActiveTab] = useState('config');
    const [isDarkMode, setIsDarkMode] = useState(true);
    // Refs
    const logEndRef = useRef(null);
    // Effects
    useEffect(() => {
        const checkTheme = () => {
            const theme = document.documentElement.getAttribute('data-theme');
            setIsDarkMode(theme !== 'light');
        };
        checkTheme();
        const observer = new MutationObserver(checkTheme);
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        return () => observer.disconnect();
    }, []);
    useEffect(() => {
        listJobs().then(res => {
            setJobs(res.jobs || []);
            // Auto-select most recent job if available
            if (res.jobs && res.jobs.length > 0) {
                // Assuming the list is ordered or just picking first
                // setSelectedJobId(res.jobs[0].job_id) 
            }
        }).catch(console.error);
    }, []);
    useEffect(() => {
        if (!selectedJobId) {
            setExcelInfo(null);
            return;
        }
        fetchExcelInfo(selectedJobId).then(setExcelInfo).catch(console.error);
    }, [selectedJobId]);
    useEffect(() => {
        if (logEndRef.current) {
            logEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs]);
    // Helpers
    const columns = useMemo(() => {
        if (!excelInfo)
            return [];
        let cols = [];
        // Try to extract from root dtypes
        const dtypes = excelInfo?.low?.dtypes || excelInfo?.dtypes || {};
        cols = Object.keys(dtypes);
        // If empty, check first sheet
        if (cols.length === 0 && excelInfo.sheets && excelInfo.sheets.length > 0) {
            const firstSheet = excelInfo.sheets[0];
            // Try direct access or under 'profile' key
            const sheetProfile = excelInfo[firstSheet] || excelInfo.profile?.[firstSheet];
            if (sheetProfile) {
                const sheetDtypes = sheetProfile?.low?.dtypes || sheetProfile?.dtypes || {};
                cols = Object.keys(sheetDtypes);
            }
        }
        return cols;
    }, [excelInfo]);
    const handleToolClick = (tool) => {
        setSelectedTool(tool);
        setConfig({});
        setGeneratedCode('');
        setLogs([]);
        setPlots([]);
        setDrawerVisible(true);
        setActiveTab('config');
    };
    const generateCode = () => {
        if (!selectedTool || !selectedJobId || !excelInfo)
            return;
        const code = selectedTool.codeTemplate(config)
            .replace('{excel_path}', excelInfo.path.replace(/\\/g, '/'))
            .replace(/{plots_dir}/g, 'plots'); // Relative to job dir in sandbox
        setGeneratedCode(code);
        setActiveTab('code');
    };
    const runAnalysis = async () => {
        if (!selectedJobId || !generatedCode)
            return;
        setRunning(true);
        setLogs([]);
        setPlots([]);
        setActiveTab('result');
        await streamSandboxCode(selectedJobId, generatedCode, (chunk) => {
            setLogs(prev => [...prev, chunk]);
            // Plot detection
            const plotMatches = [...chunk.matchAll(/Saved plot: (.*\.png)/g)];
            if (plotMatches.length > 0) {
                const newPlots = [];
                plotMatches.forEach(match => {
                    const fullPath = match[1].trim();
                    const filename = fullPath.split(/[\\/]/).pop();
                    if (filename) {
                        // Add timestamp to prevent caching
                        const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/api\/?$/, '');
                        const url = `${baseUrl}/static/jobs/${selectedJobId}/plots/${filename}?t=${Date.now()}`;
                        newPlots.push(url);
                    }
                });
                if (newPlots.length > 0) {
                    setPlots(prev => [...prev, ...newPlots]);
                }
            }
        }, (status) => {
            if (status === 'done' || status === 'error' || status === 'interrupted') {
                setRunning(false);
                if (status === 'done')
                    message.success('分析完成');
                if (status === 'error')
                    message.error('分析失败');
            }
        });
    };
    // Renderers
    return (_jsxs("div", { className: "toolbox-container", children: [_jsxs("div", { className: "toolbox-header", children: [_jsxs("div", { children: [_jsxs("div", { className: "toolbox-title", children: [_jsx(ThunderboltOutlined, { style: { color: 'var(--primary-color)' } }), "\u7EDF\u8BA1\u5DE5\u5177\u7BB1"] }), _jsx(Text, { style: { color: 'var(--text-secondary)' }, children: "\u5177\u6709\u81EA\u52A8\u4EE3\u7801\u751F\u6210\u529F\u80FD\u7684\u9AD8\u7EA7\u7EDF\u8BA1\u5206\u6790\u5DE5\u5177" })] }), _jsx(Select, { style: { width: 300 }, placeholder: "\u9009\u62E9\u9879\u76EE\u4E0A\u4E0B\u6587", value: selectedJobId, onChange: setSelectedJobId, dropdownStyle: { background: 'var(--bg-component)' }, children: jobs.map(j => (_jsxs(Option, { value: j.job_id, children: [_jsx("span", { style: { color: 'var(--text-primary)' }, children: j.topic || j.job_id }), _jsx(Tag, { style: { marginLeft: 8, background: 'var(--bg-hover)', border: 'none', color: 'var(--text-secondary)' }, children: j.job_id.substring(0, 6) })] }, j.job_id))) })] }), _jsx(Row, { gutter: [24, 24], children: TOOLS.map(tool => (_jsx(Col, { xs: 24, sm: 12, md: 8, lg: 6, children: _jsx("div", { className: "tool-card", onClick: () => handleToolClick(tool), children: _jsxs("div", { style: { padding: '24px' }, children: [_jsx("div", { className: "tool-category", children: tool.category }), _jsx("div", { className: "tool-icon-wrapper", style: { background: `${tool.color}20`, color: tool.color }, children: tool.icon }), _jsx("div", { className: "tool-name", children: tool.name }), _jsx("div", { className: "tool-desc", children: tool.description })] }) }) }, tool.id))) }), _jsx(Drawer, { title: _jsxs(Space, { children: [selectedTool?.icon, _jsx("span", { style: { color: 'var(--text-primary)' }, children: selectedTool?.name })] }), width: 720, onClose: () => setDrawerVisible(false), open: drawerVisible, styles: {
                    body: { background: 'var(--bg-app)', padding: 0 },
                    header: { background: 'var(--bg-component)', borderBottom: '1px solid var(--border-color)', color: 'var(--text-primary)' }
                }, extra: _jsxs(Space, { children: [activeTab === 'config' && (_jsx(Button, { type: "primary", onClick: () => { generateCode(); setActiveTab('code'); }, icon: _jsx(CodeOutlined, {}), children: "\u751F\u6210\u4EE3\u7801" })), activeTab === 'code' && (_jsx(Button, { type: "primary", onClick: runAnalysis, loading: running, icon: _jsx(PlayCircleOutlined, {}), children: "\u8FD0\u884C\u5206\u6790" }))] }), children: _jsx(Tabs, { activeKey: activeTab, onChange: setActiveTab, centered: true, tabBarStyle: { background: 'var(--bg-component)', borderBottom: '1px solid var(--border-color)' }, items: [
                        {
                            key: 'config',
                            label: '配置',
                            children: (_jsx("div", { style: { padding: '24px' }, children: _jsx(Form, { layout: "vertical", children: selectedTool?.params.map((param) => (_jsx(Form.Item, { label: _jsx(Text, { style: { color: 'var(--text-secondary)' }, children: param.label }), required: param.required, tooltip: param.tooltip, children: param.type === 'column' || param.type === 'multi-column' ? (_jsx(Select, { mode: param.type === 'multi-column' ? 'multiple' : undefined, placeholder: "\u9009\u62E9\u5217", value: config[param.name], onChange: v => setConfig({ ...config, [param.name]: v }), showSearch: true, dropdownStyle: { background: 'var(--bg-component)' }, style: { width: '100%' }, children: columns.map(c => _jsx(Option, { value: c, children: c }, c)) })) : (_jsx(Input, { value: config[param.name], onChange: e => setConfig({ ...config, [param.name]: e.target.value }) })) }, param.name))) }) }))
                        },
                        {
                            key: 'code',
                            label: '生成的代码',
                            children: (_jsx("div", { style: { height: 'calc(100vh - 200px)' }, children: _jsx(Editor, { height: "100%", defaultLanguage: "python", value: generatedCode, onChange: (val) => setGeneratedCode(val || ''), theme: isDarkMode ? "vs-dark" : "light", options: {
                                        minimap: { enabled: false },
                                        fontSize: 14,
                                        padding: { top: 16 }
                                    } }) }))
                        },
                        {
                            key: 'result',
                            label: '结果',
                            children: (_jsxs("div", { style: { padding: '24px', color: '#e0e0e0' }, children: [running && _jsx("div", { style: { textAlign: 'center', padding: 40 }, children: _jsx(Spin, { size: "large", tip: "\u6B63\u5728\u8FD0\u884C\u5206\u6790..." }) }), !running && logs.length === 0 && _jsx(Empty, { description: "\u6682\u65E0\u7ED3\u679C" }), plots.length > 0 && (_jsxs("div", { style: { marginBottom: 24 }, children: [_jsx(Divider, { orientation: "left", style: { borderColor: '#333', color: '#888' }, children: "\u53EF\u89C6\u5316\u7ED3\u679C" }), _jsx(Row, { gutter: [16, 16], children: plots.map((url, i) => (_jsx(Col, { span: 24, children: _jsx("div", { style: { background: '#1f1f1f', padding: 8, borderRadius: 8 }, children: _jsx("img", { src: url, style: { width: '100%', borderRadius: 4 }, alt: "\u5206\u6790\u56FE\u8868" }) }) }, i))) })] })), logs.length > 0 && (_jsxs("div", { children: [_jsx(Divider, { orientation: "left", style: { borderColor: '#333', color: '#888' }, children: "\u63A7\u5236\u53F0\u8F93\u51FA" }), _jsxs("div", { style: {
                                                    background: '#000',
                                                    padding: '16px',
                                                    borderRadius: '8px',
                                                    fontFamily: 'monospace',
                                                    fontSize: '13px',
                                                    maxHeight: '400px',
                                                    overflowY: 'auto',
                                                    border: '1px solid #333'
                                                }, children: [logs.map((log, i) => (_jsx("div", { style: { whiteSpace: 'pre-wrap', marginBottom: 4 }, children: log }, i))), _jsx("div", { ref: logEndRef })] })] }))] }))
                        }
                    ] }) })] }));
}
