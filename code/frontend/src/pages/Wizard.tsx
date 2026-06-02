import { useState, useEffect } from 'react'
import { Steps, Card, Form, Input, Button, Upload, message, Typography, Spin, Result, Collapse, Image, Space, Radio, Checkbox, List, Alert } from 'antd'
import type { UploadProps } from 'antd'
import { InboxOutlined, CodeOutlined, CheckCircleOutlined, CloseCircleOutlined, BulbOutlined, CopyOutlined } from '@ant-design/icons'
import { uploadExcel, streamPlan, streamRefinePlan, executeJobAsync, updatePlan, fetchStatus, streamExecute, fetchJobPlan, fetchExcelInfo, brainstorm, deleteProfile } from '../api/research'
import { Link, useSearchParams } from 'react-router-dom'
import { resolveStaticUrl } from '../api/client'
import '../assets/logs.css'
import JsonTree from '../components/JsonTree'
import CodeViewer from '../components/CodeViewer'
import TerminalViewer from '../components/TerminalViewer'
import StructuredLogViewer from '../components/StructuredLogViewer'

const { Title, Paragraph } = Typography

const statusMap: Record<string, string> = {
  idle: '未开始',
  connecting: '连接中...',
  streaming: '正在生成...',
  done: '已完成',
  interrupted: '已中断',
  error: '发生错误'
}

