import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Layout, Menu, Input, Space, Avatar, Button, ConfigProvider, theme, AutoComplete } from 'antd';
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Wizard from './pages/Wizard';
import ReportViewer from './pages/ReportViewer';
import Projects from './pages/Projects';
import Files from './pages/Files';
import Templates from './pages/Templates';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import ReportComposer from './pages/ReportComposer';
import ProjectDetail from './pages/ProjectDetail';
import { applySettings, loadSettings, onSettingsChange } from './utils/systemSettings';
import { DashboardOutlined, PlusCircleOutlined, ProjectOutlined, FolderOpenOutlined, AppstoreOutlined, SettingOutlined, SearchOutlined, BellOutlined, UserOutlined } from '@ant-design/icons';
import './assets/layout.css';
import CoPilot from './components/CoPilot';
import { listJobs } from './api/research';
const { Header, Sider, Content, Footer } = Layout;
export default function App() {
    const [settings, setSettings] = useState(loadSettings());
    const location = useLocation();
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [searchOptions, setSearchOptions] = useState([]);
    const [jobsCache, setJobsCache] = useState([]);
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
        if (p.startsWith('/files'))
            return 'files';
        if (p.startsWith('/reports'))
            return 'reports';
        if (p.startsWith('/templates'))
            return 'templates';
        if (p.startsWith('/settings'))
            return 'settings';
        return 'dashboard';
    };
    useEffect(() => {
        const off = onSettingsChange((s) => setSettings(s));
        return () => off();
    }, []);
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
    return (_jsx(ConfigProvider, { theme: {
            token: {
                colorPrimary: '#3b82f6',
                colorInfo: '#0ea5e9',
                colorLink: '#3b82f6',
                borderRadius: 10,
                colorBgLayout: '#f5f7fb',
                colorBgContainer: '#ffffff',
                colorBorder: '#e5e7eb',
                colorText: '#111827',
            },
            algorithm: theme.compactAlgorithm,
        }, children: _jsxs(Layout, { style: { minHeight: '100vh' }, children: [_jsxs(Sider, { width: 200, theme: "light", className: "app-sider", style: { position: 'fixed', left: 0, top: 0, bottom: 0, height: '100vh', overflow: 'auto', boxShadow: '2px 0 8px rgba(0,0,0,0.06)' }, children: [_jsxs("div", { style: { padding: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }, children: [settings.logoDataUrl && (_jsx("img", { src: settings.logoDataUrl, alt: "logo", style: { width: 28, height: 28, objectFit: 'contain' } })), _jsx("span", { className: "logo-title", children: settings.systemName || 'RWS研究系统' })] }), _jsx(Menu, { mode: "inline", selectedKeys: [getSelectedKey()], items: [
                                { key: 'dashboard', icon: _jsx(DashboardOutlined, {}), label: _jsx(Link, { to: "/dashboard", children: "\u4EEA\u8868\u76D8" }) },
                                { key: 'wizard', icon: _jsx(PlusCircleOutlined, {}), label: _jsx(Link, { to: "/", children: "\u65B0\u5EFA\u7814\u7A76" }) },
                                { key: 'projects', icon: _jsx(ProjectOutlined, {}), label: _jsx(Link, { to: "/projects", children: "\u7814\u7A76\u9879\u76EE" }) },
                                { key: 'files', icon: _jsx(FolderOpenOutlined, {}), label: _jsx(Link, { to: "/files", children: "\u6587\u4EF6\u7BA1\u7406" }) },
                                // 合并“报告中心”到“研究项目”，保留路由别名但不在菜单显示
                                { key: 'templates', icon: _jsx(AppstoreOutlined, {}), label: _jsx(Link, { to: "/templates", children: "\u6A21\u677F\u7BA1\u7406" }) },
                                { key: 'settings', icon: _jsx(SettingOutlined, {}), label: _jsx(Link, { to: "/settings", children: "\u7CFB\u7EDF\u8BBE\u7F6E" }) },
                            ] })] }), _jsxs(Layout, { style: { marginLeft: 200 }, children: [_jsx(Header, { className: "app-header", style: { position: 'sticky', top: 0, zIndex: 10, padding: '0 24px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }, children: _jsxs("div", { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }, children: [_jsx(AutoComplete, { style: { width: 360 }, options: searchOptions, value: searchTerm, onChange: (v) => doSearch(v), onSelect: (v) => onSearchSelect(v), children: _jsx(Input, { placeholder: "\u641C\u7D22\u7814\u7A76\u9879\u76EE...", prefix: _jsx(SearchOutlined, {}), allowClear: true, onPressEnter: onSearchEnter }) }), _jsxs(Space, { children: [_jsx(Button, { type: "text", icon: _jsx(BellOutlined, {}) }), _jsx(Link, { to: "/settings", children: _jsx(Button, { type: "text", icon: _jsx(SettingOutlined, {}) }) }), _jsx(Avatar, { size: 32, icon: _jsx(UserOutlined, {}) })] })] }) }), _jsx(Content, { style: { margin: 24 }, children: _jsx("div", { className: "route-animate", children: _jsxs(Routes, { children: [_jsx(Route, { path: "/dashboard", element: _jsx(Dashboard, {}) }), _jsx(Route, { path: "/", element: _jsx(Wizard, {}) }), _jsx(Route, { path: "/report/:jobId", element: _jsx(ReportViewer, {}) }), _jsx(Route, { path: "/compose/:jobId", element: _jsx(ReportComposer, {}) }), _jsx(Route, { path: "/project/:jobId", element: _jsx(ProjectDetail, {}) }), _jsx(Route, { path: "/projects", element: _jsx(Projects, {}) }), _jsx(Route, { path: "/files", element: _jsx(Files, {}) }), _jsx(Route, { path: "/reports", element: _jsx(Projects, {}) }), _jsx(Route, { path: "/templates", element: _jsx(Templates, {}) }), _jsx(Route, { path: "/settings", element: _jsx(Settings, {}) })] }) }, location.pathname) }), _jsx(Footer, { style: { textAlign: 'center', background: 'transparent' }, children: settings.footerText || '© 2025 AI4Research 系统' }), _jsx(CoPilot, {})] })] }) }));
}
