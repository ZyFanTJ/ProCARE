import { useState, useEffect, useRef, useMemo } from 'react'
import { Typography, Select, Button, Space, Card, Splitter, Tabs, Tree, Empty, Tooltip, message, Tag, List, theme } from 'antd'
import { 
  PlayCircleOutlined, 
  SaveOutlined, 
  FileTextOutlined, 
  BarChartOutlined, 
  CodeOutlined,
  DeleteOutlined,
  DatabaseOutlined
} from '@ant-design/icons'
import Editor, { useMonaco } from '@monaco-editor/react'
import { listJobs, fetchExcelInfo, streamSandboxCode, fetchAnalysisCode } from '../api/research'
import css from './Notebook.module.css'

const { Title, Text } = Typography
const { Option } = Select

// --- Types ---
interface Job {
  job_id: string
  topic?: string
}

export default function Notebook() {
  const { token } = theme.useToken()
  const isDark = token.colorTextBase === '#f1f5f9' // Check if text is light (dark mode)

  // --- Styles (Legacy/Inline) ---
  const styles = {
    terminal: {
      background: isDark ? '#000' : '#f5f5f5',
      color: isDark ? '#00ff00' : '#333',
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      fontSize: '13px',
      padding: '12px',
      flex: 1,
      overflowY: 'auto' as const,
      whiteSpace: 'pre-wrap' as const
    }
  }

  // State
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [excelInfo, setExcelInfo] = useState<any>(null)
  
  const [code, setCode] = useState<string>('# 请选择一个项目以开始编码...')
  const [logs, setLogs] = useState<string[]>([])
  const [plots, setPlots] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [activeTab, setActiveTab] = useState('console')
  
  const monaco = useMonaco()
  const logEndRef = useRef<HTMLDivElement>(null)

  // Effects
  useEffect(() => {
    listJobs().then(res => setJobs(res.jobs || [])).catch(console.error)
  }, [])

  useEffect(() => {
    if (!selectedJobId) {
        setCode('# 请选择一个项目以开始编码...')
        setExcelInfo(null)
        return
    }
    
    // Fetch Data Profile
    fetchExcelInfo(selectedJobId).then(info => {
        setExcelInfo(info)
    }).catch(console.error)

    // Fetch Code
    fetchAnalysisCode(selectedJobId).then(c => {
        if (c) setCode(c)
        else setCode(getDefaultCode(selectedJobId, null))
    }).catch(() => setCode(getDefaultCode(selectedJobId, null)))

  }, [selectedJobId])

  useEffect(() => {
    if (activeTab === 'console' && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, activeTab])

  // Sync code to global context for Copilot
  useEffect(() => {
    if (code) {
      localStorage.setItem('copilot_active_context', JSON.stringify({
        type: 'notebook',
        content: code,
        timestamp: Date.now()
      }))
    }
    return () => {
       localStorage.removeItem('copilot_active_context')
     }
   }, [code])

  // Helpers
  const getDefaultCode = (jobId: string, info: any) => {
      const path = info?.path?.replace(/\\/g, '/') || 'data.xlsx'
      return `import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# 设置图表样式
sns.set_theme(style="darkgrid")
plt.rcParams['figure.figsize'] = [10, 6]
plt.rcParams['figure.dpi'] = 100

# 确保图表目录存在
os.makedirs("plots", exist_ok=True)

# 加载数据
# 脚本在任务目录下运行
excel_path = r"${path}" 
print(f"正在从 {excel_path} 加载数据...")

try:
    df = pd.read_excel(excel_path)
    print("数据加载成功！")
    print(df.head())
    print("-" * 40)
    print(df.info())
    
except Exception as e:
    print(f"加载数据出错: {e}")
`
  }

  const handleRun = async () => {
    if (!selectedJobId) return
    setRunning(true)
    setLogs([])
    setPlots([])
    setActiveTab('console')
    
    await streamSandboxCode(selectedJobId, code, (chunk) => {
        setLogs(prev => [...prev, chunk])
        // Plot detection
        const plotMatches = [...chunk.matchAll(/Saved plot: (.*\.png)/g)]
        if (plotMatches.length > 0) {
            const newPlots: string[] = []
            plotMatches.forEach(match => {
                const fullPath = match[1].trim()
                const filename = fullPath.split(/[\\/]/).pop()
                if (filename) {
                    // Add timestamp to prevent caching
                    const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/api\/?$/, '')
                    const url = `${baseUrl}/static/jobs/${selectedJobId}/plots/${filename}?t=${Date.now()}`
                    newPlots.push(url)
                }
            })
            if (newPlots.length > 0) {
                setPlots(prev => [...prev, ...newPlots])
            }
        }
    }, (status) => {
        if (status === 'done' || status === 'error' || status === 'interrupted') {
            setRunning(false)
            if (status === 'done') message.success('执行完成')
            if (status === 'error') message.error('执行失败')
        }
    })
  }

  const columns = useMemo(() => {
    if (!excelInfo) return []
    let cols: string[] = []
    const dtypes = (excelInfo as any)?.low?.dtypes || (excelInfo as any)?.dtypes || {}
    cols = Object.keys(dtypes)
    if (cols.length === 0 && excelInfo.sheets && excelInfo.sheets.length > 0) {
        const firstSheet = excelInfo.sheets[0]
        const sheetProfile = (excelInfo as any)[firstSheet] || (excelInfo as any).profile?.[firstSheet]
        if (sheetProfile) {
             const sheetDtypes = sheetProfile?.low?.dtypes || sheetProfile?.dtypes || {}
             cols = Object.keys(sheetDtypes)
        }
    }
    return cols
  }, [excelInfo])

  return (
    <div className={css.container} data-theme={isDark ? 'dark' : 'light'}>
      {/* Sidebar */}
      <div className={css.sidebar}>
        <div className={css.sidebarHeader}>
           <CodeOutlined style={{ fontSize: 20, color: 'var(--nb-accent)' }} />
           <span className={css.title}>项目列表</span>
        </div>
        <div className={css.jobList}>
           {jobs.map(j => (
              <div 
                key={j.job_id} 
                className={`${css.jobItem} ${selectedJobId === j.job_id ? css.active : ''}`}
                onClick={() => setSelectedJobId(j.job_id)}
              >
                 <div className={css.jobId}>{j.job_id}</div>
                 <div className={css.jobTopic}>{j.topic || '研究项目'}</div>
              </div>
           ))}
        </div>
      </div>

      {/* Main Editor Area */}
      <div className={css.editorArea}>
        {/* Toolbar */}
        <div className={css.toolbar}>
           <Space>
               <Title level={4} style={{ color: 'var(--nb-text)', margin: 0 }}>
                   交互式笔记本
               </Title>
               {selectedJobId && <Tag color="blue">{selectedJobId}</Tag>}
           </Space>
           <Space>
               <Button 
                   type="primary" 
                   icon={<PlayCircleOutlined />} 
                   loading={running}
                   onClick={handleRun}
                   disabled={!selectedJobId}
                   style={{ background: token.colorSuccess, borderColor: token.colorSuccess }}
               >
                   运行代码
               </Button>
               <Button 
                   icon={<SaveOutlined />} 
                   type="text" 
                   style={{ color: 'var(--nb-text-secondary)' }}
                   disabled={!selectedJobId}
                >
                    保存
                </Button>
               <Button 
                   icon={<DeleteOutlined />} 
                   type="text" 
                   style={{ color: 'var(--nb-text-secondary)' }} 
                   onClick={() => { setLogs([]); setPlots([]) }}
                   disabled={!selectedJobId}
                >
                    清空输出
                </Button>
           </Space>
        </div>

        {/* Content */}
        {!selectedJobId ? (
            <div className={css.landing}>
                <div className={css.landingTitle}>选择一个项目以开始编码</div>
                <div className={css.landingDesc}>
                    从左侧边栏选择一个研究项目，或在下方选择以打开交互式笔记本环境。
                </div>
                <div className={css.projectGrid}>
                    {jobs.map(j => (
                        <div key={j.job_id} className={css.projectCard} onClick={() => setSelectedJobId(j.job_id)}>
                            <CodeOutlined className={css.cardIcon} />
                            <div className={css.cardTitle}>{j.job_id}</div>
                            <div className={css.cardMeta}>
                                <div className={`${css.statusDot} ${css.success}`} />
                                {j.topic || '研究项目'}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        ) : (
            <Splitter style={{ flex: 1 }}>
                {/* Left: Variables & Editor */}
                <Splitter.Panel defaultSize="60%" min="20%">
                    <Splitter>
                        {/* Variables Sidebar */}
                        <Splitter.Panel defaultSize="20%" min="10%" max="30%" style={{ background: token.colorBgLayout, borderRight: `1px solid ${token.colorBorder}` }}>
                            <div style={{ padding: '12px', borderBottom: `1px solid ${token.colorBorder}` }}>
                                <Text strong style={{ color: token.colorText }}><DatabaseOutlined /> 变量</Text>
                            </div>
                            <div style={{ padding: '12px' }}>
                                {columns.length > 0 ? (
                                    <List
                                        size="small"
                                        dataSource={columns}
                                        renderItem={item => (
                                            <List.Item style={{ padding: '4px 0', border: 'none' }}>
                                                <Tag color="blue" style={{ marginRight: 0, width: '100%', textAlign: 'left' }}>{item}</Tag>
                                            </List.Item>
                                        )}
                                    />
                                ) : (
                                    <Text style={{ color: token.colorTextSecondary, fontSize: '12px' }}>未检测到列</Text>
                                )}
                            </div>
                        </Splitter.Panel>
                        
                        {/* Editor */}
                        <Splitter.Panel>
                             <Editor
                                height="100%"
                                defaultLanguage="python"
                                value={code}
                                onChange={(val) => setCode(val || '')}
                                theme={isDark ? "vs-dark" : "light"}
                                options={{
                                    minimap: { enabled: false },
                                    fontSize: 14,
                                    padding: { top: 16 },
                                    scrollBeyondLastLine: false
                                }}
                            />
                        </Splitter.Panel>
                    </Splitter>
                </Splitter.Panel>
                
                {/* Right: Output */}
                <Splitter.Panel style={{ background: token.colorBgLayout, display: 'flex', flexDirection: 'column' }}>
                     <Tabs 
                        className={css.tabs}
                        activeKey={activeTab} 
                        onChange={setActiveTab} 
                        type="card"
                        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                        tabBarStyle={{ background: token.colorBgContainer, margin: 0, borderBottom: `1px solid ${token.colorBorder}` }}
                        items={[
                            {
                                key: 'console',
                                label: <span><FileTextOutlined /> Console ({logs.length})</span>,
                                children: (
                                    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                                        <div style={styles.terminal}>
                                            {logs.length === 0 && <Text style={{ color: token.colorTextQuaternary }}>// Output will appear here...</Text>}
                                            {logs.map((log, i) => (
                                                <span key={i}>{log}</span>
                                            ))}
                                            <div ref={logEndRef} />
                                        </div>
                                    </div>
                                )
                            },
                            {
                                key: 'plots',
                                label: <span><BarChartOutlined /> Plots ({plots.length})</span>,
                                children: (
                                    <div style={{ height: '100%', overflowY: 'auto', padding: '16px', background: token.colorBgBase }}>
                                        {plots.length === 0 && <Empty description="No plots generated" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                                        {plots.map((url, i) => (
                                            <Card 
                                                key={i} 
                                                hoverable 
                                                style={{ marginBottom: 16, background: token.colorBgContainer, borderColor: token.colorBorder }}
                                                cover={<img alt="plot" src={url} />}
                                            >
                                                <Card.Meta 
                                                    title={<Text style={{ color: token.colorText }}>Plot {i + 1}</Text>} 
                                                    description={<Text ellipsis style={{ color: token.colorTextSecondary }}>{url.split('/').pop()}</Text>}
                                                />
                                            </Card>
                                        ))}
                                    </div>
                                )
                            }
                        ]}
                     />
                </Splitter.Panel>
            </Splitter>
        )}
      </div>
    </div>
  )
}
