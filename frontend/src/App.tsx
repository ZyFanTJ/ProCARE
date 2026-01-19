import { Layout, Menu, Input, Space, Avatar, Button, ConfigProvider, theme, AutoComplete } from 'antd'
import { Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Wizard from './pages/Wizard'
import ReportViewer from './pages/ReportViewer'
import Projects from './pages/Projects'
import Files from './pages/Files'
import Reports from './pages/Reports'
import Templates from './pages/Templates'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import ReportComposer from './pages/ReportComposer'
import ProjectDetail from './pages/ProjectDetail'
import { applySettings, loadSettings, onSettingsChange, SystemSettings } from './utils/systemSettings'
import { DashboardOutlined, PlusCircleOutlined, ProjectOutlined, FolderOpenOutlined, FileTextOutlined, AppstoreOutlined, SettingOutlined, SearchOutlined, BellOutlined, UserOutlined } from '@ant-design/icons'
import './assets/layout.css'
import CoPilot from './components/CoPilot'
import { listJobs } from './api/research'

const { Header, Sider, Content, Footer } = Layout

export default function App() {
  const [settings, setSettings] = useState<SystemSettings>(loadSettings())
  const location = useLocation()
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')
  const [searchOptions, setSearchOptions] = useState<Array<{ value: string; label: string }>>([])
  const [jobsCache, setJobsCache] = useState<Array<{ job_id: string; topic?: string }>>([])

  useEffect(() => {
    applySettings(settings)
  }, [settings])

  const getSelectedKey = () => {
    const p = location.pathname
    if (p.startsWith('/dashboard')) return 'dashboard'
    if (p === '/' || p.startsWith('/wizard')) return 'wizard'
    if (p.startsWith('/projects')) return 'projects'
    if (p.startsWith('/files')) return 'files'
    if (p.startsWith('/reports')) return 'reports'
    if (p.startsWith('/templates')) return 'templates'
    if (p.startsWith('/settings')) return 'settings'
    return 'dashboard'
  }

  useEffect(() => {
    const off = onSettingsChange((s) => setSettings(s))
    return () => off()
  }, [])

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
      <ConfigProvider
        theme={{
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
        }}
      >
      <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} theme="light" className="app-sider" style={{ position: 'fixed', left: 0, top: 0, bottom: 0, height: '100vh', overflow: 'auto', boxShadow: '2px 0 8px rgba(0,0,0,0.06)' }}>
        <div style={{ padding: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
          {settings.logoDataUrl && (
            <img src={settings.logoDataUrl} alt="logo" style={{ width: 28, height: 28, objectFit: 'contain' }} />
          )}
          <span className="logo-title">{settings.systemName || 'RWS研究系统'}</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[getSelectedKey()]}
          items={[
            { key: 'dashboard', icon: <DashboardOutlined />, label: <Link to="/dashboard">仪表盘</Link> },
            { key: 'wizard', icon: <PlusCircleOutlined />, label: <Link to="/">新建研究</Link> },
            { key: 'projects', icon: <ProjectOutlined />, label: <Link to="/projects">研究项目</Link> },
            { key: 'files', icon: <FolderOpenOutlined />, label: <Link to="/files">文件管理</Link> },
            // 合并“报告中心”到“研究项目”，保留路由别名但不在菜单显示
            { key: 'templates', icon: <AppstoreOutlined />, label: <Link to="/templates">模板管理</Link> },
            { key: 'settings', icon: <SettingOutlined />, label: <Link to="/settings">系统设置</Link> },
          ]}
        />
      </Sider>
      <Layout style={{ marginLeft: 200 }}>
        <Header className="app-header" style={{ position: 'sticky', top: 0, zIndex: 10, padding: '0 24px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
            <AutoComplete style={{ width: 360 }} options={searchOptions} value={searchTerm} onChange={(v) => doSearch(v)} onSelect={(v) => onSearchSelect(v)}>
              <Input placeholder="搜索研究项目..." prefix={<SearchOutlined />} allowClear onPressEnter={onSearchEnter} />
            </AutoComplete>
            <Space>
              <Button type="text" icon={<BellOutlined />} />
              <Link to="/settings"><Button type="text" icon={<SettingOutlined />} /></Link>
              <Avatar size={32} icon={<UserOutlined />} />
            </Space>
          </div>
        </Header>
        <Content style={{ margin: 24 }}>
          <div key={location.pathname} className="route-animate">
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/" element={<Wizard />} />
            <Route path="/report/:jobId" element={<ReportViewer />} />
            <Route path="/compose/:jobId" element={<ReportComposer />} />
            <Route path="/project/:jobId" element={<ProjectDetail />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/files" element={<Files />} />
            <Route path="/reports" element={<Projects />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
          </div>
        </Content>
        <Footer style={{ textAlign: 'center', background: 'transparent' }}>
          {settings.footerText || '© 2025 AI4Research 系统'}
        </Footer>
        <CoPilot />
      </Layout>
    </Layout>
    </ConfigProvider>
  )
}