import { Layout, Menu, Input, Space, Avatar, Button, ConfigProvider, theme, AutoComplete, App as AntdApp } from 'antd'
import { Routes, Route, Link, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Wizard from './pages/Wizard'
import ReportViewer from './pages/ReportViewer'
import Projects from './pages/Projects'
import Templates from './pages/Templates'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import ReportComposer from './pages/ReportComposer'
import PaperGenerator from './pages/PaperGenerator'
import ProjectDetail from './pages/ProjectDetail'
import DataPrep from './pages/DataPrep'
import KnowledgeBase from './pages/KnowledgeBase'
import Notebook from './pages/Notebook'
import StatsToolbox from './pages/StatsToolbox'
import AuditLogs from './pages/AuditLogs'
import DataManager from './pages/DataManager'
import UserProfile from './pages/UserProfile'
import NotificationCenter from './components/NotificationCenter'
import { applySettings, loadSettings, onSettingsChange, SystemSettings, saveSettingsToBackend } from './utils/systemSettings'
import { DashboardOutlined, PlusCircleOutlined, ProjectOutlined, FolderOpenOutlined, FileTextOutlined, AppstoreOutlined, SettingOutlined, SearchOutlined, BellOutlined, UserOutlined, SunOutlined, MoonOutlined, ToolOutlined, ReadOutlined, CodeOutlined, BarChartOutlined, SafetyCertificateOutlined, DatabaseOutlined } from '@ant-design/icons'
import './assets/layout.css'
import './assets/scifi-theme.css'
import './assets/journal-theme.css'
import RightCopilotSidebar from './components/RightCopilotSidebar'
import { listJobs } from './api/research'
import { getTheme } from './theme'

const { Header, Sider, Content, Footer } = Layout

export default function App() {
  const [settings, setSettings] = useState<SystemSettings>(loadSettings())
  const location = useLocation()
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')
  const [searchOptions, setSearchOptions] = useState<Array<{ value: string; label: string }>>([])
  const [jobsCache, setJobsCache] = useState<Array<{ job_id: string; topic?: string }>>([])
  const [copilotOpen, setCopilotOpen] = useState<boolean>(() => {
    try { const raw = localStorage.getItem('copilot_sidebar_open'); return raw ? JSON.parse(raw) : true } catch { return true }
  })
  const copilotWidth = 420
  
  // Derived from settings, default to dark
  const themeMode = settings.theme || 'dark'

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', themeMode)
  }, [themeMode])

  useEffect(() => {
    applySettings(settings)
  }, [settings])

  const getSelectedKey = () => {
    const p = location.pathname
    if (p.startsWith('/dashboard')) return 'dashboard'
    if (p === '/' || p.startsWith('/wizard')) return 'wizard'
    if (p.startsWith('/projects')) return 'projects'
    if (p.startsWith('/dataprep')) return 'dataprep'
    if (p.startsWith('/knowledge')) return 'knowledge'
    if (p.startsWith('/notebook')) return 'notebook'
    if (p.startsWith('/stats')) return 'stats'
    if (p.startsWith('/data-manager')) return 'data_manager'
    if (p.startsWith('/reports')) return 'reports'
    if (p.startsWith('/templates')) return 'templates'
    if (p.startsWith('/audit')) return 'audit'
    if (p.startsWith('/settings')) return 'settings'
    return 'dashboard'
  }

  useEffect(() => {
    const off = onSettingsChange((s) => setSettings(s))
    return () => off()
  }, [])

  useEffect(() => {
    try { localStorage.setItem('copilot_sidebar_open', JSON.stringify(copilotOpen)) } catch {}
  }, [copilotOpen])

  const doSearch = async (q: string) => {
    setSearchTerm(q)
    const term = q.trim().toLowerCase()
    if (!term) { setSearchOptions([]); return }
    let jobs = jobsCache
    if (!jobs.length) {
      const res = await listJobs()
      jobs = res.jobs || []
      setJobsCache(jobs as any)
    }
    const opts = jobs
      .filter((it) => (it.job_id || '').toLowerCase().includes(term) || (it.topic || '').toLowerCase().includes(term))
      .slice(0, 8)
      .map((it) => ({ value: it.job_id, label: `${it.job_id} ${it.topic ? '｜' + it.topic : ''}` }))
    setSearchOptions(opts)
  }

  const onSearchSelect = (jobId: string) => {
    if (!jobId) return
    navigate(`/project/${jobId}`)
    setSearchOptions([])
    setSearchTerm('')
  }

  const onSearchEnter = () => {
    if (searchOptions.length >= 1) {
      navigate(`/project/${searchOptions[0].value}`)
      setSearchOptions([])
      setSearchTerm('')
    } else if (searchTerm.trim()) {
      navigate(`/projects?q=${encodeURIComponent(searchTerm.trim())}`)
    }
  }

  return (
    <ConfigProvider theme={getTheme(themeMode)}>
    <AntdApp>
    <Layout style={{ minHeight: '100vh' }} className="app-layout">
    <Sider width={240} theme={themeMode === 'dark' ? 'dark' : 'light'} className="app-sider" style={{ position: 'fixed', left: 0, top: 0, bottom: 0, height: '100vh', overflow: 'auto', borderRight: '1px solid var(--border-color)' }}>
        <div style={{ padding: '24px 16px 16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 12 }}>
          {settings.logoDataUrl && (
            <img src={settings.logoDataUrl} alt="logo" style={{ width: 32, height: 32, objectFit: 'contain' }} />
          )}
          <span className="logo-title" style={{ fontSize: '1.1rem', letterSpacing: '-0.025em' }}>{settings.systemName || 'RWS研究系统'}</span>
        </div>
        <div style={{ padding: '0 12px', marginBottom: 16 }}>
             <Button type="primary" block icon={<PlusCircleOutlined />} onClick={() => navigate('/')} size="large" style={{ borderRadius: 8, fontWeight: 500 }}>
               新建研究
             </Button>
        </div>
        <Menu
          mode="inline"
          theme={themeMode === 'dark' ? 'dark' : 'light'}
          selectedKeys={[getSelectedKey()]}
          items={[
            { key: 'dashboard', icon: <DashboardOutlined />, label: <Link to="/dashboard">仪表盘</Link> },
            { 
              key: 'research_group', 
              label: '研究中心', 
              type: 'group',
              children: [
                { key: 'projects', icon: <ProjectOutlined />, label: <Link to="/projects">研究项目</Link> },
              ]
            },
            { 
              key: 'data_group', 
              label: '数据与资产', 
              type: 'group',
              children: [
                { key: 'data_manager', icon: <DatabaseOutlined />, label: <Link to="/data-manager">数据与文件</Link> },
                { key: 'dataprep', icon: <ToolOutlined />, label: <Link to="/dataprep">数据预处理</Link> },
                { key: 'knowledge', icon: <ReadOutlined />, label: <Link to="/knowledge">知识库</Link> },
                { key: 'templates', icon: <AppstoreOutlined />, label: <Link to="/templates">模板管理</Link> },
              ]
            },
            { 
              key: 'tools_group', 
              label: '分析工具', 
              type: 'group',
              children: [
                { key: 'notebook', icon: <CodeOutlined />, label: <Link to="/notebook">代码沙箱</Link> },
                { key: 'stats', icon: <BarChartOutlined />, label: <Link to="/stats">统计工具</Link> },
              ]
            },
            { 
              key: 'system_group', 
              label: '系统管理', 
              type: 'group',
              children: [
                { key: 'audit', icon: <SafetyCertificateOutlined />, label: <Link to="/audit">系统审计</Link> },
                { key: 'settings', icon: <SettingOutlined />, label: <Link to="/settings">系统设置</Link> },
              ]
            },
          ]}
          style={{ border: 'none', background: 'transparent' }}
        />
      </Sider>
      <Layout style={{ marginLeft: 240, marginRight: copilotOpen ? copilotWidth : 56, transition: 'all 0.3s cubic-bezier(0.2, 0, 0, 1)' }}>
        <Header className="app-header" style={{ position: 'sticky', top: 0, zIndex: 100, padding: '0 32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', height: '100%' }}>
            <AutoComplete style={{ width: 420 }} options={searchOptions} value={searchTerm} onSearch={(v) => doSearch(v)} onSelect={(v) => onSearchSelect(v)}>
              <Input 
                placeholder="搜索研究项目、报告或文件..." 
                prefix={<SearchOutlined style={{ color: 'var(--text-secondary)' }} />} 
                allowClear 
                onPressEnter={onSearchEnter} 
                className="search-input"
              />
            </AutoComplete>
            <Space size={16}>
              <Button type="text" icon={themeMode === 'dark' ? <SunOutlined /> : <MoonOutlined />} onClick={() => {
                const newTheme = themeMode === 'dark' ? 'light' : 'dark'
                const newSettings = { 
                  ...settings, 
                  theme: newTheme as 'light' | 'dark' 
                }
                // Optimistic update via setSettings will happen via onSettingsChange if we use saveSettingsLocal
                // But here we can just call saveSettingsToBackend which calls saveSettingsLocal
                saveSettingsToBackend(newSettings)
              }} />
              <NotificationCenter />
              <Avatar size={36} icon={<UserOutlined />} style={{ backgroundColor: 'var(--primary-color)', cursor: 'pointer' }} onClick={() => navigate('/profile')} />
            </Space>
          </div>
        </Header>
        <Content style={{ margin: '32px', minHeight: 'calc(100vh - 64px - 64px)' }}>
          <div key={location.pathname} className="route-animate">
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/wizard" element={<Wizard />} />
            <Route path="/report/:jobId" element={<ReportViewer />} />
            <Route path="/compose/:jobId" element={<ReportComposer />} />
            <Route path="/project/:jobId/paper" element={<PaperGenerator />} />
            <Route path="/project/:jobId" element={<ProjectDetail />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/dataprep" element={<DataPrep />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
            <Route path="/notebook" element={<Notebook />} />
            <Route path="/stats" element={<StatsToolbox />} />
            <Route path="/audit" element={<AuditLogs />} />
            <Route path="/data-manager" element={<DataManager />} />
            <Route path="/profile" element={<UserProfile />} />
            <Route path="/reports" element={<Projects />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
          </div>
        </Content>
        <Footer style={{ textAlign: 'center', background: 'transparent', color: 'var(--text-secondary)' }}>
          {settings.footerText || '© 2025 AI4Research System'}
        </Footer>
      </Layout>
      <RightCopilotSidebar open={copilotOpen} onToggle={() => setCopilotOpen((v) => !v)} width={copilotWidth} />
    </Layout>
    </AntdApp>
    </ConfigProvider>
  )
}
