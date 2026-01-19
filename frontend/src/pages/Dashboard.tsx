import { useEffect, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Typography, Space, Button, Badge, Carousel } from 'antd'
import type { CarouselRef } from 'antd/es/carousel'
import { useRef } from 'react'
import { listJobs, listUploads, listReports } from '../api/research'
import { DashboardOutlined, CheckCircleOutlined, FolderOpenOutlined, FileTextOutlined, PlusCircleOutlined } from '@ant-design/icons'
import '../assets/dashboard.css'
import { loadSettings } from '../utils/systemSettings'

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
      setSlides(s.carouselSlides || [])
    } catch {}
  }, [])

  const jobsTotal = jobs.length
  const jobsSuccess = jobs.filter(j => j.success === true).length
  const filesTotal = files.length
  const reportsTotal = reports.length

  const sortByCreatedDesc = <T extends { created_ts?: number }>(arr: T[]) =>
    [...arr].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))

  const recentJobs = sortByCreatedDesc(jobs).slice(0, 5)
  const recentFiles = sortByCreatedDesc(files).slice(0, 5)

  const jobsColumns = [
    { title: 'Job ID', dataIndex: 'job_id', key: 'job_id' },
    { title: '主题', dataIndex: 'topic', key: 'topic' },
    { title: '成功', dataIndex: 'success', key: 'success', render: (v: boolean) => v === true ? '是' : v === false ? '否' : '未知' },
    { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-' },
  ]

  const filesColumns = [
    { title: '文件名', dataIndex: 'name', key: 'name' },
    { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
    { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-' },
  ]

  return (
    <div>
      <Card className="dashboard-hero" bordered={false} style={{ marginBottom: 16 }}>
        <div className="dashboard-hero__title">
          <DashboardOutlined style={{ marginRight: 8 }} /> 仪表盘
        </div>
        <div className="dashboard-hero__subtitle">概览研究进展、上传与报告生成情况</div>
        <Space style={{ marginTop: 12 }}>
          <Button type="primary" icon={<PlusCircleOutlined />} href="/">新建研究</Button>
          <Button icon={<FileTextOutlined />} href="/reports">报告中心</Button>
          <Button icon={<FolderOpenOutlined />} href="/files">文件管理</Button>
        </Space>
        {!!slides?.length && (
          <div className="dashboard-carousel" style={{ marginTop: 16 }}>
            <Carousel
              ref={carouselRef as any}
              autoplay
              dots
              pauseOnHover
              draggable
              swipeToSlide
              touchMove
            >
              {slides.map((s, i) => (
                <div key={i}>
                  <div className="dashboard-carousel__slide">
                    {s.image ? <img src={s.image} alt={s.title || ''} /> : <div className="dashboard-carousel__placeholder" />}
                    <div className="dashboard-carousel__overlay">
                      <Typography.Title level={4} style={{ margin: 0 }}>{s.title || '推荐'}</Typography.Title>
                      {!!s.desc && <Typography.Paragraph style={{ margin: 0 }}>{s.desc}</Typography.Paragraph>}
                      {!!s.link && <Button size="small" type="primary" href={s.link}>查看</Button>}
                    </div>
                    <button className="dashboard-carousel__nav dashboard-carousel__nav--prev" onClick={() => carouselRef.current?.prev()} aria-label="上一张" />
                    <button className="dashboard-carousel__nav dashboard-carousel__nav--next" onClick={() => carouselRef.current?.next()} aria-label="下一张" />
                  </div>
                </div>
              ))}
            </Carousel>
          </div>
        )}
      </Card>

      <Row gutter={16}>
        <Col span={6}>
          <Card className="stat-card stat-card--blue" bordered={false}>
            <Space align="center">
              <Badge color="#2563eb" />
              <Statistic title="研究项目总数" value={jobsTotal} prefix={<DashboardOutlined />} valueStyle={{ color: '#2563eb' }} />
            </Space>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card stat-card--green" bordered={false}>
            <Space align="center">
              <Badge color="#389e0d" />
              <Statistic title="成功研究数" value={jobsSuccess} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#389e0d' }} />
            </Space>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card stat-card--orange" bordered={false}>
            <Space align="center">
              <Badge color="#d46b08" />
              <Statistic title="上传文件数" value={filesTotal} prefix={<FolderOpenOutlined />} valueStyle={{ color: '#d46b08' }} />
            </Space>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card stat-card--teal" bordered={false}>
            <Space align="center">
              <Badge color="#14b8a6" />
              <Statistic title="报告数量" value={reportsTotal} prefix={<FileTextOutlined />} valueStyle={{ color: '#14b8a6' }} />
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="近期研究项目" loading={loading} bordered={false}>
            <Table rowKey="job_id" size="small" columns={jobsColumns as any} dataSource={recentJobs} pagination={false} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="近期上传文件" loading={loading} bordered={false}>
            <Table rowKey="name" size="small" columns={filesColumns as any} dataSource={recentFiles} pagination={false} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}