export default function Wizard() {
  const [current, setCurrent] = useState(0)
  const [topic, setTopic] = useState('')
  const [excelPath, setExcelPath] = useState<string>('')
  const [excelInfo, setExcelInfo] = useState<any>(null)
  const [excelDesc, setExcelDesc] = useState<string>('')
  const [md5, setMd5] = useState<string>('')
  const [profileReused, setProfileReused] = useState<boolean>(false)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [executionFailed, setExecutionFailed] = useState(false)
  const [job, setJob] = useState<{ id: string; success?: boolean; report?: string } | null>(null)
  const [initialPlan, setInitialPlan] = useState<any>(null)
  const [refinedPlan, setRefinedPlan] = useState<any>(null)
  const [planText, setPlanText] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [plots, setPlots] = useState<string[]>([])
  const [collapsedStates, setCollapsedStates] = useState<Record<string, boolean>>({})
  
  const [execPhase, setExecPhase] = useState<'idle' | 'code_generation' | 'opencode_init' | 'execution' | 'validation' | 'report'>('idle')
  const [streamCode, setStreamCode] = useState<string>('')
  const [fixThought, setFixThought] = useState<string>('')

  const [mode, setMode] = useState<'instruction' | 'discovery'>('instruction')
  const [hypotheses, setHypotheses] = useState<string[]>([])
  const [brainstorming, setBrainstorming] = useState(false)
  
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    const jid = searchParams.get('job_id')
    if (jid) {
      loadJobState(jid)
    }
  }, []) // only run on initial load

  useEffect(() => {
    if (job?.id && searchParams.get('job_id') !== job.id) {
      setSearchParams({ job_id: job.id })
    }
  }, [job?.id, searchParams, setSearchParams])

  const loadJobState = async (jid: string) => {
    setLoading(true)
    try {
      const [plan, info, status] = await Promise.all([
        fetchJobPlan(jid).catch(() => null),
        fetchExcelInfo(jid).catch(() => null),
        fetchStatus(jid).catch(() => null)
      ])

      if (plan && info) {
        setJob({ 
          id: jid, 
          success: status?.success, 
          report: status?.report_path 
        })
        setTopic(plan.topic || plan.objective || '')
        setExcelInfo(info)
        setExcelPath(info.path || '')
        setExcelDesc(info.user_description || '')
        setInitialPlan(plan)
        setPlanText(JSON.stringify(plan, null, 2))
        
        // Restore logs and plots if available
        if (status) {
            setLogs(status.logs || [])
            setPlots(status.plots || [])
            if (status.running) {
                setRunning(true)
                setExecPhase('execution')
                setCurrent(2)
            } else if (status.success) {
                setExecPhase('report')
                setCurrent(3)
            } else if (status.logs && status.logs.length > 0) {
                // Failed or interrupted
                setExecPhase('execution')
                setExecutionFailed(true)
                setCurrent(2)
            } else {
                // Just planned but not executed
                setCurrent(1)
            }
        } else {
            setCurrent(1)
        }
        message.success('已恢复任务状态')
      } else {
        message.error('无法加载任务信息')
      }
    } catch (e) {
      console.error(e)
      message.error('加载任务失败')
    } finally {
      setLoading(false)
    }
  }

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
    setLoading(true)
    try {
      const f = file as File
      const res = await uploadExcel(f, excelDesc)
      setExcelPath(res.excel_path)
      setExcelInfo(res.excel_info)
      setMd5(res.md5 || '')
      setProfileReused(!!res.profile_reused)
      
      if (res.job_id) {
        setJob({ id: res.job_id })
      }
      if (res.profile_reused) {
        message.success(`已加载缓存画像 (MD5: ${res.md5?.slice(0, 8)})`)
      } else if (res.duplicate) {
        message.info(`检测到相同文件，已复用路径 (MD5: ${res.md5?.slice(0, 8)})`)
      } else {
        message.success('Excel上传与分析成功')
      }
      onSuccess && onSuccess(res, new XMLHttpRequest())
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '上传失败')
      setError(e?.response?.data?.detail || '上传失败')
      onError && onError(e)
    } finally {
      setLoading(false)
    }
  }

  const [connStatus, setConnStatus] = useState<'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error'>('idle')
  const [controller, setController] = useState<AbortController | null>(null)

  const appendChunkTypewriter = (t: string) => {
    if (!t) return
    setPlanText(prev => prev + t)
    // Optional: auto-scroll to bottom
    try {
      const el = document.getElementById('plan-textarea') as HTMLTextAreaElement | null
      if (el) {
        el.selectionStart = el.value.length
        el.selectionEnd = el.value.length
        el.scrollTop = el.scrollHeight
      }
    } catch {}
  }

  const doBrainstorm = async () => {
    if (!job?.id) {
        message.warning('请先上传Excel文件')
        return
    }
    setBrainstorming(true)
    try {
        const res = await brainstorm(job.id, topic)
        setHypotheses(res.hypotheses || [])
        message.success(`生成了 ${res.hypotheses?.length || 0} 条假设`)
    } catch (e: any) {
        message.error(e.message || '生成假设失败')
    } finally {
        setBrainstorming(false)
    }
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
      const res = await streamPlan({ topic, excel_path: excelPath, excel_description: excelDesc, job_id: job?.id, mode }, (t) => {
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
    setExecutionFailed(false)
    setError('')
    setLogs([])
    setPlots([])
    setStreamCode('')
    setFixThought('')
    setExecPhase('idle')
    
    try {
      const ctrl = new AbortController()
      setController(ctrl)
      
      await streamExecute(job.id, (event) => {
         if (event.type === 'phase') {
             setExecPhase(event.phase)
         } else if (event.type === 'code_chunk') {
             setStreamCode(prev => prev + event.content)
         } else if (event.type === 'exec_result') {
             setLogs(prev => [...prev, event.log])
         } else if (event.type === 'plots') {
             setPlots(event.plots)
         } else if (event.type === 'llm_fix_chunk') {
             setFixThought(prev => prev + event.chunk)
         } else if (event.type === 'llm_suggestion') {
             setFixThought('')
             setLogs(prev => {
                 const newLogs = [...prev]
                 if (newLogs.length > 0) {
                     newLogs[newLogs.length - 1].llm_suggestion = event.suggestion || (newLogs[newLogs.length - 1].llm_suggestion)
                 }
                 return newLogs
             })
         } else if (event.type === 'report_ready') {
             setJob(prev => prev ? ({ ...prev, report: event.report_path }) : null)
         } else if (event.type === 'success') {
             setJob(prev => prev ? ({ ...prev, success: true }) : null)
             message.success('执行成功')
             setCurrent(3)
         } else if (event.type === 'error') {
             setError(event.error)
             message.error(event.error)
             setExecutionFailed(true)
         }
      }, (st) => {
          if (st === 'done' || st === 'error' || st === 'interrupted') {
              setRunning(false)
              setLoading(false)
              setController(null)
          }
      }, ctrl.signal)
      
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '执行失败'
      setError(msg)
      message.error(msg)
      setExecutionFailed(true)
      setRunning(false)
      setLoading(false)
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
            <Form.Item label="研究模式">
              <Radio.Group value={mode} onChange={e => setMode(e.target.value)}>
                <Radio.Button value="instruction">指令模式</Radio.Button>
                <Radio.Button value="discovery">发现模式</Radio.Button>
              </Radio.Group>
            </Form.Item>

            {mode === 'instruction' ? (
              <Form.Item label="研究主题">
                <Input.TextArea rows={3} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如：肝癌患者五年生存率" />
              </Form.Item>
            ) : (
              <>
                <Form.Item label="研究方向（可选）">
                  <Input.TextArea rows={2} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如：心血管疾病风险因素（留空则完全由AI探索）" />
                </Form.Item>
                <Form.Item>
                  <Button 
                      type="dashed" 
                      icon={<BulbOutlined />} 
                      onClick={doBrainstorm} 
                      loading={brainstorming}
                      disabled={!excelInfo}
                  >
                      AI 头脑风暴：生成研究假设
                  </Button>
                  {!excelInfo && <Typography.Text type="secondary" style={{ marginLeft: 8 }}>(请先上传Excel)</Typography.Text>}
                </Form.Item>
                {hypotheses.length > 0 && (
                  <div style={{ marginBottom: 16, border: '1px solid #f0f0f0', padding: 12, borderRadius: 4, background: '#fafafa' }}>
                    <div style={{ marginBottom: 8 }}>
                        <Typography.Text strong>生成的假设（勾选以组合为主题）：</Typography.Text>
                    </div>
                    <List
                        size="small"
                        dataSource={hypotheses}
                        renderItem={(item) => (
                            <List.Item>
                                <Checkbox 
                                    onChange={(e) => {
                                        if (e.target.checked) {
                                            const newTopic = topic ? `${topic}；${item}` : item;
                                            setTopic(newTopic);
                                        }
                                    }}
                                >
                                    {item}
                                </Checkbox>
                            </List.Item>
                        )}
                    />
                    <div style={{ marginTop: 8 }}>
                       <Button type="link" size="small" onClick={() => setMode('instruction')}>
                           切换回指令模式继续
                       </Button>
                    </div>
                  </div>
                )}
              </>
            )}
            <Form.Item label="补充表格描述（可选）">
              <Input.TextArea rows={3} value={excelDesc} onChange={(e) => setExcelDesc(e.target.value)} placeholder="例如：Sheet1为患者基本信息，Sheet2为随访记录..." />
            </Form.Item>
            <Form.Item label="上传Excel文件">
              <Upload.Dragger name="file" customRequest={doUpload} accept=".xlsx,.xls" maxCount={1}>
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">点击或拖拽Excel到此区域上传</p>
              </Upload.Dragger>
            </Form.Item>
            
            {profileReused && (
              <div style={{ marginBottom: 24 }}>
                <Alert 
                  message="已加载缓存的画像信息" 
                  description="系统检测到相同文件并复用了历史分析结果（含详细画像）。如需重新分析，请清除缓存。" 
                  type="success" 
                  showIcon 
                  action={
                    <Button size="small" danger onClick={async () => {
                      if (!md5) return
                      try {
                        await deleteProfile(md5)
                        setProfileReused(false)
                        setExcelInfo(null)
                        setExcelPath('')
                        setMd5('')
                        message.success('缓存已清除，请重新上传文件')
                      } catch (e) {
                        message.error('清除失败')
                      }
                    }}>
                      清除缓存
                    </Button>
                  }
                />
              </div>
            )}

            {excelInfo && (
              <Collapse defaultActiveKey={[]} items={[{
                key: 'excel-structure',
                label: 'Excel 结构信息',
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
              <Typography.Text style={{ marginLeft: 8 }}>状态：{statusMap[connStatus] || connStatus}</Typography.Text>
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
          <Space>
            <Button type="primary" onClick={runResearch} disabled={!excelPath || !topic} loading={running}>
              {running ? '正在执行...' : (executionFailed ? '重试执行' : '生成并执行研究')}
            </Button>
            <Button onClick={() => setCurrent(1)} disabled={running}>返回修改计划</Button>
            {executionFailed && <Typography.Text type="danger">执行失败，请检查下方日志并重试</Typography.Text>}
          </Space>
          <div style={{ marginTop: 16 }}>{loading && <Spin tip="正在执行..." />}</div>
          {!!error && (
            <div style={{ marginTop: 12 }}>
              <Button onClick={runResearch}>重试此步骤</Button>
            </div>
          )}

          {/* 实时生成代码展示 */}
          {(execPhase === 'code_generation' || execPhase === 'opencode_init' || execPhase === 'validation' || (execPhase === 'execution' && !logs.length)) && streamCode && (
             <Card type="inner" title={execPhase === 'opencode_init' || execPhase === 'validation' ? "OpenCode 运行进度" : "正在生成代码..."} style={{ marginTop: 16 }}>
                {execPhase === 'opencode_init' || execPhase === 'validation' ? (
                  <StructuredLogViewer log={streamCode} />
                ) : (
                  <CodeViewer code={streamCode} />
                )}
             </Card>
          )}
          
          {/* 实时修复思考 */}
          {!!fixThought && (
             <Card type="inner" title="LLM正在思考修复方案..." style={{ marginTop: 16, borderColor: '#1890ff' }}>
                <pre className="log-pre">{fixThought}</pre>
             </Card>
          )}

          {/* 实时进度展示 */}
          {!!logs?.length && (
            <Card type="inner" title="执行进度（实时）" style={{ marginTop: 16 }}>
              {logs.map((l, idx) => (
                <Card key={idx} style={{ marginBottom: 12 }}>
                  <Space align="center" style={{ marginBottom: 8 }}>
                    <Typography.Text strong>步骤 {l.step}</Typography.Text>
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
                  const src = resolveStaticUrl(`/static/jobs/${job!.id}/plots/${p}`)
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
              subTitle={job.report ? `报告已生成` : '执行已完成，请继续生成报告'}
              extra={(
                <Space>
                  {job.report && (
                    <Link to={`/report/${job.id}`}>
                      <Button type="primary">查看报告</Button>
                    </Link>
                  )}
                  <Link to={`/compose/${job.id}`}>
                    <Button type={job.report ? 'default' : 'primary'}>{job.report ? '按需修改报告' : '生成报告'}</Button>
                  </Link>
                </Space>
              )}
            />
          ) : (
            <Result status="warning" title="执行未成功" subTitle="请查看日志或重试" />
          )}

          {/* 如果是 OpenCode 模式，logs 可能为空，此时我们展示完整的 OpenCode 运行日志 */}
          {!!streamCode && (!logs || logs.length === 0) && (
            <Card type="inner" title="OpenCode 完整执行日志" style={{ marginTop: 16 }}>
              <StructuredLogViewer log={streamCode} />
            </Card>
          )}

          {logs && logs.length > 0 && (
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
                  const src = resolveStaticUrl(`/static/jobs/${job.id}/plots/${p}`)
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
