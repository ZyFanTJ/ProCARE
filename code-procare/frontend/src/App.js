import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Layout, Menu, Input, Space, Avatar, Button, ConfigProvider, AutoComplete, App as AntdApp } from 'antd';
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Wizard from './pages/Wizard';
import ReportViewer from './pages/ReportViewer';
import Projects from './pages/Projects';
import Templates from './pages/Templates';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import ReportComposer from './pages/ReportComposer';
import PaperGenerator from './pages/PaperGenerator';
import ProjectDetail from './pages/ProjectDetail';
import DataPrep from './pages/DataPrep';
import KnowledgeBase from './pages/KnowledgeBase';
import Notebook from './pages/Notebook';
import StatsToolbox from './pages/StatsToolbox';
import AuditLogs from './pages/AuditLogs';
import DataManager from './pages/DataManager';
import UserProfile from './pages/UserProfile';
import NotificationCenter from './components/NotificationCenter';
import { applySettings, loadSettings, onSettingsChange, saveSettingsToBackend } from './utils/systemSettings';
import { DashboardOutlined, PlusCircleOutlined, ProjectOutlined, AppstoreOutlined, SettingOutlined, SearchOutlined, UserOutlined, SunOutlined, MoonOutlined, ToolOutlined, ReadOutlined, CodeOutlined, BarChartOutlined, SafetyCertificateOutlined, DatabaseOutlined } from '@ant-design/icons';
import './assets/layout.css';
import './assets/scifi-theme.css';
import './assets/journal-theme.css';
import RightCopilotSidebar from './components/RightCopilotSidebar';
import { listJobs } from './api/research';
import { getTheme } from './theme';
const { Header, Sider, Content, Footer } = Layout;
export default function App() {
    const [settings, setSettings] = useState(loadSettings());
    const location = useLocation();
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [searchOptions, setSearchOptions] = useState([]);
    const [jobsCache, setJobsCache] = useState([]);
    const [copilotOpen, setCopilotOpen] = useState(() => {
        try {
            const raw = localStorage.getItem('copilot_sidebar_open');
            return raw ? JSON.parse(raw) : true;
        }
        catch {
            return true;
        }
    });
    const copilotWidth = 420;
    // Derived from settings, default to dark
    const themeMode = settings.theme || 'dark';
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', themeMode);
    }, [themeMode]);
    useEffect(() => {
        applySettings(settings);
    }, [settings]);
    const getSelectedKey = () => {
        const p = location.pathname;
        if (p.startsWith('/dashboard'))
            return 'dashboard';
        if (p === '/' || p.startsWith('/wizard'))
            return 'wizard';
        if (p.startsWith('/projects'))
            return 'projects';
        if (p.startsWith('/dataprep'))
            return 'dataprep';
        if (p.startsWith('/knowledge'))
            return 'knowledge';
        if (p.startsWith('/notebook'))
            return 'notebook';
        if (p.startsWith('/stats'))
            return 'stats';
        if (p.startsWith('/data-manager'))
            return 'data_manager';
        if (p.startsWith('/reports'))
            return 'reports';
        if (p.startsWith('/templates'))
            return 'templates';
        if (p.startsWith('/audit'))
            return 'audit';
        if (p.startsWith('/settings'))
            return 'settings';
        return 'dashboard';
    };
    useEffect(() => {
        const off = onSettingsChange((s) => setSettings(s));
        return () => off();
    }, []);
    useEffect(() => {
        try {
            localStorage.setItem('copilot_sidebar_open', JSON.stringify(copilotOpen));
        }
        catch { }
    }, [copilotOpen]);
    const doSearch = async (q) => {
        setSearchTerm(q);
        const term = q.trim().toLowerCase();
        if (!term) {
            setSearchOptions([]);
            return;
        }
        let jobs = jobsCache;
        if (!jobs.length) {
            const res = await listJobs();
            jobs = res.jobs || [];
            setJobsCache(jobs);
        }
        const opts = jobs
            .filter((it) => (it.job_id || '').toLowerCase().includes(term) || (it.topic || '').toLowerCase().includes(term))
            .slice(0, 8)
            .map((it) => ({ value: it.job_id, label: `${it.job_id} ${it.topic ? '｜' + it.topic : ''}` }));
        setSearchOptions(opts);
    };
    const onSearchSelect = (jobId) => {
        if (!jobId)
            return;
        navigate(`/project/${jobId}`);
        setSearchOptions([]);
        setSearchTerm('');
    };
    const onSearchEnter = () => {
        if (searchOptions.length >= 1) {
            navigate(`/project/${searchOptions[0].value}`);
            setSearchOptions([]);
            setSearchTerm('');
        }
        else if (searchTerm.trim()) {
            navigate(`/projects?q=${encodeURIComponent(searchTerm.trim())}`);
        }
    };
    return (_jsx(ConfigProvider, { theme: getTheme(themeMode), children: _jsx(AntdApp, { children: _jsxs(Layout, { style: { minHeight: '100vh' }, className: "app-layout", children: [_jsxs(Sider, { width: 240, theme: themeMode === 'dark' ? 'dark' : 'light', className: "app-sider", style: { position: 'fixed', left: 0, top: 0, bottom: 0, height: '100vh', overflow: 'auto', borderRight: '1px solid var(--border-color)' }, children: [_jsxs("div", { style: { padding: '24px 16px 16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 12 }, children: [settings.logoDataUrl && (_jsx("img", { src: settings.logoDataUrl, alt: "logo", style: { width: 32, height: 32, objectFit: 'contain' } })), _jsx("span", { className: "logo-title", style: { fontSize: '1.1rem', letterSpacing: '-0.025em' }, children: settings.systemName || 'RWS研究系统' })] }), _jsx("div", { style: { padding: '0 12px', marginBottom: 16 }, children: _jsx(Button, { type: "primary", block: true, icon: _jsx(PlusCircleOutlined, {}), onClick: () => navigate('/'), size: "large", style: { borderRadius: 8, fontWeight: 500 }, children: "\u65B0\u5EFA\u7814\u7A76" }) }), _jsx(Menu, { mode: "inline", theme: themeMode === 'dark' ? 'dark' : 'light', selectedKeys: [getSelectedKey()], items: [
                                    { key: 'dashboard', icon: _jsx(DashboardOutlined, {}), label: _jsx(Link, { to: "/dashboard", children: "\u4EEA\u8868\u76D8" }) },
                                    {
                                        key: 'research_group',
                                        label: '研究中心',
                                        type: 'group',
                                        children: [
                                            { key: 'projects', icon: _jsx(ProjectOutlined, {}), label: _jsx(Link, { to: "/projects", children: "\u7814\u7A76\u9879\u76EE" }) },
                                        ]
                                    },
                                    {
                                        key: 'data_group',
                                        label: '数据与资产',
                                        type: 'group',
                                        children: [
                                            { key: 'data_manager', icon: _jsx(DatabaseOutlined, {}), label: _jsx(Link, { to: "/data-manager", children: "\u6570\u636E\u4E0E\u6587\u4EF6" }) },
                                            { key: 'dataprep', icon: _jsx(ToolOutlined, {}), label: _jsx(Link, { to: "/dataprep", children: "\u6570\u636E\u9884\u5904\u7406" }) },
                                            { key: 'knowledge', icon: _jsx(ReadOutlined, {}), label: _jsx(Link, { to: "/knowledge", children: "\u77E5\u8BC6\u5E93" }) },
                                            { key: 'templates', icon: _jsx(AppstoreOutlined, {}), label: _jsx(Link, { to: "/templates", children: "\u6A21\u677F\u7BA1\u7406" }) },
                                        ]
                                    },
                                    {
                                        key: 'tools_group',
                                        label: '分析工具',
                                        type: 'group',
                                        children: [
                                            { key: 'notebook', icon: _jsx(CodeOutlined, {}), label: _jsx(Link, { to: "/notebook", children: "\u4EE3\u7801\u6C99\u7BB1" }) },
                                            { key: 'stats', icon: _jsx(BarChartOutlined, {}), label: _jsx(Link, { to: "/stats", children: "\u7EDF\u8BA1\u5DE5\u5177" }) },
                                        ]
                                    },
                                    {
                                        key: 'system_group',
                                        label: '系统管理',
                                        type: 'group',
                                        children: [
                                            { key: 'audit', icon: _jsx(SafetyCertificateOutlined, {}), label: _jsx(Link, { to: "/audit", children: "\u7CFB\u7EDF\u5BA1\u8BA1" }) },
                                            { key: 'settings', icon: _jsx(SettingOutlined, {}), label: _jsx(Link, { to: "/settings", children: "\u7CFB\u7EDF\u8BBE\u7F6E" }) },
                                        ]
                                    },
                                ], style: { border: 'none', background: 'transparent' } })] }), _jsxs(Layout, { style: { marginLeft: 240, marginRight: copilotOpen ? copilotWidth : 56, transition: 'all 0.3s cubic-bezier(0.2, 0, 0, 1)' }, children: [_jsx(Header, { className: "app-header", style: { position: 'sticky', top: 0, zIndex: 100, padding: '0 32px' }, children: _jsxs("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', height: '100%' }, children: [_jsx(AutoComplete, { style: { width: 420 }, options: searchOptions, value: searchTerm, onSearch: (v) => doSearch(v), onSelect: (v) => onSearchSelect(v), children: _jsx(Input, { placeholder: "\u641C\u7D22\u7814\u7A76\u9879\u76EE\u3001\u62A5\u544A\u6216\u6587\u4EF6...", prefix: _jsx(SearchOutlined, { style: { color: 'var(--text-secondary)' } }), allowClear: true, onPressEnter: onSearchEnter, className: "search-input" }) }), _jsxs(Space, { size: 16, children: [_jsx(Button, { type: "text", icon: themeMode === 'dark' ? _jsx(SunOutlined, {}) : _jsx(MoonOutlined, {}), onClick: () => {
                                                        const newTheme = themeMode === 'dark' ? 'light' : 'dark';
                                                        const newSettings = {
                                                            ...settings,
                                                            theme: newTheme
                                                        };
                                                        // Optimistic update via setSettings will happen via onSettingsChange if we use saveSettingsLocal
                                                        // But here we can just call saveSettingsToBackend which calls saveSettingsLocal
                                                        saveSettingsToBackend(newSettings);
                                                    } }), _jsx(NotificationCenter, {}), _jsx(Avatar, { size: 36, icon: _jsx(UserOutlined, {}), style: { backgroundColor: 'var(--primary-color)', cursor: 'pointer' }, onClick: () => navigate('/profile') })] })] }) }), _jsx(Content, { style: { margin: '32px', minHeight: 'calc(100vh - 64px - 64px)' }, children: _jsx("div", { className: "route-animate", children: _jsxs(Routes, { children: [_jsx(Route, { path: "/dashboard", element: _jsx(Dashboard, {}) }), _jsx(Route, { path: "/", element: _jsx(Wizard, {}) }), _jsx(Route, { path: "/wizard", element: _jsx(Wizard, {}) }), _jsx(Route, { path: "/report/:jobId", element: _jsx(ReportViewer, {}) }), _jsx(Route, { path: "/compose/:jobId", element: _jsx(ReportComposer, {}) }), _jsx(Route, { path: "/project/:jobId/paper", element: _jsx(PaperGenerator, {}) }), _jsx(Route, { path: "/project/:jobId", element: _jsx(ProjectDetail, {}) }), _jsx(Route, { path: "/projects", element: _jsx(Projects, {}) }), _jsx(Route, { path: "/dataprep", element: _jsx(DataPrep, {}) }), _jsx(Route, { path: "/knowledge", element: _jsx(KnowledgeBase, {}) }), _jsx(Route, { path: "/notebook", element: _jsx(Notebook, {}) }), _jsx(Route, { path: "/stats", element: _jsx(StatsToolbox, {}) }), _jsx(Route, { path: "/audit", element: _jsx(AuditLogs, {}) }), _jsx(Route, { path: "/data-manager", element: _jsx(DataManager, {}) }), _jsx(Route, { path: "/profile", element: _jsx(UserProfile, {}) }), _jsx(Route, { path: "/reports", element: _jsx(Projects, {}) }), _jsx(Route, { path: "/templates", element: _jsx(Templates, {}) }), _jsx(Route, { path: "/settings", element: _jsx(Settings, {}) })] }) }, location.pathname) }), _jsx(Footer, { style: { textAlign: 'center', background: 'transparent', color: 'var(--text-secondary)' }, children: settings.footerText || '© 2025 AI4Research System' })] }), _jsx(RightCopilotSidebar, { open: copilotOpen, onToggle: () => setCopilotOpen((v) => !v), width: copilotWidth })] }) }) }));
}
