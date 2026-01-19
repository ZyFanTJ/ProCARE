import { useEffect, useMemo, useState } from 'react'
import { Card, Tabs, Typography, Space, Tag, Button, Image, message, Collapse } from 'antd'
import { Link, useParams } from 'react-router-dom'
import { fetchStatus, fetchReportPreview, fetchJobPlan, fetchExcelInfo, fetchExecLogs, fetchAnalysisCode, executeJobAsync } from '../api/research'
import JsonTree from '../components/JsonTree'
import CodeViewer from '../components/CodeViewer'
import PlanPreview from '../components/PlanPreview'
import ReportViewer from './ReportViewer'
import '../assets/logs.css'

const { Title } = Typography

export default function ProjectDetail() {
  const { jobId } = useParams()
  const [status, setStatus] = useState<any>(null)
  const [plan, setPlan] = useState<any>(null)
  const [excelInfo, setExcelInfo] = useState<any>(null)
  const [execLogs, setExecLogs] = useState<any>(null)
  const [code, setCode] = useState<string>('')
  const [report, setReport] = useState<string>('')
  const [codeCollapsed, setCodeCollapsed] = useState<boolean>(true)

  const staticPrefix = useMemo(() => {
    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    return baseApi ? baseApi.replace(/\/api$/, '') : ''
  }, [])

  useEffect(() => {
    if (!jobId) return
    fetchStatus(jobId).then(setStatus).catch(() => setStatus(null))
    fetchJobPlan(jobId).then(setPlan).catch(() => setPlan(null))
    fetchExcelInfo(jobId).then(setExcelInfo).catch(() => setExcelInfo(null))
    fetchExecLogs(jobId).then(setExecLogs).catch(() => setExecLogs(null))
    fetchAnalysisCode(jobId).then(setCode).catch(() => setCode(''))
    fetchReportPreview(jobId).then(setReport).catch(() => setReport(''))
  }, [jobId])

  const copyText = async (text: string) => {
    try { await navigator.clipboard.writeText(text || '') ; message.success('已复制') } catch { message.warning('复制失败') }
  }

  const CollapsiblePre = ({ text, maxLines = 16, collapsed = true }: { text: string; maxLines?: number; collapsed?: boolean }) => {
    const lines = (text || '').split(/\r?\n/)
    const needCollapse = lines.length > maxLines
    const shown = (collapsed && needCollapse) ? lines.slice(0, maxLines).join('\n') + '\n…（已折叠）' : text
    return <pre className="log-pre">{shown}</pre>
  }

  const plots: string[] = (status?.plots || []) as string[]

  return (
    <div>
      <Title level={3}>研究项目详情</Title>
      <Space style={{ marginBottom: 12 }}>
        <Tag color={status?.success ? 'green' : (status?.running ? 'orange' : 'red')}>{status?.success ? '成功' : (status?.running ? '执行中' : '未成功')}</Tag>
        <Link to={`/report/${jobId}`}><Button type="link">查看报告</Button></Link>
        <Link to={`/compose/${jobId}`}><Button type="link">组合报告章节</Button></Link>
      </Space>

      <Tabs
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <Card bordered={false}>
                <Space wrap>
                  <Tag>Job: {jobId}</Tag>
                  <Tag>步骤: {status?.current_step}/{status?.max_iters}</Tag>
                  <Tag>图表: {plots.length}</Tag>
                </Space>
                {!!plots?.length && (
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
                    {plots.map((p) => (
                      <div key={p} style={{ width: 260 }}>
                        <Image src={`${staticPrefix}/static/jobs/${jobId}/plots/${p}`} alt={p} width={240} height={180} style={{ objectFit: 'contain' }} />
                        <div style={{ fontSize: 12, marginTop: 4 }}>{p}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ),
          },
          {
            key: 'plan',
            label: '研究计划',
            children: (
              <Card bordered={false}>
                {plan ? (
                  <div>
                    <PlanPreview plan={plan} />
                    <Collapse style={{ marginTop: 12 }} defaultActiveKey={[]} items={[{ key: 'json', label: '原始JSON', children: (<JsonTree data={plan} defaultCollapsed />) }]} />
                  </div>
                ) : (
                  <Typography.Text type="secondary">无计划数据</Typography.Text>
                )}
              </Card>
            ),
          },
          {
            key: 'profile',
            label: '数据画像',
            children: (
              <Card bordered={false}>
                {excelInfo ? <JsonTree data={excelInfo} defaultCollapsed /> : <Typography.Text type="secondary">暂无Excel画像</Typography.Text>}
              </Card>
            ),
          },
          {
            key: 'code',
            label: '分析代码',
            children: (
              <Card bordered={false}>
                <Space style={{ marginBottom: 8 }}>
                  <Button onClick={() => copyText(code)}>复制代码</Button>
                  <Button onClick={() => setCodeCollapsed((v) => !v)}>{codeCollapsed ? '展开全部' : '收起'}</Button>
                  <Button type="primary" onClick={async () => {
                    if (!jobId) return
                    try {
                      const res = await executeJobAsync(jobId)
                      if (res.started) message.success('已启动后台重新执行')
                    } catch (e: any) {
                      const msg = e?.response?.data?.detail || '重新执行失败'
                      message.error(msg)
                    }
                  }}>重新执行</Button>
                  <a href={`${staticPrefix}/static/jobs/${jobId}/analysis.py`} target="_blank" rel="noreferrer">在新窗口打开</a>
                </Space>
                {code ? (
                  <div style={{ maxHeight: codeCollapsed ? undefined : 520, overflow: codeCollapsed ? undefined : 'auto' }}>
                    <CodeViewer code={code} collapsed={codeCollapsed} />
                  </div>
                ) : (
                  <Typography.Text type="secondary">未找到分析代码</Typography.Text>
                )}
              </Card>
            ),
          },
          {
            key: 'logs',
            label: '执行日志',
            children: (
              <Card bordered={false}>
                {Array.isArray(execLogs?.logs) && execLogs.logs.length ? (
                  <div>
                    {execLogs.logs.map((l: any, idx: number) => (
                      <Card key={idx} style={{ marginBottom: 12 }}>
                        <Space align="center" style={{ marginBottom: 8 }}>
                          <Typography.Text strong>Step {l.step}</Typography.Text>
                        </Space>
                        {l.code && (
                          <div className="log-block log-code">
                            <div className="log-block__header"><Typography.Text>LLM生成代码</Typography.Text></div>
                            <CollapsiblePre text={l.code} maxLines={20} />
                          </div>
                        )}
                        {l.stdout && (
                          <div className="log-block log-stdout">
                            <div className="log-block__header"><Typography.Text>stdout</Typography.Text></div>
                            <CollapsiblePre text={l.stdout} maxLines={10} />
                          </div>
                        )}
                        {l.stderr && (
                          <div className="log-block log-stderr">
                            <div className="log-block__header"><Typography.Text>stderr</Typography.Text></div>
                            <CollapsiblePre text={l.stderr} maxLines={10} />
                          </div>
                        )}
                        {l.llm_suggestion && (
                          <div className="log-block log-suggestion">
                            <div className="log-block__header"><Typography.Text>LLM建议</Typography.Text></div>
                            <CollapsiblePre text={l.llm_suggestion} maxLines={10} />
                          </div>
                        )}
                      </Card>
                    ))}
                  </div>
                ) : (
                  <Typography.Text type="secondary">暂无执行日志</Typography.Text>
                )}
              </Card>
            ),
          },
          {
            key: 'report',
            label: '报告预览',
            children: (
              <Card bordered={false}>
                <ReportViewer />
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}