import { useEffect, useState } from 'react'
import { Card, Table, Button } from 'antd'
import { listUploads } from '../api/research'

export default function Files() {
  const [data, setData] = useState<Array<any>>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    listUploads().then((res) => setData(res.files || [])).finally(() => setLoading(false))
  }, [])

  const columns = [
    { title: '文件名', dataIndex: 'name', key: 'name' },
    { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
    { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-' },
    { title: '操作', key: 'action', render: (_: any, r: any) => r.url ? <a href={prefixUrl(r.url)} target="_blank">下载/预览</a> : '-' },
  ]

  const prefixUrl = (u: string) => {
    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    const prefix = baseApi.replace(/\/api$/, '')
    return `${prefix}${u}`
  }

  return (
    <Card title="文件管理">
      <Table rowKey="name" columns={columns} dataSource={data} loading={loading} pagination={{ pageSize: 10 }} />
    </Card>
  )
}