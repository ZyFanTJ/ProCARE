
import { useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Typography, Space, Button, Badge, Carousel, Tag } from 'antd'
import type { CarouselRef } from 'antd/es/carousel'
import { useRef } from 'react'
import { listJobs, listUploads, listReports } from '../api/research'
import { 
  DashboardOutlined, 
  CheckCircleOutlined, 
  FolderOpenOutlined, 
  FileTextOutlined, 
  PlusCircleOutlined,
  ExperimentOutlined,
  RightOutlined
} from '@ant-design/icons'
import '../assets/dashboard.css'
import { loadSettings, DEFAULT_SETTINGS } from '../utils/systemSettings'
import { Link } from 'react-router-dom'

type JobItem = { job_id: string; topic?: string; success?: boolean; report_exists?: boolean; plots?: string[]; created_ts?: number }
type FileItem = { name: string; size?: number; created_ts?: number; url?: string }
type ReportItem = { job_id: string; report_url: string; static_url: string; created_ts?: number }

export default function Dashboard() {
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [files, setFiles] = useState<FileItem[]>([])
  const [reports, setReports] = useState<ReportItem[]>([])
  const [loading, setLoading] = useState(false)
  const [slides, setSlides] = useState<Array<{ title?: string; desc?: string; image?: string; link?: string }>>([])
  const carouselRef = useRef<CarouselRef | null>(null)
  const heroContentRef = useRef<HTMLDivElement | null>(null)
  const resizeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([listJobs(), listUploads(), listReports()])
      .then(([j, f, r]) => {
        setJobs(j.jobs || [])
        setFiles(f.files || [])
        setReports(r.reports || [])
      })
      .finally(() => setLoading(false))
    try {
      const s = loadSettings()
      // Ensure we have valid slides, filtering out empty/null entries
      let list = (s.carouselSlides || []).filter(x => x && (x.title || x.image))
      // If no valid slides from settings, use defaults
      if (list.length === 0) {
        list = DEFAULT_SETTINGS.carouselSlides || []
      }
      setSlides(list)
    } catch {
      setSlides(DEFAULT_SETTINGS.carouselSlides || [])
    }

    const ro = new ResizeObserver((entries) => {
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current)
      resizeTimerRef.current = window.setTimeout(() => {
        window.dispatchEvent(new Event('resize'))
      }, 120)
    })
    const el = heroContentRef.current
    if (el) {
      ro.observe(el)
    }

    return () => {
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current)
      ro.disconnect()
    }
  }, [])

  // Force carousel refresh when slides change
  useEffect(() => {
    if (carouselRef.current && slides.length > 0) {
      // Small delay to ensure DOM is updated
      setTimeout(() => {
        carouselRef.current?.goTo(0, false)
      }, 100)
    }
  }, [slides])

  const jobsTotal = jobs.length
  const jobsSuccess = jobs.filter(j => j.success === true).length
  const filesTotal = files.length
  const reportsTotal = reports.length
  const successRate = jobsTotal > 0 ? Math.round((jobsSuccess / jobsTotal) * 100) : 0

  const sortByCreatedDesc = <T extends { created_ts?: number }>(arr: T[]) =>
    [...arr].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))

  const recentJobs = sortByCreatedDesc(jobs).slice(0, 5)
  const recentFiles = sortByCreatedDesc(files).slice(0, 5)

  const jobsColumns = [
    { 
      title: '项目 ID', 
      dataIndex: 'job_id', 
      key: 'job_id',
      render: (v: string) => <Link to={`/project/${v}`} style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{v}</Link>
    },
    { 
      title: '研究主题', 
      dataIndex: 'topic', 
      key: 'topic',
      ellipsis: true,
      render: (v: string) => v || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>未命名主题</span>
    },
    { 
      title: '状态', 
      dataIndex: 'success', 
      key: 'success', 
      width: 100,
      render: (v: boolean) => (
        v === true ? <Tag color="success" style={{ border: 0 }}>成功</Tag> : 
        v === false ? <Tag color="error" style={{ border: 0 }}>失败</Tag> : 
        <Tag color="processing" style={{ border: 0 }}>进行中</Tag>
      )
    },
    { 
      title: '创建时间', 
      dataIndex: 'created_ts', 
      key: 'created_ts', 
      width: 160,
      render: (v: number) => <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-'}</span> 
    },
  ]

  const filesColumns = [
    { 
      title: '文件名', 
      dataIndex: 'name', 
      key: 'name',
      render: (v: string) => <span style={{ fontFamily: 'var(--font-mono)' }}>{v}</span>
    },
    { 
      title: '大小', 
      dataIndex: 'size', 
      key: 'size',
      width: 100,
      render: (v: number) => <span style={{ color: 'var(--text-muted)' }}>{v ? (v / 1024).toFixed(1) + ' KB' : '-'}</span>
    },
    { 
      title: '上传时间', 
      dataIndex: 'created_ts', 
      key: 'created_ts', 
      width: 160,
      render: (v: number) => <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-'}</span> 
    },
  ]

  return (
    <div className="dashboard-container">
      {/* <div className="scanline-overlay" /> */}
      <Card className="sci-fi-card dashboard-hero" bordered={false} style={{ marginBottom: 24 }}>
        <div className="dashboard-hero__content" ref={heroContentRef}>
          <div>
            <div className="dashboard-hero__title" style={{ color: 'var(--neon-cyan)', textShadow: '0 0 10px rgba(6, 182, 212, 0.5)' }}>
              <DashboardOutlined style={{ marginRight: 12 }} /> 科研控制台
            </div>
            <div className="dashboard-hero__subtitle" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              SYSTEM STATUS: ONLINE | 智能化研究助理已就绪
            </div>
            <Space style={{ marginTop: 24 }} size={16}>
              <Link to="/wizard">
                <Button type="primary" size="large" icon={<PlusCircleOutlined />} className="hero-btn-primary">
                  发起新研究
                </Button>
              </Link>
              <Link to="/reports">
                <Button ghost size="large" icon={<FileTextOutlined />} className="hero-btn-secondary">
                  查阅报告库
                </Button>
              </Link>
              <Link to="/data-manager">
                <Button ghost size="large" icon={<FolderOpenOutlined />} className="hero-btn-tertiary">
                  数据归档
                </Button>
              </Link>
            </Space>
          </div>
          
          {!!slides?.length && (
            <div className="dashboard-carousel-wrapper">
              <Carousel
                ref={carouselRef as any}
                autoplay
                autoplaySpeed={8000}
                dots={{ className: 'custom-dots' }}
                pauseOnHover
                draggable
                effect="fade"
              >
                {slides.map((s, i) => (
                  <div key={i}>
                    <div className="dashboard-carousel__slide">
                      {s.image ? <img src={s.image} alt={s.title || ''} /> : <div className="dashboard-carousel__placeholder" />}
                      <div className="dashboard-carousel__overlay">
                        <Typography.Title level={4} style={{ margin: 0, color: '#fff', fontFamily: 'var(--font-display)', fontSize: 18 }}>
                          {s.title || '功能模块'}
                        </Typography.Title>
                        {!!s.desc && <Typography.Paragraph style={{ margin: '4px 0 0', color: 'rgba(255,255,255,0.8)', fontSize: 13 }}>
                          {s.desc}
                        </Typography.Paragraph>}
                        {!!s.link && <Button size="small" type="primary" ghost href={s.link} style={{ marginTop: 8 }}>进入</Button>}
                      </div>
                    </div>
                  </div>
                ))}
              </Carousel>
            </div>
          )}
        </div>
      </Card>

      <Row gutter={[24, 24]}>
        <Col span={6}>
          <Card className="sci-fi-card stat-card" variant="borderless">
            <Statistic 
              title={<span className="stat-label">研究项目总数</span>}
              value={jobsTotal} 
              prefix={<ExperimentOutlined style={{ color: 'var(--neon-cyan)' }} />} 
              valueStyle={{ color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 }} 
            />
            <div className="stat-footer">
              <Badge color="var(--neon-cyan)" status="processing" text={<span style={{color: 'var(--text-muted)', fontSize: 12}}>活跃中</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="sci-fi-card stat-card" variant="borderless">
            <Statistic 
              title={<span className="stat-label">运行成功率</span>}
              value={successRate} 
              suffix="%"
              prefix={<CheckCircleOutlined style={{ color: 'var(--neon-green)' }} />} 
              valueStyle={{ color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 }} 
            />
            <div className="stat-footer">
               <Badge color="var(--neon-green)" status="processing" text={<span style={{color: 'var(--text-muted)', fontSize: 12}}>系统稳定</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="sci-fi-card stat-card" variant="borderless">
            <Statistic 
              title={<span className="stat-label">数据资产归档</span>}
              value={filesTotal} 
              prefix={<FolderOpenOutlined style={{ color: 'var(--neon-purple)' }} />} 
              valueStyle={{ color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 }} 
            />
            <div className="stat-footer">
               <Badge color="var(--neon-purple)" status="processing" text={<span style={{color: 'var(--text-muted)', fontSize: 12}}>存储正常</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="sci-fi-card stat-card" variant="borderless">
            <Statistic 
              title={<span className="stat-label">已生成报告</span>}
              value={reportsTotal} 
              prefix={<FileTextOutlined style={{ color: '#F59E0B' }} />} 
              valueStyle={{ color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 }} 
            />
            <div className="stat-footer">
               <Badge color="#F59E0B" status="processing" text={<span style={{color: 'var(--text-muted)', fontSize: 12}}>持续产出</span>} />
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
        <Col span={14}>
          <Card 
            title={<><DashboardOutlined /> 近期研究活动</>} 
            className="sci-fi-card table-card" 
            loading={loading} 
            variant="borderless" 
            extra={<Link to="/projects"><Button type="text" className="view-all-btn">查看全部 <RightOutlined /></Button></Link>}
          >
            <Table 
              rowKey="job_id" 
              size="middle" 
              columns={jobsColumns as any} 
              dataSource={recentJobs} 
              pagination={false} 
              className="dashboard-table"
            />
          </Card>
        </Col>
        <Col span={10}>
          <Card 
            title={<><FolderOpenOutlined /> 最新上传数据</>} 
            className="sci-fi-card table-card" 
            loading={loading} 
            variant="borderless" 
            extra={<Link to="/data-manager"><Button type="text" className="view-all-btn">查看全部 <RightOutlined /></Button></Link>}
          >
            <Table 
              rowKey="name" 
              size="middle" 
              columns={filesColumns as any} 
              dataSource={recentFiles} 
              pagination={false}
              className="dashboard-table" 
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
