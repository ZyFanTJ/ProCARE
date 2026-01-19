import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Button, Input, Space, Tag, Typography, Spin, Tooltip, Avatar } from 'antd'
import { RobotOutlined, CloseOutlined, SendOutlined, PauseCircleOutlined, ReloadOutlined, UserOutlined, CopyOutlined } from '@ant-design/icons'
import { useLocation } from 'react-router-dom'
import { fetchAssistantGuide, assistantChatStream, ChatMessage } from '../api/assistant'
import ReactMarkdown from 'react-markdown'
import '../assets/copilot.css'

type Pos = { x: number; y: number }

function resolvePageKey(pathname: string) {
  if (pathname.startsWith('/dashboard')) return 'dashboard'
  if (pathname === '/' || pathname.startsWith('/wizard')) return 'wizard'
  if (pathname.startsWith('/compose')) return 'report-composer'
  if (pathname.startsWith('/report')) return 'report-viewer'
  if (pathname.startsWith('/projects')) return 'projects'
  if (pathname.startsWith('/files')) return 'files'
  if (pathname.startsWith('/templates')) return 'templates'
  if (pathname.startsWith('/settings')) return 'settings'
  return 'unknown'
}

function resolveJobId(pathname: string) {
  const m1 = pathname.match(/^\/report\/([^\/]+)/)
  if (m1) return m1[1]
  const m2 = pathname.match(/^\/compose\/([^\/]+)/)
  if (m2) return m2[1]
  return undefined
}

