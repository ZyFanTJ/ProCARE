import { useEffect, useMemo, useState } from 'react'
import { Card, Table, Empty, Button, message } from 'antd'
import { listReports, listJobs, executeJobAsync, regenReport } from '../api/research'
import { Link } from 'react-router-dom'

export default function Reports() {
  const [data, setData] = useState<Array<any>>([])
  const [loading, setLoading] = useState(false)
  const [plotsByJob, setPlotsByJob] = useState<Record<string, string[]>>({})

  useEffect(() => {
    setLoading(true)
    Promise.all([listReports(), listJobs()])
      .then(([r, j]) => {
        const reports = r.reports || []
        const jobs = (j.jobs || []) as Array<{ job_id: string; plots?: string[] }>
        const map: Record<string, string[]> = {}
        jobs.forEach((it) => { map[it.job_id] = Array.isArray(it.plots) ? it.plots : [] })
        setPlotsByJob(map)
        setData(reports)
      })
      .finally(() => setLoading(false))
  }, [])

  // 解析静态资源前缀，确保在开发模式下也能正确加载图片
  const staticPrefix = useMemo(() => {
    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    // 后端将API挂载在 /api，静态资源在根域名下，需去掉 /api
    return baseApi ? baseApi.replace(/\/api$/, '') : ''
  }, [])

  const columns = [
    { title: 'Job ID', dataIndex: 'job_id', key: 'job_id', render: (v: string) => <Link to={`/report/${v}`}>{v}</Link> },
    {
      title: '创建时间',
      dataIndex: 'created_ts',
      key: 'created_ts',
      render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-',
      sorter: (a: any, b: any) => (a.created_ts || 0) - (b.created_ts || 0),
      defaultSortOrder: 'descend' as const,
    },
    {
      title: '预览',
      dataIndex: 'preview',
      key: 'preview',
      render: (_: any, r: any) => {
        const jobId: string = r.job_id
        const plots = plotsByJob[jobId] || []
        const show = plots.slice(0, 3)
        if (!show.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无图表" />
        return (
          <div style={{ display: 'flex', gap: 8 }}>
            {show.map((fname) => {
              const src = `${staticPrefix}/static/jobs/${jobId}/plots/${fname}`
              return (
                <img
                  key={fname}
                  src={src}
                  alt={fname}
                  style={{ width: 80, height: 60, objectFit: 'cover', borderRadius: 6, border: '1px solid #eee' }}
                  crossOrigin="anonymous"
                />
              )
            })}
          </div>
        )
      },
    },
    { title: '报告', dataIndex: 'report_url', key: 'report_url', render: (_: any, r: any) => <Link to={`/report/${r.job_id}`}>查看报告</Link> },
    {
      title: '操作',
      key: 'action',
      render: (_: any, r: any) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to={`/wizard?job_id=${r.job_id}`}>
            <Button size="small">继续</Button>
          </Link>
          <Link to={`/compose/${r.job_id}`}>
            <Button size="small">重新生成报告</Button>
          </Link>
          <Button size="small" type="primary" onClick={async () => {
            try {
              const res = await executeJobAsync(r.job_id)
              if (res.started) message.success('已启动后台重新执行')
            } catch (e: any) {
              const msg = e?.response?.data?.detail || '重新执行失败'
              message.error(msg)
            }
          }}>重新执行</Button>
        </div>
      ),
    },
  ]

  return (
    <Card title="报告中心">
      <Table
        rowKey="job_id"
        columns={columns}
        dataSource={[...data].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />
    </Card>
  )
}