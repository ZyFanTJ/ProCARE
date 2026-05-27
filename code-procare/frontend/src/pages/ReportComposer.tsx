import { useEffect, useState } from 'react'
import type React from 'react'
import { useParams } from 'react-router-dom'
import { Card, Checkbox, Input, Button, Space, message, List, Tag, Progress } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { composeReport, fetchSectionsMeta, composeReportAsync, fetchReportStatus, fetchReportSections, generateSection, saveReport } from '../api/research'

export default function ReportComposer() {
  const { jobId } = useParams()
  const [options, setOptions] = useState<Array<{ id: string; title: string; desc?: string; default?: boolean; category?: string }>>([])
  const [selected, setSelected] = useState<string[]>([])
  const [order, setOrder] = useState<string[]>([])
  const [overrides, setOverrides] = useState<Record<string, { human_note?: string; guidelines?: string }>>({})
  const [md, setMd] = useState('')
  const [mdSections, setMdSections] = useState<Array<{ id: string; title?: string; content: string }>>([])
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [liveSectionContent, setLiveSectionContent] = useState<Record<string, string>>({})
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState('')
  const [existing, setExisting] = useState<Set<string>>(new Set())
  const [useExisting, setUseExisting] = useState(true)
  const [existingList, setExistingList] = useState<Array<{ id: string; path: string; size?: number; mtime?: number }>>([])
  const [generating, setGenerating] = useState<Set<string>>(new Set())
  

  useEffect(() => {
    fetchSectionsMeta().then((r) => {
      const secs = r.sections || []
      setOptions(secs)
      const defaults = secs.filter((s) => s.default).map((s) => s.id)
      setSelected(defaults)
      setOrder(defaults)
    }).catch(() => {})
    if (jobId) {
      fetchReportSections(jobId).then((r) => {
        const secs = (r.sections || []) as Array<{ id: string; path: string; size?: number; mtime?: number }>
        setExisting(new Set(secs.map((x) => x.id)))
        setExistingList(secs)
        if (secs.length) {
          const ids = secs.map((x) => x.id)
          setSelected(ids)
          setOrder(ids)
        }
      }).catch(() => {})
    }
  }, [])

  

  const onGenerate = async (save?: boolean) => {
    if (!jobId) return
    setLoading(true)
    try {
      const { content, saved } = await composeReport(jobId, order.filter((id) => selected.includes(id)), overrides, !!save, useExisting)
      setMd(content || '')
      if (saved) message.success('报告已保存')
      else message.success('已生成预览')
    } catch (e) {
      message.error('生成失败')
    } finally {
      setLoading(false)
    }
  }

  const generateOne = async (sid: string) => {
    if (!jobId) return
    setGenerating((prev) => { const n = new Set(prev); n.add(sid); return n })
    try {
      const baseApi = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
      const url = `${baseApi}/generate_section_stream`
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Stream': '1' },
        body: JSON.stringify({ job_id: jobId, section_id: sid, ...(overrides[sid] || {}) }),
      })
      if (!resp.ok || !resp.body) {
        message.error('章节生成失败')
        setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n })
        return
      }
      message.success(`${sid} 开始流式生成`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let acc = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        acc += chunk.replace(/JOB_ID:[^\n]*\n?/, '')
        setLiveSectionContent((prev) => ({ ...prev, [sid]: acc }))
      }
      // 流式结束后，刷新列表并静默重新组装
      try {
        const r = await fetchReportSections(jobId)
        const secs = (r.sections || []) as Array<{ id: string; path: string; size?: number; mtime?: number }>
        setExisting(new Set(secs.map((x) => x.id)))
        setExistingList(secs)
      } catch {}
      await assemblePreviewClient(true)
      message.success(`${sid} 流式生成完成`)
      setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n })
    } catch {
      message.error('章节生成失败')
      setGenerating((prev) => { const n = new Set(prev); n.delete(sid); return n })
    }
  }

  const streamRenderSection = async (sid: string, full: string) => {
    return new Promise<void>((resolve) => {
      const total = full.length
      let i = 0
      const step = Math.max(10, Math.floor(total / 200)) // 约200步完成
      const interval = 20
      const timer = setInterval(() => {
        i = Math.min(total, i + step)
        setLiveSectionContent((prev) => ({ ...prev, [sid]: full.slice(0, i) }))
        if (i >= total) {
          clearInterval(timer)
          resolve()
        }
      }, interval)
    })
  }

  const assemblePreviewClient = async (silent?: boolean) => {
    if (!jobId) return
    const selectedIds = order.filter((id) => selected.includes(id))
    const pathById: Record<string, string> = {}
    existingList.forEach((x) => { pathById[x.id] = x.path })
    const contents: string[] = []
    const sectionBlocks: Array<{ id: string; title?: string; content: string }> = []
    for (const sid of selectedIds) {
      let content = ''
      const path = pathById[sid]
      if (useExisting && path) {
        try {
          const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
          const prefix = baseApi ? baseApi.replace(/\/api$/, '') : ''
          const url = `${prefix}/static/jobs/${jobId}/${path}`
          const resp = await fetch(url)
          if (resp.ok) content = await resp.text()
        } catch {}
      }
      if (content) contents.push(content)
      if (content) {
        const secMeta = options.find((o) => o.id === sid)
        sectionBlocks.push({ id: sid, title: secMeta?.title || sid, content })
      }
    }
    setMd(contents.join('\n'))
    setMdSections(sectionBlocks)
    if (!silent) message.success('已在前端完成组装预览')
  }

  const composeSectionLive = async (jid: string, sid: string, ov: { human_note?: string; guidelines?: string }) => {
    const res = await generateSection(jid, sid, ov)
    return res.content || ''
  }

  const exportReport = async () => {
    if (!jobId) return
    const parts = mdSections.length ? mdSections.map((b) => b.content) : [md]
    const content = parts.join('\n')
    try {
      const r = await saveReport(jobId, content)
      if (r.ok) message.success('已保存到job目录: report.md')
      else message.error('保存失败')
    } catch {
      message.error('保存失败')
    }
  }

  const updateOverride = (sid: string, field: 'human_note' | 'guidelines', v: string) => {
    setOverrides((prev) => ({ ...prev, [sid]: { ...(prev[sid] || {}), [field]: v } }))
  }

  const toggle = (ids: string[]) => {
    const prev = new Set(selected)
    const next = new Set(ids)
    setSelected(Array.from(next))
    setOrder((o) => {
      const base = o.filter((id) => next.has(id))
      const appended = ids.filter((id) => !base.includes(id))
      return [...base, ...appended]
    })
    // 选择变更后，静默重新组装预览
    assemblePreviewClient(true)
  }

  const move = (id: string, dir: 'up' | 'down') => {
    setOrder((prev) => {
      const idx = prev.indexOf(id)
      if (idx < 0) return prev
      const arr = [...prev]
      const sw = dir === 'up' ? idx - 1 : idx + 1
      if (sw < 0 || sw >= arr.length) return prev
      const t = arr[sw]; arr[sw] = arr[idx]; arr[idx] = t
      // 移动完成后触发静默预览
      setTimeout(() => assemblePreviewClient(true), 0)
      return arr
    })
  }

  const onDragStart = (id: string) => setDraggingId(id)
  const onDragOver = (e: React.DragEvent) => { e.preventDefault() }
  const onDrop = (targetId: string) => {
    if (!draggingId || draggingId === targetId) return
    setOrder((prev) => {
      const arr = prev.filter((x) => x !== draggingId)
      const idx = arr.indexOf(targetId)
      const left = arr.slice(0, idx)
      const right = arr.slice(idx)
      const next = [...left, draggingId, ...right]
      return next
    })
    setDraggingId(null)
  }

  // 监听顺序变化，实时静默组装预览，确保首次拖动立即生效
  useEffect(() => {
    assemblePreviewClient(true)
  }, [order])

  const startAsync = async () => {
    if (!jobId) return
    setRunning(true)
    setProgress(0)
    setCurrentStep('')
    try {
      const started = await composeReportAsync(jobId, order.filter((id) => selected.includes(id)), overrides, useExisting)
      if (started.started) {
        const timer = setInterval(async () => {
          try {
            const st = await fetchReportStatus(jobId)
            setProgress(st.progress || 0)
            setCurrentStep(st.step || '')
            if (st.state === 'running') {
              await assemblePreviewClient(true)
            } else {
              clearInterval(timer)
              setRunning(false)
              if (st.state === 'done') message.success('组合完成')
            }
          } catch {
            clearInterval(timer)
            setRunning(false)
          }
        }, 1000)
      }
    } catch {
      setRunning(false)
      message.error('后台组合启动失败')
    }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 16 }}>
      <Card title={`交互生成报告 (${jobId})`} style={{ height: 'calc(100vh - 160px)', overflow: 'auto' }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Checkbox.Group
            options={options.map((o) => ({ label: `${o.title}${o.category ? '（' + o.category + '）' : ''}`, value: o.id }))}
            value={selected}
            onChange={(v) => toggle(v as string[])}
          />
          <List
            dataSource={order.filter((id) => selected.includes(id))}
            renderItem={(id, i) => {
              const sec = options.find((o) => o.id === id)
              return (
                <List.Item
                  draggable
                  onDragStart={() => onDragStart(id)}
                  onDragOver={onDragOver}
                  onDrop={() => onDrop(id)}
                >
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space>
                      <Tag color="green">{i + 1}</Tag>
                      <span>{sec?.title || id}</span>
                      {existing.has(id) && <Tag color="geekblue">已有</Tag>}
                    </Space>
                    <Space>
                      <Button size="small" onClick={() => move(id, 'up')}>上移</Button>
                      <Button size="small" onClick={() => move(id, 'down')}>下移</Button>
                    </Space>
                  </Space>
                </List.Item>
              )
            }}
          />
          {order.filter((id) => selected.includes(id)).map((sid) => {
            const sec = options.find((o) => o.id === sid)
            return (
            <Card key={sid} size="small" title={sec?.title || sid} extra={<Button size="small" onClick={() => generateOne(sid)} disabled={generating.has(sid)} loading={generating.has(sid)}>生成该章节</Button>}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input.TextArea
                  rows={3}
                  placeholder="人工补充"
                  value={overrides[sid]?.human_note || ''}
                  onChange={(e) => updateOverride(sid, 'human_note', e.target.value)}
                />
                <Input.TextArea
                  rows={3}
                  placeholder="指导建议（将影响生成风格与重点）"
                  value={overrides[sid]?.guidelines || ''}
                  onChange={(e) => updateOverride(sid, 'guidelines', e.target.value)}
                />
              </Space>
            </Card>
          )})}
          <Space>
            <Button type="primary" onClick={() => assemblePreviewClient(false)}>刷新渲染</Button>
            <Button onClick={() => exportReport()}>导出报告</Button>
          </Space>
        </Space>
      </Card>
      <Card title="预览" style={{ height: 'calc(100vh - 160px)', overflow: 'auto' }}>
        <Space style={{ marginBottom: 12 }}>
          <Progress percent={progress} status={running ? 'active' : (progress >= 100 ? 'success' : 'normal')} />
          {currentStep && <Tag color="blue">{currentStep}</Tag>}
          <Button onClick={startAsync} disabled={running}>后台组合</Button>
        </Space>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {mdSections.length ? mdSections.map((blk) => (
            <div key={blk.id} style={{ border: '1px solid #1d39c4', boxShadow: '0 2px 10px rgba(29,57,196,0.08)', borderRadius: 10, padding: 12, background: '#fff' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 16, color: '#1d39c4' }}>{blk.title}</div>
                <Space>
                  <Button size="small" onClick={() => setCollapsed((prev) => {
                    const n = new Set(prev); if (n.has(blk.id)) n.delete(blk.id); else n.add(blk.id); return n;
                  })}>{collapsed.has(blk.id) ? '展开' : '折叠'}</Button>
                  <Button size="small" type="primary" onClick={() => generateOne(blk.id)} disabled={generating.has(blk.id)} loading={generating.has(blk.id)}>重新生成</Button>
                </Space>
              </div>
              {!collapsed.has(blk.id) && (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  img: ({ node, ...props }) => {
                    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
                    const prefix = baseApi ? baseApi.replace(/\/api$/, '') : ''
                    const src = (props.src || '')
                    const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src
                    return (
                      <img
                        {...props}
                        src={finalSrc}
                        style={{ maxWidth: '75%', height: 'auto', display: 'block', margin: '12px 0', objectFit: 'contain' }}
                        crossOrigin="anonymous"
                      />
                    )
                  },
                  pre: ({ node, ...props }) => (
                    <pre {...props} style={{ overflowX: 'auto', background: '#fafafa', padding: 8, borderRadius: 6 }} />
                  ),
                  code: ({ node, className, children, ...props }) => (
                    <code {...props} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }} className={className}>{children}</code>
                  ),
                  table: ({ node, ...props }) => (
                    <div style={{ overflowX: 'auto' }}>
                      <table {...props} style={{ width: '100%', borderCollapse: 'collapse' }} />
                    </div>
                  ),
                  th: ({ node, ...props }) => <th style={{ border: '1px solid #ddd', padding: '6px 10px', background: '#fafafa' }} {...props} />,
                  td: ({ node, ...props }) => <td style={{ border: '1px solid #ddd', padding: '6px 10px' }} {...props} />,
                  a: ({ node, ...props }) => <a target="_blank" rel="noreferrer" {...props} />,
                }}
              >{liveSectionContent[blk.id] ?? blk.content}</ReactMarkdown>
              )}
            </div>
          )) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                img: ({ node, ...props }) => {
                  const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
                  const prefix = baseApi ? baseApi.replace(/\/api$/, '') : ''
                  const src = (props.src || '')
                  const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src
                  return <img {...props} src={finalSrc} style={{ maxWidth: '100%', height: 'auto', display: 'block', margin: '12px 0' }} crossOrigin="anonymous" />
                },
                pre: ({ node, ...props }) => (
                  <pre {...props} style={{ overflowX: 'auto', background: '#fafafa', padding: 8, borderRadius: 6 }} />
                ),
                code: ({ node, className, children, ...props }) => (
                  <code {...props} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }} className={className}>{children}</code>
                ),
                table: ({ node, ...props }) => (
                  <div style={{ overflowX: 'auto' }}>
                    <table {...props} style={{ width: '100%', borderCollapse: 'collapse' }} />
                  </div>
                ),
                th: ({ node, ...props }) => <th style={{ border: '1px solid #ddd', padding: '6px 10px', background: '#fafafa' }} {...props} />,
                td: ({ node, ...props }) => <td style={{ border: '1px solid #ddd', padding: '6px 10px' }} {...props} />,
                a: ({ node, ...props }) => <a target="_blank" rel="noreferrer" {...props} />,
              }}
            >{md}</ReactMarkdown>
          )}
        </div>
      </Card>
    </div>
  )
}