export default function CoPilot() {
  const location = useLocation()
  const pageKey = useMemo(() => resolvePageKey(location.pathname), [location.pathname])
  const jobId = useMemo(() => resolveJobId(location.pathname), [location.pathname])
  const [open, setOpen] = useState<boolean>(() => {
    try { const s = localStorage.getItem('copilot_open'); return s ? JSON.parse(s) : true } catch { return true }
  })
  const [pos, setPos] = useState<Pos>(() => {
    try { const raw = localStorage.getItem('copilot_pos'); if (raw) return JSON.parse(raw) } catch {}
    return { x: window.innerWidth - 380 - 16, y: Math.max(64, Math.floor(window.innerHeight * 0.3)) }
  })
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef<{ ox: number; oy: number; w: number; h: number } | null>(null)
  const dragKindRef = useRef<'panel' | 'fab' | null>(null)
  const dragStartRef = useRef<{ sx: number; sy: number } | null>(null)
  const didDragRef = useRef<boolean>(false)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const chatRef = useRef<HTMLDivElement | null>(null)
  const [fabDocked, setFabDocked] = useState<boolean>(() => {
    try { const s = localStorage.getItem('copilot_fab_docked'); return s ? JSON.parse(s) : true } catch { return true }
  })
  const [guide, setGuide] = useState<string>('')
  const [loadingGuide, setLoadingGuide] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try { const raw = localStorage.getItem(`copilot_chat_${pageKey}`); return raw ? JSON.parse(raw) : [] } catch { return [] }
  })
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<'idle' | 'connecting' | 'streaming' | 'done' | 'interrupted' | 'error'>('idle')
  const [controller, setController] = useState<AbortController | null>(null)
  const statusRef = useRef(status)
  useEffect(() => { statusRef.current = status }, [status])
  const accRef = useRef<string>('')
  const pendingRef = useRef<string>('')
  const typingTimerRef = useRef<number | null>(null)

  useEffect(() => {
    localStorage.setItem('copilot_open', JSON.stringify(open))
  }, [open])

  useEffect(() => {
    localStorage.setItem('copilot_pos', JSON.stringify(pos))
  }, [pos])

  useEffect(() => {
    localStorage.setItem('copilot_fab_docked', JSON.stringify(fabDocked))
  }, [fabDocked])

  useEffect(() => {
    try { const raw = localStorage.getItem(`copilot_chat_${pageKey}`); setMessages(raw ? JSON.parse(raw) : []) } catch { setMessages([]) }
  }, [pageKey])

  useEffect(() => {
    localStorage.setItem(`copilot_chat_${pageKey}`, JSON.stringify(messages))
    // 滚动到底部
    try {
      const el = chatRef.current
      if (el) el.scrollTop = el.scrollHeight
    } catch {}
  }, [messages, pageKey])

  useEffect(() => {
    if (!open) return
    setLoadingGuide(true)
    fetchAssistantGuide(pageKey).then((r) => setGuide(r.text || '')).catch(() => setGuide('')).finally(() => setLoadingGuide(false))
  }, [open, pageKey])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging || !dragRef.current) return
      const { ox, oy, w, h } = dragRef.current
      if (dragStartRef.current) {
        const dx = Math.abs(e.clientX - dragStartRef.current.sx)
        const dy = Math.abs(e.clientY - dragStartRef.current.sy)
        if (!didDragRef.current && (dx > 3 || dy > 3)) didDragRef.current = true
      }
      const nx = Math.min(Math.max(0, e.clientX - ox), Math.max(0, window.innerWidth - w))
      const ny = Math.min(Math.max(0, e.clientY - oy), Math.max(0, window.innerHeight - h))
      setPos({ x: nx, y: ny })
    }
    const onUp = () => { setDragging(false); dragRef.current = null }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [dragging])


  const startDrag = (e: React.MouseEvent) => {
    setDragging(true)
    dragKindRef.current = 'panel'
    dragStartRef.current = { sx: e.clientX, sy: e.clientY }
    didDragRef.current = false
    const rect = panelRef.current ? panelRef.current.getBoundingClientRect() : ({ left: 0, top: 0, width: 360, height: 300 } as DOMRect)
    const w = (rect as any).width || 360
    const h = (rect as any).height || 300
    dragRef.current = { ox: e.clientX - (rect as any).left, oy: e.clientY - (rect as any).top, w, h }
  }

  const onPanelMouseDown = (e: React.MouseEvent) => {
    const el = e.target as HTMLElement
    const inHeader = !!el.closest('.ant-card-head') || !!el.closest('.copilot-header')
    if (inHeader) startDrag(e)
  }

  const startFabDrag = (e: React.MouseEvent) => {
    setDragging(true)
    setFabDocked(false)
    dragKindRef.current = 'fab'
    dragStartRef.current = { sx: e.clientX, sy: e.clientY }
    didDragRef.current = false
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const w = rect.width || 56
    const h = rect.height || 56
    dragRef.current = { ox: e.clientX - rect.left, oy: e.clientY - rect.top, w, h }
  }

  const onFabClick = () => {
    if (dragKindRef.current === 'fab' && didDragRef.current) {
      didDragRef.current = false
      dragKindRef.current = null
      return
    }
    didDragRef.current = false
    dragKindRef.current = null
    setOpen(true)
  }

  const send = async () => {
    const content = input.trim()
    if (!content || status === 'streaming') return
    const next: ChatMessage[] = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    const ctl = new AbortController()
    setController(ctl)
    setStatus('connecting')
    // 预置一条空的助手消息用于流式更新
    setMessages((prev) => [...prev, Object.assign({ role: 'assistant', content: '' } as ChatMessage, { __streaming: true })])
    accRef.current = ''
    pendingRef.current = ''
    await assistantChatStream({ page_key: pageKey, pathname: location.pathname, job_id: jobId, messages: next }, (t) => {
      setStatus('streaming')
      pendingRef.current += (t || '')
      if (!typingTimerRef.current) {
        typingTimerRef.current = window.setInterval(() => {
          const step = Math.max(2, Math.min(24, Math.ceil(pendingRef.current.length / 40)))
          if (pendingRef.current.length > 0) {
            const emit = pendingRef.current.slice(0, step)
            pendingRef.current = pendingRef.current.slice(step)
            accRef.current = accRef.current + emit
            const last = { role: 'assistant', content: accRef.current } as ChatMessage
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
            setMessages((prev) => prev.map((m) => ({ role: m.role as any, content: (m as any).content })))
          }
        }, 20)
      }
    }, (st) => setStatus(st), ctl.signal).catch(() => setStatus('error'))
    setController(null)
    if (!typingTimerRef.current) {
      setMessages((prev) => prev.map((m) => ({ role: m.role as any, content: (m as any).content })))
    }
  }

  const abort = () => { if (controller) controller.abort() }
  const resetChat = () => { setMessages([]); localStorage.removeItem(`copilot_chat_${pageKey}`) }
  const copyText = async (text: string) => {
    try { await navigator.clipboard.writeText(text || '') } catch {}
  }

  return (
    <div>
      {!open && (
        <div className={`copilot-fab ${fabDocked ? 'copilot-fab--docked' : ''}`} style={fabDocked ? undefined : { left: pos.x, top: pos.y }} onMouseDown={startFabDrag}>
          <div className="copilot-fab__bot" onClick={onFabClick} aria-label="Copilot">
            <span className="copilot-fab__eyes" />
            <span className="copilot-fab__ring" />
            <span className="copilot-fab__pulse" />
            <RobotOutlined />
          </div>
        </div>
      )}
      {open && (
        <div ref={panelRef} className="copilot-panel" style={{ left: Math.min(Math.max(8, pos.x), Math.max(8, (typeof window !== 'undefined' ? window.innerWidth : 0) - (panelRef.current?.offsetWidth || 360) - 8)), top: Math.min(Math.max(64, pos.y), Math.max(64, (typeof window !== 'undefined' ? window.innerHeight : 0) - (panelRef.current?.offsetHeight || 300) - 8)) }} onMouseDown={onPanelMouseDown}>
          <Card size="small" title={<div className="copilot-header" onMouseDown={startDrag} onDoubleClick={() => setOpen(false)} style={{ cursor: dragging ? 'grabbing' : 'grab', width: '100%', display: 'flex', alignItems: 'center', gap: 8 }}><RobotOutlined /><span>Copilot</span></div>} extra={
            <Space>
              <Tag color="blue">{pageKey}</Tag>
              <Button type="text" icon={<CloseOutlined />} onClick={() => setOpen(false)} />
            </Space>
          }>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Space size={4} wrap>
                {!!jobId && <Tag>job: {jobId}</Tag>}
                <Tag>{location.pathname}</Tag>
                {status !== 'idle' && <Tag color={status === 'error' ? 'red' : (status === 'done' ? 'green' : 'orange')}>{status}</Tag>}
              </Space>
              <div className="copilot-guide">
                {loadingGuide ? <Spin /> : (guide ? <Typography.Paragraph>{guide}</Typography.Paragraph> : <Typography.Text type="secondary">未加载指南</Typography.Text>)}
              </div>
              <div className="copilot-chat" ref={chatRef}>
                {messages.map((m, i) => (
                  <div key={i} className={m.role === 'user' ? 'copilot-row copilot-row--user' : 'copilot-row copilot-row--assistant'}>
                    {m.role === 'assistant' && <Avatar className="copilot-avatar" size={28} icon={<RobotOutlined />} />}
                    <div className={m.role === 'user' ? 'copilot-msg copilot-msg--user' : 'copilot-msg copilot-msg--assistant'}>
                      <ReactMarkdown>{m.content}</ReactMarkdown>
                      {m.role === 'assistant' && (
                        <div className="copilot-msg__actions">
                          <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => copyText(m.content)}>复制</Button>
                        </div>
                      )}
                    </div>
                    {m.role === 'user' && <Avatar className="copilot-avatar" size={28} icon={<UserOutlined />} />}
                  </div>
                ))}
              </div>
              <div className="copilot-input">
                <Input.TextArea rows={2} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Shift+Enter 换行，Enter 发送" onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send() } }} />
                <div className="copilot-input__actions">
                  <Button type="primary" icon={<SendOutlined />} onClick={send} disabled={!input.trim() || status === 'streaming'}>发送</Button>
                  {(status === 'connecting' || status === 'streaming') && <Button danger icon={<PauseCircleOutlined />} onClick={abort}>中断</Button>}
                  <Button icon={<ReloadOutlined />} onClick={resetChat}>重置</Button>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}