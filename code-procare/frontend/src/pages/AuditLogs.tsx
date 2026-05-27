
import { Typography, Card, Table, Statistic, Row, Col, Tag, Button, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { fetchAuditLogs, fetchAuditStats, AuditLog, AuditStats } from '../api/audit'

const { Title, Paragraph } = Typography

export default function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [loading, setLoading] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [logsData, statsData] = await Promise.all([
        fetchAuditLogs(100, 0),
        fetchAuditStats()
      ])
      setLogs(logsData)
      setStats(statsData)
    } catch (error) {
      console.error("Failed to load audit data", error)
      message.error("加载审计数据失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const columns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (ts: number) => new Date(ts * 1000).toLocaleString(),
      width: 180,
    },
    {
      title: '任务ID',
      dataIndex: 'job_id',
      key: 'job_id',
      render: (text: string) => text ? <Tag color="blue">{text}</Tag> : <Tag>系统</Tag>,
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: 'Token消耗',
      dataIndex: 'total_tokens',
      key: 'total_tokens',
      render: (val: number, rec: AuditLog) => (
        <span>
          {val} <span style={{fontSize: 12, color: '#888'}}>({rec.prompt_tokens}/{rec.completion_tokens})</span>
        </span>
      ),
    },
    {
      title: '费用 ($)',
      dataIndex: 'cost',
      key: 'cost',
      render: (val: number) => val.toFixed(4),
    },
    {
      title: '接口端点',
      dataIndex: 'endpoint',
      key: 'endpoint',
    },
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
            <Title level={2}>🛡️ 系统审计与运行日志</Title>
            <Paragraph>
                查看系统运行状态、API Token 消耗统计以及任务执行队列的详细历史记录。
            </Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>刷新</Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="总费用"
              value={stats?.total_cost}
              precision={4}
              prefix="$"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="总Token消耗"
              value={stats?.total_tokens}
            />
          </Card>
        </Col>
        <Col span={8}>
            <Card title="最高费用任务">
                {stats?.top_jobs?.[0] ? (
                    <div>
                        <div style={{fontWeight: 'bold'}}>{stats.top_jobs[0].job_id}</div>
                        <div>${stats.top_jobs[0].cost.toFixed(4)} ({stats.top_jobs[0].tokens} tokens)</div>
                    </div>
                ) : '无数据'}
            </Card>
        </Col>
      </Row>

      <Card title="近期API调用日志">
        <Table
          dataSource={logs}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>
    </div>
  )
}
