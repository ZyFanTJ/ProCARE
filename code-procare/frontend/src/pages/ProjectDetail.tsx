import { useEffect, useMemo, useState } from 'react'
import { Card, Tabs, Typography, Space, Tag, Button, Image, message, Collapse, Table, Descriptions, Divider } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { fetchStatus, fetchReportPreview, fetchJobPlan, fetchExcelInfo, fetchExecLogs, fetchAnalysisCode, executeJobAsync, streamRunCode } from '../api/research'
import JsonTree from '../components/JsonTree'
import CodeViewer from '../components/CodeViewer'
import PlanPreview from '../components/PlanPreview'
import ReportViewer from './ReportViewer'
import '../assets/logs.css'

const { Title } = Typography

export default function ProjectDetail() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<any>(null)
  const [plan, setPlan] = useState<any>(null)
  const [excelInfo, setExcelInfo] = useState<any>(null)
  const [execLogs, setExecLogs] = useState<any>(null)
  const [code, setCode] = useState<string>('')
  const [report, setReport] = useState<string>('')
  const [codeCollapsed, setCodeCollapsed] = useState<boolean>(true)
  const [terminalLogs, setTerminalLogs] = useState<string[]>([])
  const [terminalStatus, setTerminalStatus] = useState<string>('idle')

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

  const handleRunCode = async () => {
    if (!jobId) return
    setTerminalLogs([])
    setTerminalStatus('connecting')
    await streamRunCode(jobId, (chunk) => {
      setTerminalLogs(prev => [...prev, chunk])
    }, (status) => {
      setTerminalStatus(status)
    })
  }

  const plots: string[] = (status?.plots || []) as string[]

  const rateTag = (v: any, mode: 'missing' | 'unique') => {
    if (typeof v !== 'number' || Number.isNaN(v)) return <Tag>-</Tag>
    const pct = v * 100
    const color = mode === 'missing'
      ? (pct >= 30 ? 'red' : pct >= 10 ? 'orange' : 'green')
      : (pct >= 90 ? 'green' : pct >= 60 ? 'blue' : 'orange')
    return <Tag color={color}>{pct.toFixed(1)}%</Tag>
  }

  const renderKeyValueTags = (entries: [string, any][], emptyText: string) => {
    if (!entries.length) return <Typography.Text type="secondary">{emptyText}</Typography.Text>
    return (
      <Space wrap>
        {entries.map(([k, v]) => (
          <Tag key={`${k}-${v}`}>{k}: {String(v)}</Tag>
        ))}
      </Space>
    )
  }

  const renderListTags = (items: any[], emptyText: string) => {
    if (!items.length) return <Typography.Text type="secondary">{emptyText}</Typography.Text>
    return (
      <Space wrap>
        {items.map((v) => (
          <Tag key={String(v)}>{String(v)}</Tag>
        ))}
      </Space>
    )
  }

  const renderSheetProfile = (sheetName: string, sheetProfile: any, fallbackColumns: string[]) => {
    const dtypes = sheetProfile?.dtypes || {}
    const missing = sheetProfile?.missing_rate || {}
    const unique = sheetProfile?.unique_rate || {}
    const samples = sheetProfile?.samples || {}
    const topValues = sheetProfile?.top_values || {}
    const columnNames = Array.isArray(fallbackColumns) && fallbackColumns.length
      ? fallbackColumns
      : Object.keys(dtypes)
    const rows = columnNames.map((col) => ({
      key: col,
      name: col,
      dtype: dtypes[col] || '-',
      missing: missing[col],
      unique: unique[col],
      samples: Array.isArray(samples[col]) ? samples[col] : [],
      topValues: Array.isArray(topValues[col]) ? topValues[col] : [],
    }))

    const dtypeCounts = Object.values(dtypes).reduce((acc: Record<string, number>, v: any) => {
      const k = String(v || 'unknown')
      acc[k] = (acc[k] || 0) + 1
      return acc
    }, {})
    const dtypeTags = Object.entries(dtypeCounts).map(([k, v]) => `${k}: ${v}`)
    const candidateKeys = Array.isArray(sheetProfile?.candidate_keys) ? sheetProfile.candidate_keys : []
    const knowledge = sheetProfile?.knowledge || {}
    const variableRoles = Object.entries(knowledge?.variable_roles || {})
    const ontologyMapping = Object.entries(knowledge?.ontology_mapping || {})
    const plausibility = Object.entries(knowledge?.plausibility || {})
    const studyDesign = knowledge?.study_design || ''
    const summary = sheetProfile?.llm_summary || ''

    return (
      <div>
        <Descriptions size="small" column={2} items={[
          { key: 'dtype', label: '类型分布', children: dtypeTags.length ? renderListTags(dtypeTags, '暂无') : <Typography.Text type="secondary">暂无</Typography.Text> },
          { key: 'keys', label: '候选主键', children: renderListTags(candidateKeys, '无候选主键') },
          { key: 'summary', label: '摘要', children: summary ? <Typography.Text>{summary}</Typography.Text> : <Typography.Text type="secondary">暂无摘要</Typography.Text> },
          { key: 'study', label: '研究角色', children: studyDesign ? <Typography.Text>{studyDesign}</Typography.Text> : <Typography.Text type="secondary">未知</Typography.Text> },
        ]} />

        <Divider style={{ margin: '12px 0' }} />

        <Table
          size="small"
          pagination={false}
          rowKey="key"
          dataSource={rows}
          columns={[
            { title: '字段', dataIndex: 'name', key: 'name', width: 180, render: (v: string) => <span style={{ fontFamily: 'var(--font-mono)' }}>{v}</span> },
            { title: '类型', dataIndex: 'dtype', key: 'dtype', width: 120, render: (v: string) => <Tag color="blue">{v}</Tag> },
            { title: '缺失率', dataIndex: 'missing', key: 'missing', width: 100, render: (v: any) => rateTag(v, 'missing') },
            { title: '唯一率', dataIndex: 'unique', key: 'unique', width: 100, render: (v: any) => rateTag(v, 'unique') },
            {
              title: '示例值',
              dataIndex: 'samples',
              key: 'samples',
              render: (v: any[]) => (
                <div style={{ maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={(v || []).join(', ')}>
                  {(v || []).join(', ') || '-'}
                </div>
              )
            },
            {
              title: '高频值',
              dataIndex: 'topValues',
              key: 'topValues',
              render: (v: any[]) => (
                <div style={{ maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={(v || []).join(', ')}>
                  {(v || []).join(', ') || '-'}
                </div>
              )
            },
          ]}
        />

        <Divider style={{ margin: '12px 0' }} />

        <Collapse
          defaultActiveKey={[]}
          items={[
            {
              key: 'knowledge',
              label: '知识画像',
              children: (
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <div>
                    <Typography.Text strong>变量角色</Typography.Text>
                    <div style={{ marginTop: 6 }}>{renderKeyValueTags(variableRoles, '暂无角色映射')}</div>
                  </div>
                  <div>
                    <Typography.Text strong>概念映射</Typography.Text>
                    <div style={{ marginTop: 6 }}>{renderKeyValueTags(ontologyMapping, '暂无映射')}</div>
                  </div>
                  <div>
                    <Typography.Text strong>合理性检查</Typography.Text>
                    <div style={{ marginTop: 6 }}>{renderKeyValueTags(plausibility, '暂无检查结果')}</div>
                  </div>
                </Space>
              )
            }
          ]}
        />
      </div>
    )
  }

  const renderExcelProfile = () => {
    if (!excelInfo) return <Typography.Text type="secondary">暂无Excel画像</Typography.Text>
    const sheets: string[] = Array.isArray(excelInfo?.sheets) ? excelInfo.sheets : Object.keys(excelInfo?.profile || {})
    const columnsMap = excelInfo?.columns || {}
    const totalColumns = sheets.reduce((sum, s) => sum + (Array.isArray(columnsMap?.[s]) ? columnsMap[s].length : 0), 0)
    const description = excelInfo?.description || ''
    const path = excelInfo?.path || ''
    const profile = excelInfo?.profile || {}

    return (
      <div>
        <Descriptions size="small" column={2} items={[
          { key: 'sheets', label: 'Sheet数', children: sheets.length || '-' },
          { key: 'columns', label: '字段总数', children: totalColumns || '-' },
          { key: 'path', label: '数据路径', children: path ? <Typography.Text>{path}</Typography.Text> : <Typography.Text type="secondary">未知</Typography.Text> },
          { key: 'desc', label: '描述', children: description ? <Typography.Text>{description}</Typography.Text> : <Typography.Text type="secondary">无描述</Typography.Text> },
        ]} />

        <Divider style={{ margin: '12px 0' }} />

        {sheets.length ? (
          <Collapse
            defaultActiveKey={sheets.slice(0, 1)}
            items={sheets.map((s) => ({
              key: s,
              label: s,
              children: renderSheetProfile(s, profile?.[s], columnsMap?.[s] || []),
            }))}
          />
        ) : (
          <Typography.Text type="secondary">未找到Sheet</Typography.Text>
        )}

        <Collapse style={{ marginTop: 12 }} defaultActiveKey={[]} items={[
          { key: 'json', label: '原始JSON', children: (<JsonTree data={excelInfo} defaultCollapsed />) }
        ]} />
      </div>
    )
  }

  return (
    <div>
      <Title level={3}>研究项目详情</Title>
      <Space style={{ marginBottom: 12 }} wrap>
        <Tag color={status?.success ? 'green' : (status?.running ? 'orange' : 'red')}>{status?.success ? '成功' : (status?.running ? '执行中' : '未成功')}</Tag>
        <Link to={`/report/${jobId}`}><Button type="link">查看报告</Button></Link>
        <Link to={`/compose/${jobId}`}><Button type="link">组合报告章节</Button></Link>
        <Link to={`/project/${jobId}/paper`}><Button type="link">论文生成</Button></Link>
      </Space>

      <Tabs
        onTabClick={(key) => {
          if (key === 'paper-generation' && jobId) navigate(`/project/${jobId}/paper`)
        }}
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
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginTop: 12 }}>
                    {plots.map((p) => (
                      <div key={p} style={{ border: '1px solid var(--border-color)', borderRadius: 8, padding: 12, background: 'var(--bg-component)' }}>
                        <div style={{ width: '100%', height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-app)', borderRadius: 4, overflow: 'hidden' }}>
                          <Image src={`${staticPrefix}/static/jobs/${jobId}/plots/${p}`} alt={p} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                        </div>
                        <div style={{ fontSize: 13, marginTop: 8, fontWeight: 500, color: 'var(--text-primary)', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={p}>{p}</div>
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
                {renderExcelProfile()}
              </Card>
            ),
          },
          {
            key: 'code',
            label: '分析代码',
            children: (
              <Card bordered={false}>
                <Space style={{ marginBottom: 8 }} wrap>
                  <Button onClick={() => copyText(code)}>复制代码</Button>
                  <Button onClick={() => setCodeCollapsed((v) => !v)}>{codeCollapsed ? '展开全部' : '收起'}</Button>
                  <Button onClick={handleRunCode} loading={terminalStatus === 'streaming' || terminalStatus === 'connecting'}>运行当前代码</Button>
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
                {(terminalLogs.length > 0 || terminalStatus === 'streaming' || terminalStatus === 'connecting') && (
                  <div style={{ marginTop: 16, background: '#1e1e1e', padding: 12, borderRadius: 8, color: '#d4d4d4', fontFamily: 'monospace', maxHeight: 300, overflow: 'auto' }}>
                    <div style={{ marginBottom: 8, borderBottom: '1px solid #333', paddingBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
                      <span>终端输出</span>
                      <span style={{ fontSize: 12, opacity: 0.7 }}>{terminalStatus}</span>
                    </div>
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12 }}>
                      {terminalLogs.join('')}
                    </pre>
                  </div>
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
                          <Typography.Text strong>步骤 {l.step}</Typography.Text>
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
          {
            key: 'paper-generation',
            label: '论文生成',
            children: (
              <Card bordered={false}>
                <Button type="primary" onClick={() => jobId && navigate(`/project/${jobId}/paper`)}>进入论文生成</Button>
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}
