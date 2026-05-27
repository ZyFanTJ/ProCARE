import { api } from '../api/client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Avatar, Button, Card, Collapse, Input, Space, Tag, Typography, Tooltip, Image, App } from 'antd'
import { CloseOutlined, CopyOutlined, PauseCircleOutlined, RobotOutlined, SendOutlined, ThunderboltOutlined, PictureOutlined, DeleteOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { assistantChatStream, ChatMessage, fetchAssistantGuide } from '../api/assistant'
import '../assets/copilotSidebar.css'

function resolvePageKey(pathname: string) {
  if (pathname.startsWith('/dashboard')) return 'dashboard'
  if (pathname === '/' || pathname.startsWith('/wizard')) return 'wizard'
  if (pathname.startsWith('/compose')) return 'report-composer'
  if (pathname.startsWith('/report')) return 'report-viewer'
  if (pathname.startsWith('/projects')) return 'projects'
  if (pathname.startsWith('/data-manager')) return 'data-manager'
  if (pathname.startsWith('/templates')) return 'templates'
  if (pathname.startsWith('/settings')) return 'settings'
  return 'unknown'
}

function resolveJobId(pathname: string, search: string) {
  const m1 = pathname.match(/^\/report\/([^\/]+)/)
  if (m1) return m1[1]
  const m2 = pathname.match(/^\/compose\/([^\/]+)/)
  if (m2) return m2[1]
  const m3 = pathname.match(/^\/project\/([^\/]+)/)
  if (m3) return m3[1]
  
  if (search) {
    const params = new URLSearchParams(search)
    const jid = params.get('job_id')
    if (jid) return jid
  }
  
  return undefined
}

export default function RightCopilotSidebar(props: { open: boolean; onToggle: () => void; width?: number; handleWidth?: number }) {
  const { message } = App.useApp()
  const { open, onToggle, width = 420, handleWidth = 56 } = props
  const location = useLocation()
  const navigate = useNavigate()
  const pageKey = useMemo(() => resolvePageKey(location.pathname), [location.pathname])
  const jobId = useMemo(() => resolveJobId(location.pathname, location.search), [location.pathname, location.search])

  const chatRef = useRef<HTMLDivElement | null>(null)
  const [guide, setGuide] = useState<string>('')
  const [loadingGuide, setLoadingGuide] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try { const raw = localStorage.getItem(`copilot_sidebar_chat_global`); return raw ? JSON.parse(raw) : [] } catch { return [] }
  })
  const [input, setInput] = useState('')
  const [images, setImages] = useState<string[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error'>('idle')
  const [controller, setController] = useState<AbortController | null>(null)
  const statusRef = useRef(status)
  useEffect(() => { statusRef.current = status }, [status])
  const accRef = useRef<string>('')
  const pendingRef = useRef<string>('')
  const actionExecutedRef = useRef(false)
  const typingTimerRef = useRef<number | null>(null)

  useEffect(() => {
    // try { const raw = localStorage.getItem(`copilot_sidebar_chat_${pageKey}`); setMessages(raw ? JSON.parse(raw) : []) } catch { setMessages([]) }
  }, [pageKey])

  useEffect(() => {
    localStorage.setItem(`copilot_sidebar_chat_global`, JSON.stringify(messages))
    try {
      const el = chatRef.current
      if (el) el.scrollTop = el.scrollHeight
    } catch {}
  }, [messages])

  useEffect(() => {
    if (!open) return
    setLoadingGuide(true)
    fetchAssistantGuide(pageKey).then((r) => setGuide(r.text || '')).catch(() => setGuide('')).finally(() => setLoadingGuide(false))
  }, [open, pageKey])

  // Polling for job status to provide proactive notifications
  const lastStatusRef = useRef<any>(null)
  useEffect(() => {
    if (!jobId || !open) return
    
    let isMounted = true
    const poll = async () => {
      try {
        const res = await api.get(`/status/${jobId}`)
        const st = res.data
        const last = lastStatusRef.current
        
        if (last) {
            // Check for completion
            if (last.running && !st.running) {
                const msg = st.success ? '✅ Execution finished successfully!' : '❌ Execution failed.'
                setMessages(prev => [...prev, { role: 'assistant', content: `${msg} You can check the results now.` }])
            }
            // Check for report ready
            if (!last.report_ready && st.report_ready) {
                setMessages(prev => [...prev, { role: 'assistant', content: '📊 Report is ready! Click the Report Viewer to see it.' }])
            }
            // Check for step increment
            if (st.running && st.current_step > last.current_step) {
                setMessages(prev => [...prev, { role: 'assistant', content: `✅ Step ${last.current_step + 1} completed. Proceeding to step ${st.current_step + 1}...` }])
            }
        }
        lastStatusRef.current = st
      } catch {}
      
      if (isMounted) setTimeout(poll, 3000)
    }
    
    poll()
    return () => { isMounted = false }
  }, [jobId, open])

  const abort = () => { if (controller) controller.abort() }
  const resetChat = () => { setMessages([]); localStorage.removeItem(`copilot_sidebar_chat_global`) }
  const copyText = async (text: string) => { try { await navigator.clipboard.writeText(text || ''); message.success('已复制') } catch {} }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      Array.from(e.target.files).forEach(file => {
        const reader = new FileReader()
        reader.onload = (evt) => {
          if (evt.target?.result) {
            setImages(prev => [...prev, evt.target!.result as string])
          }
        }
        reader.readAsDataURL(file)
      })
      e.target.value = ''
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        e.preventDefault()
        const blob = items[i].getAsFile()
        if (blob) {
          const reader = new FileReader()
          reader.onload = (evt) => {
            if (evt.target?.result) {
              setImages(prev => [...prev, evt.target!.result as string])
            }
          }
          reader.readAsDataURL(blob)
        }
      }
    }
  }

  const removeImage = (index: number) => {
    setImages(prev => prev.filter((_, i) => i !== index))
  }

  const send = async () => {
    const content = input.trim()
    if ((!content && images.length === 0) || status === 'streaming') return
    const next: ChatMessage[] = [...messages, { role: 'user', content, images: images.length > 0 ? images : undefined }]
    setMessages(next)
    setInput('')
    setImages([])
    const ctl = new AbortController()
    setController(ctl)
    setStatus('connecting')
    setMessages((prev) => [...prev, Object.assign({ role: 'assistant', content: '' } as ChatMessage, { __streaming: true })])
    accRef.current = ''
    pendingRef.current = ''
    actionExecutedRef.current = false

    // Try to get page context
    let context: any = undefined
    try {
      const rawCtx = localStorage.getItem('copilot_active_context')
      if (rawCtx) {
        context = JSON.parse(rawCtx)
      }
    } catch {}

    await assistantChatStream(
      { page_key: pageKey, pathname: location.pathname, job_id: jobId, messages: next, context },
      (t) => {
        setStatus('streaming')
        pendingRef.current += (t || '')
        if (!typingTimerRef.current) {
          typingTimerRef.current = window.setInterval(() => {
            const step = Math.max(2, Math.min(24, Math.ceil(pendingRef.current.length / 40)))
            if (pendingRef.current.length > 0) {
              const emit = pendingRef.current.slice(0, step)
              pendingRef.current = pendingRef.current.slice(step)
              accRef.current = accRef.current + emit

              // Parse and execute frontend actions
              let displayContent = accRef.current
              
              // 1. Frontend Actions
              const actionRegex = /<frontend_action\s+type="([^"]+)"\s+path="([^"]+)"\s*\/>/g
              let match
              while ((match = actionRegex.exec(accRef.current)) !== null) {
                if (!actionExecutedRef.current) {
                  const [fullTag, type, path] = match
                  if (type === 'navigate') {
                    actionExecutedRef.current = true // Only execute once per stream
                    navigate(path)
                    message.success('正在跳转...')
                  }
                }
                displayContent = displayContent.replace(match[0], '')
              }

              // 2. Server Actions
              const serverActionRegex = /<server_action\s+type="([^"]+)"\s+job_id="([^"]+)">([\s\S]*?)<\/server_action>/g
              let smatch
              while ((smatch = serverActionRegex.exec(accRef.current)) !== null) {
                if (!actionExecutedRef.current) {
                  const [fullTag, type, jid, payloadStr] = smatch
                  if (type === 'update_plan') {
                     actionExecutedRef.current = true
                     try {
                        const payload = JSON.parse(payloadStr)
                        api.post('/plan/update', { job_id: jid, plan: payload.plan })
                           .then(() => message.success('Plan updated successfully'))
                           .catch(() => message.error('Failed to update plan'))
                     } catch (e) { console.error(e) }
                  }
                }
                displayContent = displayContent.replace(smatch[0], '')
              }

              const last = { role: 'assistant', content: displayContent } as ChatMessage
              setMessages((prev) => {
                const arr = [...prev]
                const idx = [...arr].reverse().findIndex((m) => (m as any).__streaming)
                const realIdx = idx >= 0 ? arr.length - 1 - idx : -1
                if (realIdx >= 0) { arr[realIdx] = last; (arr[realIdx] as any).__streaming = true; return arr }
                return [...arr, Object.assign(last, { __streaming: true })]
              })
            }
            if (pendingRef.current.length === 0 && statusRef.current !== 'streaming') {
              if (typingTimerRef.current) { clearInterval(typingTimerRef.current); typingTimerRef.current = null }
              // Final cleanup of tags
              setMessages((prev) => prev.map((m) => {
                const content = (m as any).content || ''
                const clean = content.replace(/<frontend_action\s+[^>]*\/>/g, '').replace(/<server_action\s+[^>]*>[\s\S]*?<\/server_action>/g, '')
                return { role: m.role as any, content: clean }
              }))
            }
          }, 20)
        }
      },
      (st) => setStatus(st),
      ctl.signal,
    ).catch(() => setStatus('error'))
    setController(null)
    if (!typingTimerRef.current) {
      // Final cleanup in case of fast completion
      setMessages((prev) => prev.map((m) => {
        const content = (m as any).content || ''
        const clean = content.replace(/<frontend_action\s+[^>]*\/>/g, '').replace(/<server_action\s+[^>]*>[\s\S]*?<\/server_action>/g, '')
        return { role: m.role as any, content: clean }
      }))
    }
  }

  const quickPrompts = [
    '我应该如何新建一个研究项目？',
    '我现在所在页面能做什么？',
    '如何上传数据并生成报告？',
    '如何解释当前页面的字段/按钮含义？',
  ]

  return (
    <div
      className={`copilot-sider ${open ? 'copilot-sider--open' : 'copilot-sider--collapsed'}`}
      style={{
        ['--copilot-sider-width' as any]: `${width}px`,
        ['--copilot-handle-width' as any]: `${handleWidth}px`,
      }}
      aria-label="Copilot Sidebar"
    >
      {!open && (
        <div className="copilot-collapsed-strip" onClick={onToggle} title="展开 Copilot">
            <div className="copilot-collapsed-icon">
                <RobotOutlined style={{ fontSize: 24, color: 'var(--copilot-accent)' }} />
            </div>
            <div className="copilot-collapsed-text">AI ASSISTANT</div>
        </div>
      )}

      <div className="copilot-sider__inner" style={{ display: open ? 'flex' : 'none' }}>
        <div className="copilot-sider__top">
          <div className="copilot-sider__title">
            <Space size={8}>
              <span className="copilot-sider__badge"><ThunderboltOutlined /></span>
              <span>Copilot</span>
            </Space>
            <Space size={6}>
              {status !== 'idle' && <Tag className="copilot-status" color={status === 'error' ? 'red' : (status === 'done' ? 'green' : 'gold')}>{status}</Tag>}
              <Tooltip title="清空对话">
                <Button size="small" type="text" icon={<DeleteOutlined />} onClick={resetChat} />
              </Tooltip>
              <Button size="small" type="text" icon={<CloseOutlined />} onClick={onToggle} />
            </Space>
          </div>

          <div className="copilot-sider__meta">
            <Space size={6} wrap>
              <Tag color="cyan">{pageKey}</Tag>
              {!!jobId && <Tag color="blue">job: {jobId}</Tag>}
              <Tag className="copilot-path" color="default">{location.pathname}</Tag>
            </Space>
          </div>

          <Collapse
            size="small"
            bordered={false}
            defaultActiveKey={guide ? ['guide'] : []}
            className="copilot-collapse"
            items={[
              {
                key: 'guide',
                label: '本页指南',
                children: (
                  <div>
                    {loadingGuide ? (
                      <Typography.Text type="secondary">加载中…</Typography.Text>
                    ) : (
                      <Typography.Paragraph className="copilot-guide">
                        {guide || '还没有针对本页的指南。你可以直接提问：如何使用本页功能、每个按钮的含义、推荐流程等。'}
                      </Typography.Paragraph>
                    )}
                    <div className="copilot-quick">
                      {quickPrompts.map((t) => (
                        <button key={t} className="copilot-chip" onClick={() => setInput(t)}>{t}</button>
                      ))}
                    </div>
                  </div>
                ),
              }
            ]}
          />
        </div>

        <div className="copilot-sider__chat" ref={chatRef}>
          {messages.length === 0 && (
            <div className="copilot-empty">
              <div className="copilot-empty__logo">
                <div className="copilot-logo-pulse" />
                <RobotOutlined style={{ fontSize: 32, color: '#fff' }} />
              </div>
              <div className="copilot-empty__title">Research Copilot</div>
              <div className="copilot-empty__desc">
                我是您的科研助手。我可以协助您分析数据、撰写报告或解答项目疑问。
              </div>
              <div className="copilot-suggestions">
                {quickPrompts.map((t, i) => (
                  <div key={i} className="copilot-suggestion-card" onClick={() => setInput(t)}>
                    <div className="copilot-suggestion-icon"><ThunderboltOutlined /></div>
                    <div className="copilot-suggestion-text">{t}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`copilot-row ${m.role === 'user' ? 'copilot-row--user' : 'copilot-row--assistant'}`}>
              {m.role === 'assistant' && (
                <div className="copilot-avatar-container">
                  <Avatar size={32} icon={<RobotOutlined />} className="copilot-avatar" />
                </div>
              )}
              <div className={`copilot-msg ${m.role === 'user' ? 'copilot-msg--user' : 'copilot-msg--assistant'}`}>
                {m.role === 'assistant' && <div className="copilot-msg__header">AI Assistant</div>}
                <div className="copilot-msg__content">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                  {m.images && m.images.length > 0 && (
                    <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {m.images.map((img, idx) => (
                        <Image key={idx} src={img} width={100} style={{ borderRadius: 4, objectFit: 'cover' }} />
                      ))}
                    </div>
                  )}
                </div>
                {m.role === 'assistant' && (
                  <div className="copilot-msg__actions">
                    <Tooltip title="复制内容">
                      <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => copyText(m.content)} />
                    </Tooltip>
                  </div>
                )}
              </div>
            </div>
          ))}
          {status === 'streaming' || status === 'connecting' ? (
             <div className="copilot-row copilot-row--assistant">
               <div className="copilot-avatar-container">
                  <Avatar size={32} icon={<RobotOutlined />} className="copilot-avatar copilot-avatar--thinking" />
               </div>
               <div className="copilot-msg copilot-msg--assistant copilot-msg--thinking">
                 <div className="typing-indicator">
                   <span></span><span></span><span></span>
                 </div>
               </div>
             </div>
          ) : null}
        </div>

        <div className="copilot-sider__input">
          <div className="copilot-input-container">
            {images.length > 0 && (
              <div className="copilot-image-preview">
                {images.map((img, i) => (
                  <div key={i} className="copilot-image-item">
                    <Image src={img} width={48} height={48} style={{ objectFit: 'cover' }} preview={false} />
                    <div className="copilot-image-remove" onClick={() => removeImage(i)}>
                      <CloseOutlined />
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="copilot-input-wrapper">
              <Input.TextArea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPaste={handlePaste}
                placeholder="输入指令或提问..."
                autoSize={{ minRows: 1, maxRows: 4 }}
                onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send() } }}
                className="copilot-textarea"
              />
              <div className="copilot-input-actions">
                <input type="file" accept="image/*" multiple ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileSelect} />
                <Tooltip title="上传图片">
                  <Button type="text" shape="circle" icon={<PictureOutlined />} onClick={() => fileInputRef.current?.click()} />
                </Tooltip>
                <Button 
                  type="primary" 
                  shape="circle" 
                  icon={status === 'connecting' || status === 'streaming' ? <PauseCircleOutlined /> : <SendOutlined />} 
                  onClick={status === 'connecting' || status === 'streaming' ? abort : send}
                  disabled={(!input.trim() && images.length === 0) && status !== 'streaming' && status !== 'connecting'}
                  className="copilot-send-btn"
                />
              </div>
            </div>
          </div>
          <div className="copilot-footer-text">
            AI 生成内容仅供参考，请核实重要信息。
          </div>
        </div>
      </div>
    </div>
  )
}
