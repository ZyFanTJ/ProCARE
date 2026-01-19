import { useState } from 'react'
import { Steps, Card, Form, Input, Button, Upload, message, Typography, Spin, Result, Collapse, Image, Space } from 'antd'
import type { UploadProps } from 'antd'
import { InboxOutlined, CodeOutlined, CheckCircleOutlined, CloseCircleOutlined, BulbOutlined, CopyOutlined } from '@ant-design/icons'
import { uploadExcel, streamPlan, streamRefinePlan, executeJobAsync, updatePlan, fetchStatus } from '../api/research'
import { Link } from 'react-router-dom'
import '../assets/logs.css'
import JsonTree from '../components/JsonTree'
import CodeViewer from '../components/CodeViewer'

const { Title, Paragraph } = Typography

export default function Wizard() {
  const [current, setCurrent] = useState(0)
  const [topic, setTopic] = useState('')
  const [excelPath, setExcelPath] = useState<string>('')
  const [excelInfo, setExcelInfo] = useState<any>(null)
  const [excelDesc, setExcelDesc] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [job, setJob] = useState<{ id: string; success?: boolean; report?: string } | null>(null)
  const [initialPlan, setInitialPlan] = useState<any>(null)
  const [refinedPlan, setRefinedPlan] = useState<any>(null)
  const [planText, setPlanText] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [plots, setPlots] = useState<string[]>([])
  const [collapsedStates, setCollapsedStates] = useState<Record<string, boolean>>({})

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      message.success('已复制到剪贴板')
    } catch {
      message.warning('复制失败，请手动选择文本')
    }
  }

  // 折叠的预格式文本组件，默认折叠，显示前N行
  const isCollapsed = (key: string, defaultValue = true) => (
    collapsedStates.hasOwnProperty(key) ? collapsedStates[key] : defaultValue
  )

  const toggleCollapsed = (key: string, defaultValue = true) => {
    setCollapsedStates(prev => ({
      ...prev,
      [key]: !(prev.hasOwnProperty(key) ? prev[key] : defaultValue),
    }))
  }

  const CollapsiblePre = ({ text, maxLines = 10, collapsed = true }: { text: string; maxLines?: number; collapsed?: boolean }) => {
    const lines = (text || '').split(/\r?\n/)
    const needCollapse = lines.length > maxLines
    const shown = collapsed && needCollapse ? lines.slice(0, maxLines).join('\n') + '\n…（已折叠）' : text
    return <pre className="log-pre">{shown}</pre>
  }

  const steps = [
    { title: '输入主题与上传文件' },
    { title: '生成计划' },
    { title: '生成与执行' },
    { title: '查看报告' },
  ]

  const next = () => setCurrent((c) => Math.min(c + 1, steps.length - 1))
  const prev = () => setCurrent((c) => Math.max(c - 1, 0))

  const doUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    try {
      const f = file as File
      const res = await uploadExcel(f, excelDesc)
      setExcelPath(res.excel_path)
      setExcelInfo(res.excel_info)
      if (res.duplicate) {
        message.info(`检测到相同文件，已复用（MD5: ${res.md5})`)
      } else {
        message.success('Excel上传与分析成功')
      }
      onSuccess && onSuccess({}, new XMLHttpRequest())
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '上传失败')
      setError(e?.response?.data?.detail || '上传失败')
      onError && onError(e)
    }
  }

  const [connStatus, setConnStatus] = useState<'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error'>('idle')
  const [controller, setController] = useState<AbortController | null>(null)

  const appendChunkTypewriter = (t: string) => {
    if (!t) return
    let i = 0
    const step = Math.max(10, Math.floor(t.length / 50))
    const emit = () => {
      if (i >= t.length) return
      const next = t.slice(i, i + step)
      i += step
      setPlanText(prev => prev + next)
      try {
        const el = document.getElementById('plan-textarea') as HTMLTextAreaElement | null
        if (el) {
          el.selectionStart = el.value.length
          el.selectionEnd = el.value.length
          el.scrollTop = el.scrollHeight
        }
      } catch {}
      setTimeout(emit, 20)
    }
    emit()
  }

  const doPlan = async () => {
    if (!topic || !excelPath) {
      message.warning('请先填写主题并上传Excel')
      return
    }
    setLoading(true)
    setError('')
    try {
      setPlanText('')
      setConnStatus('idle')
      const ctrl = new AbortController()
      setController(ctrl)
      const res = await streamPlan({ topic, excel_path: excelPath, excel_description: excelDesc, job_id: job?.id }, (t) => {
        appendChunkTypewriter(t)
      }, (st) => setConnStatus(st), ctrl.signal)
      if (res.job_id) setJob({ id: res.job_id })
      if (res.plan) {
        setInitialPlan(res.plan)
        setPlanText(JSON.stringify(res.plan, null, 2))
        message.success('研究计划生成成功')
      } else {
        message.warning('流式结果未解析为JSON，请手动检查')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '生成计划失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
      setConnStatus('idle')
      setController(null)
    }
  }

  const doRefinePlan = async () => {
    if (!job?.id) { message.warning('请先生成初步计划'); return }
    setLoading(true)
    setError('')
    try {
      setPlanText('')
      setConnStatus('idle')
      const ctrl = new AbortController()
      setController(ctrl)
      const res = await streamRefinePlan(job.id, (t: string) => {
        appendChunkTypewriter(t)
      }, (st: 'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error') => setConnStatus(st), ctrl.signal)
      if (res.plan_refined) {
        setRefinedPlan(res.plan_refined)
        setPlanText(JSON.stringify(res.plan_refined, null, 2))
        message.success('细化计划生成成功')
      } else {
        message.warning('流式结果未解析为JSON，请手动检查')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '细化计划生成失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
      setConnStatus('idle')
      setController(null)
    }
  }

  const saveEditedPlan = async () => {
    if (!job?.id) { message.warning('请先生成或选择一个job'); return }
    try {
      const parsed = JSON.parse(planText)
      const res = await updatePlan(job.id, parsed)
      if (res.ok) {
        if (refinedPlan) {
          setRefinedPlan(parsed)
        } else {
          setInitialPlan(parsed)
        }
        message.success('计划已保存')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '保存失败，请确认JSON格式正确'
      message.error(msg)
    }
  }

  const runResearch = async () => {
    if (!job?.id) { message.warning('请先生成研究计划'); return }
    setLoading(true)
    setRunning(true)
    setError('')
    try {
      // 启动异步执行
      const start = await executeJobAsync(job.id)
      if (start.started) {
        message.success('已开始后台执行，正在获取实时进度...')
        // 轮询状态直到完成
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
        const prefix = baseApi.replace(/\/api$/, '')
        const timer = setInterval(async () => {
          try {
            const st = await fetchStatus(job.id)
            setLogs(st.logs || [])
            setPlots(st.plots || [])
            // 保持在当前步骤展示实时进度
            if (!st.running) {
              clearInterval(timer)
              setRunning(false)
              setLoading(false)
              setJob({ id: job.id, success: st.success, report: `${prefix}/static/jobs/${job.id}/report.md` })
              const finalMsg = st.success
                ? '执行成功'
                : (st.message || (st.max_iters_reached ? '已达到最大重试次数，执行未成功' : '执行未成功'))
              const notify = st.success ? message.success : message.warning
              notify(finalMsg)
              setCurrent(3)
            }
          } catch (e) {
            clearInterval(timer)
            setRunning(false)
          }
        }, 1500)
      }
      } catch (e: any) {
      const msg = e?.response?.data?.detail || '执行失败'
      setError(msg)
      message.error(msg)
    } finally {
      // 保持loading由轮询结束控制
    }
  }

  return (
    <div>
      <Title level={3}>新建研究</Title>
      <Card>
        <Steps current={current} items={steps} />
      </Card>

      {current === 0 && (
        <Card style={{ marginTop: 16 }}>
          <Paragraph>请输入研究主题，并上传数据文件，两者共同用于生成研究计划。</Paragraph>
          <Form layout="vertical">
            <Form.Item label="研究主题">
              <Input.TextArea rows={3} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如：肝癌患者五年生存率" />
            </Form.Item>
            <Form.Item label="补充表格描述（可选）">
              <Input.TextArea rows={3} value={excelDesc} onChange={(e) => setExcelDesc(e.target.value)} placeholder="例如：Sheet1为患者基本信息，Sheet2为随访记录..." />
            </Form.Item>
            <Form.Item label="上传Excel文件">
              <Upload.Dragger name="file" customRequest={doUpload} accept=".xlsx,.xls" maxCount={1}>
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">点击或拖拽Excel到此区域上传</p>
              </Upload.Dragger>
            </Form.Item>
            {excelInfo && (
              <Collapse defaultActiveKey={[]} items={[{
                key: 'excel-structure',
                label: 'Excel结构信息',
                children: (
                  <JsonTree data={excelInfo} defaultCollapsed />
                ),
              }]} />
            )}
            <Form.Item style={{ marginTop: 16 }}>
              <Button type="primary" onClick={next} disabled={!topic || !excelPath}>下一步</Button>
            </Form.Item>
          </Form>
        </Card>
      )}

      {current === 1 && (
        <Card style={{ marginTop: 16 }}>
          <Paragraph>请生成研究计划。计划将用于指导代码生成与执行。</Paragraph>
          <Space style={{ marginBottom: 12 }}>
            <Button type="primary" onClick={doPlan} disabled={!excelPath || !topic}>生成研究计划</Button>
            {(connStatus === 'connecting' || connStatus === 'streaming') && (
              <Button danger onClick={() => controller && controller.abort()}>中断</Button>
            )}
            {connStatus !== 'idle' && (
              <Typography.Text style={{ marginLeft: 8 }}>状态：{connStatus}</Typography.Text>
            )}
          </Space>
          {!!error && (
            <div style={{ marginTop: 12 }}>
              <Button onClick={doPlan}>重试此步骤</Button>
            </div>
          )}
          <div style={{ marginTop: 16 }}>{loading && <Spin />}</div>
          <Card type="inner" title="计划（可编辑）" style={{ marginTop: 16 }}>
            <Input.TextArea id="plan-textarea" rows={12} value={planText} onChange={(e) => setPlanText(e.target.value)} />
            <div style={{ marginTop: 12 }}>
              <Button type="default" onClick={saveEditedPlan} style={{ marginRight: 8 }}>保存计划修改</Button>
              <Button onClick={doRefinePlan} type="primary">根据字段理解生成细化计划</Button>
              <Button onClick={() => setCurrent(2)} style={{ marginLeft: 8 }}>下一步：生成与执行</Button>
            </div>
          </Card>
        </Card>
      )}

      {current === 2 && (
        <Card style={{ marginTop: 16 }}>
          <Paragraph>将基于Excel结构信息制定计划并生成Python代码，运行后生成图表与报告。</Paragraph>
          <Button type="primary" onClick={runResearch} disabled={!excelPath || !topic}>生成并执行研究</Button>
          <div style={{ marginTop: 16 }}>{loading && <Spin />}</div>
          {!!error && (
            <div style={{ marginTop: 12 }}>
              <Button onClick={runResearch}>重试此步骤</Button>
            </div>
          )}

          {/* 实时进度展示 */}
          {!!logs?.length && (
            <Card type="inner" title="执行进度（实时）" style={{ marginTop: 16 }}>
              {logs.map((l, idx) => (
                <Card key={idx} style={{ marginBottom: 12 }}>
                  <Space align="center" style={{ marginBottom: 8 }}>
                    <Typography.Text strong>Step {l.step}</Typography.Text>
                  </Space>
                  {l.code && (
                    <div className="log-block log-code">
                      <div className="log-block__header">
                        <Space>
                          <CodeOutlined />
                          <Typography.Text>LLM生成代码</Typography.Text>
                        </Space>
                        <Space>
                          <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.code)}>复制</Button>
                          <Button type="link" onClick={() => toggleCollapsed(`code-${idx}`, false)}>
                            {isCollapsed(`code-${idx}`, false) ? '展开全部' : '收起'}
                          </Button>
                        </Space>
                      </div>
                      <CodeViewer code={l.code} collapsed={isCollapsed(`code-${idx}`, false)} />
                    </div>
                  )}
                  {l.stdout && (
                    <div className="log-block log-stdout">
                      <div className="log-block__header">
                        <Space>
                          <CheckCircleOutlined />
                          <Typography.Text>执行结果（stdout）</Typography.Text>
                        </Space>
                        <Space>
                          <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.stdout)}>复制</Button>
                          <Button type="link" onClick={() => toggleCollapsed(`stdout-${idx}`, true)}>
                            {isCollapsed(`stdout-${idx}`, true) ? '展开全部' : '收起'}
                          </Button>
                        </Space>
                      </div>
                      <CollapsiblePre text={l.stdout} maxLines={10} collapsed={isCollapsed(`stdout-${idx}`, true)} />
                    </div>
                  )}
                  {l.stderr && (
                    <div className="log-block log-stderr">
                      <div className="log-block__header">
                        <Space>
                          <CloseCircleOutlined />
                          <Typography.Text>错误信息（stderr）</Typography.Text>
                        </Space>
                        <Space>
                          <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.stderr)}>复制</Button>
                          <Button type="link" onClick={() => toggleCollapsed(`stderr-${idx}`, true)}>
                            {isCollapsed(`stderr-${idx}`, true) ? '展开全部' : '收起'}
                          </Button>
                        </Space>
                      </div>
                      <CollapsiblePre text={l.stderr} maxLines={10} collapsed={isCollapsed(`stderr-${idx}`, true)} />
                    </div>
                  )}
                  {l.llm_suggestion && (
                    <div className="log-block log-suggestion">
                      <div className="log-block__header">
                        <Space>
                          <BulbOutlined />
                          <Typography.Text>LLM修改建议</Typography.Text>
                        </Space>
                        <Space>
                          <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.llm_suggestion)}>复制</Button>
                          <Button type="link" onClick={() => toggleCollapsed(`suggestion-${idx}`, true)}>
                            {isCollapsed(`suggestion-${idx}`, true) ? '展开全部' : '收起'}
                          </Button>
                        </Space>
                      </div>
                      <CollapsiblePre text={l.llm_suggestion} maxLines={10} collapsed={isCollapsed(`suggestion-${idx}`, true)} />
                    </div>
                  )}
                </Card>
              ))}
            </Card>
          )}

          {!!plots?.length && (
            <Card type="inner" title="图表预览（实时）" style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {plots.map((p) => {
                  const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
                  const prefix = baseApi.replace(/\/api$/, '')
                  const src = `${prefix}/static/jobs/${job!.id}/plots/${p}`
                  return (
                    <div key={p} style={{ width: 260 }}>
                      <Image src={src} alt={p} width={240} height={180} style={{ objectFit: 'contain' }} />
                      <div style={{ fontSize: 12, marginTop: 4 }}>{p}</div>
                    </div>
                  )
                })}
              </div>
            </Card>
          )}
        </Card>
      )}

      {current === 3 && job && (
        <Card style={{ marginTop: 16 }}>
          {job.success ? (
            <Result
              status="success"
              title="执行成功"
              subTitle={`报告路径：${job.report}`}
              extra={(
                <Space>
                  <Link to={`/report/${job.id}`}>查看报告</Link>
                  <Link to={`/compose/${job.id}`}>按需生成报告章节</Link>
                </Space>
              )}
            />
          ) : (
            <Result status="warning" title="执行未成功" subTitle="请查看日志或重试" />
          )}

          {!!logs?.length && (
            <Card type="inner" title="执行日志（多轮）" style={{ marginTop: 16 }}>
              {logs.map((l, idx) => (
                <Card key={idx} style={{ marginBottom: 12 }}>
                  <Space align="center" style={{ marginBottom: 8 }}>
                    <Typography.Text strong>Step {l.step}</Typography.Text>
                  </Space>
                  {l.code && (
                    <div className="log-block log-code">
                      <div className="log-block__header">
                        <Space>
                          <CodeOutlined />
                          <Typography.Text>LLM生成代码</Typography.Text>
                        </Space>
                        <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.code)}>复制</Button>
                      </div>
                      <CodeViewer code={l.code} />
                    </div>
                  )}
                  {l.stdout && (
                    <div className="log-block log-stdout">
                      <div className="log-block__header">
                        <Space>
                          <CheckCircleOutlined />
                          <Typography.Text>执行结果（stdout）</Typography.Text>
                        </Space>
                        <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.stdout)}>复制</Button>
                      </div>
                      <CollapsiblePre text={l.stdout} maxLines={10} />
                    </div>
                  )}
                  {l.stderr && (
                    <div className="log-block log-stderr">
                      <div className="log-block__header">
                        <Space>
                          <CloseCircleOutlined />
                          <Typography.Text>错误信息（stderr）</Typography.Text>
                        </Space>
                        <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.stderr)}>复制</Button>
                      </div>
                      <CollapsiblePre text={l.stderr} maxLines={10} />
                    </div>
                  )}
                  {l.llm_suggestion && (
                    <div className="log-block log-suggestion">
                      <div className="log-block__header">
                        <Space>
                          <BulbOutlined />
                          <Typography.Text>LLM修改建议</Typography.Text>
                        </Space>
                        <Button type="link" icon={<CopyOutlined />} onClick={() => copyText(l.llm_suggestion)}>复制</Button>
                      </div>
                      <CollapsiblePre text={l.llm_suggestion} maxLines={10} />
                    </div>
                  )}
                </Card>
              ))}
            </Card>
          )}

          {!!plots?.length && (
            <Card type="inner" title="图表预览" style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {plots.map((p) => {
                  const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
                  const prefix = baseApi.replace(/\/api$/, '')
                  const src = `${prefix}/static/jobs/${job.id}/plots/${p}`
                  return (
                    <div key={p} style={{ width: 260 }}>
                      <Image src={src} alt={p} width={240} height={180} style={{ objectFit: 'contain' }} />
                      <div style={{ fontSize: 12, marginTop: 4 }}>{p}</div>
                    </div>
                  )
                })}
              </div>
              <div style={{ marginTop: 12 }}>
                <Button onClick={() => runResearch()} type="primary">重新执行此研究</Button>
              </div>
            </Card>
          )}
        </Card>
      )}
    </div>
  )
}