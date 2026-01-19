import { useEffect, useMemo, useState } from 'react'
import { Card, Table, Tag, Button, message, Empty, Space, Image, Popconfirm } from 'antd'
import { listJobs, executeJobAsync, deleteJob } from '../api/research'
import { Link, useSearchParams } from 'react-router-dom'

export default function Projects() {
  const [data, setData] = useState<Array<any>>([])
  const [loading, setLoading] = useState(false)
  const [params] = useSearchParams()

  useEffect(() => {
    setLoading(true)
    listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false))
  }, [])

  const staticPrefix = useMemo(() => {
    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    return baseApi ? baseApi.replace(/\/api$/, '') : ''
  }, [])

  const q = (params.get('q') || '').trim().toLowerCase()
  const filtered = q ? data.filter((it) => (it.job_id || '').toLowerCase().includes(q) || (it.topic || '').toLowerCase().includes(q)) : data

  const columns = [
    { title: '项目', dataIndex: 'job_id', key: 'job_id', render: (v: string, r: any) => (
      <Space direction="vertical" size={2}>
        <Link to={`/project/${v}`}>{v}</Link>
        <div style={{ color: '#999' }}>{r.topic || '未设置主题'}</div>
      </Space>
    ) },
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
      dataIndex: 'plots',
      key: 'preview',
      render: (plots: string[], r: any) => {
        const show = Array.isArray(plots) ? plots.slice(0, 3) : []
        if (!show.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无图表" />
        return (
          <Image.PreviewGroup>
            <div style={{ display: 'flex', gap: 8 }}>
              {show.map((fname) => {
                const src = `${staticPrefix}/static/jobs/${r.job_id}/plots/${fname}`
                return (
                  <Image
                    key={fname}
                    src={src}
                    alt={fname}
                    width={80}
                    height={60}
                    style={{ objectFit: 'cover', borderRadius: 6, border: '1px solid #eee' }}
                    crossOrigin="anonymous"
                  />
                )
              })}
            </div>
          </Image.PreviewGroup>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'success',
      key: 'status',
      render: (v: boolean, r: any) => (
        <Space>
          {v === true ? <Tag color="green">成功</Tag> : v === false ? <Tag color="red">失败</Tag> : <Tag>未知</Tag>}
          {r.report_exists ? <Tag color="blue">报告已生成</Tag> : <Tag>报告未生成</Tag>}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, r: any) => (
        <Space>
          <Link to={`/project/${r.job_id}`}><Button size="small" type="primary">管理与查看</Button></Link>
          <Link to={`/report/${r.job_id}`}><Button size="small">查看报告</Button></Link>
          <Link to={`/compose/${r.job_id}`}><Button size="small" type="default">按章节重新生成</Button></Link>
          <Popconfirm
            title="确认删除该研究项目？"
            description="删除后不可恢复，包含报告与图表文件。"
            okText="删除"
            cancelText="取消"
            onConfirm={async () => {
              try {
                const res = await deleteJob(r.job_id)
                if (res.ok) {
                  message.success('已删除')
                  setLoading(true)
                  listJobs().then((res) => setData(res.jobs || [])).finally(() => setLoading(false))
                }
              } catch (e: any) {
                const msg = e?.response?.data?.detail || '删除失败'
                message.error(msg)
              }
            }}
          >
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card title="研究项目" extra={q ? <Tag color="blue">搜索：{q}</Tag> : undefined}>
      <Table
        rowKey="job_id"
        columns={columns}
        dataSource={[...filtered].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))}
        loading={loading}
        pagination={{ pageSize: 10 }}
      />
    </Card>
  )
}