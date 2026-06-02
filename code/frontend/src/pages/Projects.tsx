
import { useEffect, useState } from 'react'
import { Table, Tag, Button, message, Empty, Space, Image, Popconfirm, Input, Tooltip } from 'antd'
import { listJobs, executeJobAsync, deleteJob } from '../api/research'
import { resolveStaticUrl } from '../api/client'
import { Link, useSearchParams } from 'react-router-dom'
import { 
  SearchOutlined, 
  ExperimentOutlined, 
  EyeOutlined, 
  ReloadOutlined, 
  DeleteOutlined, 
  FileTextOutlined,
  AppstoreOutlined,
  PlayCircleOutlined
} from '@ant-design/icons'
import './Projects.css'

export default function Projects() {
  const [data, setData] = useState<Array<any>>([])
  const [loading, setLoading] = useState(false)
  const [params, setParams] = useSearchParams()
  // Generate a unique timestamp for this session to bypass browser cache issues (CORS on 304)
  const [cacheBuster] = useState(Date.now())

  useEffect(() => {
    setLoading(true)
    listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false))
  }, [])

  const q = (params.get('q') || '').trim().toLowerCase()
  const filtered = q ? data.filter((it) => (it.job_id || '').toLowerCase().includes(q) || (it.topic || '').toLowerCase().includes(q)) : data

  const onSearch = (value: string) => {
    if (value) {
      setParams({ q: value })
    } else {
      setParams({})
    }
  }

  const columns = [
    { 
      title: '项目名称 / 研究主题', 
      dataIndex: 'job_id', 
      key: 'job_id', 
      width: 350,
      render: (v: string, r: any) => (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <Link to={`/project/${v}`} className="project-name">
            <ExperimentOutlined style={{ marginRight: 8 }} />
            {v}
          </Link>
          <div className="project-topic" title={r.topic}>
            {r.topic || '暂未设置研究主题'}
          </div>
        </div>
      ) 
    },
    {
      title: '创建时间',
      dataIndex: 'created_ts',
      key: 'created_ts',
      width: 180,
      render: (v: number) => (
        <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
          {v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-'}
        </span>
      ),
      sorter: (a: any, b: any) => (a.created_ts || 0) - (b.created_ts || 0),
      defaultSortOrder: 'descend' as const,
    },
    {
      title: '可视化预览',
      dataIndex: 'plots',
      key: 'preview',
      render: (plots: string[], r: any) => {
        const show = Array.isArray(plots) ? plots.slice(0, 4) : []
        if (!show.length) return <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>暂无图表</span>
        return (
          <Image.PreviewGroup>
            <div className="preview-grid">
              {show.map((fname) => {
                // Add timestamp to bypass 304 cache issues (which might cause CORS errors in some environments)
                // We combine job creation time with a session-level cache buster
                const timestamp = r.created_ts || 0
                const src = `${resolveStaticUrl(`/static/jobs/${r.job_id}/plots/${fname}`)}?t=${timestamp}&cb=${cacheBuster}`
                return (
                  <Image
                    key={fname}
                    src={src}
                    alt={fname}
                    width={48}
                    height={36}
                    className="preview-img"
                    style={{ objectFit: 'cover' }}
                    fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
                    crossOrigin="anonymous"
                  />
                )
              })}
              {plots.length > 4 && (
                <div style={{ 
                  width: 48, height: 36, background: 'rgba(0,0,0,0.05)', borderRadius: 6, 
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#666' 
                }}>
                  +{plots.length - 4}
                </div>
              )}
            </div>
          </Image.PreviewGroup>
        )
      },
    },
    {
      title: '运行状态',
      dataIndex: 'success',
      key: 'status',
      width: 150,
      render: (v: boolean, r: any) => (
        <Space direction="vertical" size={2}>
          {v === true ? 
            <Tag className="status-tag status-tag-success">运行成功</Tag> : 
            v === false ? <Tag className="status-tag status-tag-error">运行失败</Tag> : 
            <Tag className="status-tag status-tag-processing">进行中 / 未知</Tag>
          }
          {r.report_exists && <Tag className="status-tag status-tag-default">已生成报告</Tag>}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      render: (_: any, r: any) => (
        <Space wrap size={8}>
          <Tooltip title="进入项目详情与管理">
            <Link to={`/project/${r.job_id}`}>
              <Button size="small" type="primary" className="action-btn action-btn-primary" icon={<AppstoreOutlined />}>
                管理
              </Button>
            </Link>
          </Tooltip>

          <Tooltip title="回到向导继续执行">
            <Link to={`/wizard?job_id=${r.job_id}`}>
              <Button size="small" className="action-btn" icon={<PlayCircleOutlined />}>
                继续
              </Button>
            </Link>
          </Tooltip>
          
          <Tooltip title="查看研究报告">
            <Link to={`/report/${r.job_id}`}>
              <Button size="small" className="action-btn" icon={<FileTextOutlined />} disabled={!r.report_exists}>
                报告
              </Button>
            </Link>
          </Tooltip>
          
          <Tooltip title="按章节重新生成报告">
            <Link to={`/compose/${r.job_id}`}>
              <Button size="small" className="action-btn" icon={<ReloadOutlined />}>
                重组
              </Button>
            </Link>
          </Tooltip>
          
          <Popconfirm
            title="确认删除该研究项目？"
            description="删除后不可恢复，包含所有报告与图表文件。"
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              try {
                const res = await deleteJob(r.job_id)
                if (res.ok) {
                  message.success('项目已删除')
                  setLoading(true)
                  listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false))
                }
              } catch (e: any) {
                const msg = e?.response?.data?.detail || '删除失败'
                message.error(msg)
              }
            }}
          >
            <Button size="small" danger type="text" className="action-btn" icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="projects-container">
      <div className="projects-card">
        <div style={{ padding: '24px 24px 0 24px' }}>
          <div className="projects-header">
            <div className="projects-title">
              <AppstoreOutlined style={{ color: 'var(--primary-color)' }} />
              研究项目库
            </div>
            <div style={{ display: 'flex', gap: 16 }}>
              <Input 
                placeholder="搜索项目ID或主题..." 
                prefix={<SearchOutlined style={{ color: 'var(--text-secondary)' }} />} 
                allowClear
                value={q}
                onChange={(e) => onSearch(e.target.value)}
                className="search-input"
                style={{ width: 280 }}
              />
              <Link to="/wizard">
                <Button type="primary" icon={<ExperimentOutlined />} size="middle" className="action-btn action-btn-primary">
                  新建研究
                </Button>
              </Link>
            </div>
          </div>
        </div>
        
        <Table
          className="projects-table"
          rowKey="job_id"
          columns={columns}
          dataSource={[...filtered].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))}
          loading={loading}
          pagination={{ 
            pageSize: 10, 
            showTotal: (total) => `共 ${total} 个项目`,
            showSizeChanger: true,
            showQuickJumper: true
          }}
        />
      </div>
    </div>
  )
}
