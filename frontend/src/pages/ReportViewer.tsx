import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Card, Typography, Space, Button, message, Layout, Tree, Progress, Tag } from 'antd'
import ReactMarkdown from 'react-markdown'
import { fetchReport, regenReport, fetchReportStatus, fetchReportPreview } from '../api/research'
import '../assets/markdown.css'

const { Title } = Typography

type HeadingItem = { level: number; text: string; id: string; children?: HeadingItem[] }

function slugify(text: string) {
  return (text || '')
    .toLowerCase()
    .trim()
    .replace(/[\s]+/g, '-')
    .replace(/[^\p{L}\p{N}-]+/gu, '')
}

function buildToc(markdown: string): { toc: HeadingItem[]; idList: string[] } {
  const lines = (markdown || '').split(/\r?\n/)
  const items: HeadingItem[] = []
  const stack: HeadingItem[] = []
  const idCounts: Record<string, number> = {}
  const idList: string[] = []
  let seq = 1
  lines.forEach((line) => {
    const m = line.match(/^(#{1,6})\s+(.*)$/)
    if (!m) return
    const rawLevel = m[1].length
    const level = Math.min(rawLevel, 3) // 仅到三级，目录与锚点只处理H1-H3
    const text = m[2].trim()
    const base = slugify(text)
    let id = base
    if (!id) {
      id = `section-${seq++}`
    }
    if (idCounts[id] !== undefined) {
      idCounts[id] += 1
      id = `${id}-${idCounts[id]}`
    } else {
      idCounts[id] = 0
    }
    // 仅收集H1-H3的id用于渲染顺序匹配，避免H4+打乱索引
    if (rawLevel <= 3) {
      idList.push(id)
    }
    const node: HeadingItem = { level, text, id, children: [] }
    if (stack.length === 0) {
      items.push(node)
      stack.push(node)
      return
    }
    // 调整栈以适配层级
    while (stack.length && stack[stack.length - 1].level >= level) {
      stack.pop()
    }
    if (stack.length === 0) {
      items.push(node)
      stack.push(node)
    } else {
      const parent = stack[stack.length - 1]
      parent.children = parent.children || []
      parent.children.push(node)
      stack.push(node)
    }
  })
  return { toc: items, idList }
}

export default function ReportViewer() {
  const { jobId } = useParams()
  const [text, setText] = useState<string>('')
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [progress, setProgress] = useState(0)
  const [step, setStep] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!jobId) return
    let timer: any
    fetchReportStatus(jobId).then((st) => {
      setProgress(st.progress || 0)
      setStep(st.step || '')
      const isRunning = st.state === 'running'
      setRunning(isRunning)
      if (isRunning) {
        timer = setInterval(async () => {
          try {
            const s = await fetchReportStatus(jobId)
            setProgress(s.progress || 0)
            setStep(s.step || '')
            if (s.state === 'running') {
              try {
                const pv = await fetchReportPreview(jobId)
                setText(pv || '')
              } catch {}
            } else {
              clearInterval(timer)
              setRunning(false)
              if (s.state === 'done') {
                const t = await fetchReport(jobId)
                setText(t)
              }
            }
          } catch {
            clearInterval(timer)
            setRunning(false)
          }
        }, 1000)
      } else {
        fetchReport(jobId).then(setText).catch(() => setText('报告获取失败'))
      }
    }).catch(() => {
      fetchReport(jobId).then(setText).catch(() => setText('报告获取失败'))
    })
    return () => { if (timer) clearInterval(timer) }
  }, [jobId])

  const blobToDataUrl = async (blob: Blob): Promise<string> => {
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = (e) => reject(e)
      reader.readAsDataURL(blob)
    })
  }

  const inlineImages = async (root: HTMLElement) => {
    const imgs = Array.from(root.querySelectorAll('img')) as HTMLImageElement[]
    for (const img of imgs) {
      const src = img.getAttribute('src') || ''
      if (!src || src.startsWith('data:')) continue
      try {
        const resp = await fetch(src, { mode: 'cors' })
        if (!resp.ok) continue
        const blob = await resp.blob()
        const dataUrl = await blobToDataUrl(blob)
        img.setAttribute('src', dataUrl)
        img.setAttribute('crossorigin', 'anonymous')
      } catch (e) {
        // 忽略单张图片失败，继续处理其他图片
        continue
      }
    }
  }

  const downloadMarkdown = () => {
    if (!text) { message.warning('暂无可下载的报告'); return }
    try {
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report_${jobId || 'unknown'}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      message.error('下载失败')
    }
  }

  const exportPDF = async () => {
    try {
      const el = containerRef.current
      if (!el) { message.warning('暂无可导出的内容'); return }
      // 优先使用全局已加载的html2pdf，否则从CDN动态加载
      const getHtml2Pdf = async (): Promise<any> => {
        const w = window as any
        if (w.html2pdf) return w.html2pdf
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement('script')
          s.src = 'https://cdn.staticfile.net/html2pdf.js/0.10.2/html2pdf.bundle.min.js'
          s.async = true
          s.onload = () => resolve()
          s.onerror = () => reject(new Error('html2pdf加载失败'))
          document.body.appendChild(s)
        })
        return (window as any).html2pdf
      }
      // 先将容器内图片内联为dataURL，避免跨域导致的canvas污染
      await inlineImages(el)
      const html2pdf = await getHtml2Pdf()
      const opt = {
        margin: [10, 10, 10, 10],
        filename: `report_${jobId || 'unknown'}.pdf`,
        image: { type: 'jpeg', quality: 0.95 },
        html2canvas: { scale: 2, useCORS: true, allowTaint: false, scrollY: 0 },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: { mode: ['css', 'legacy'], avoid: ['.md-code', '.md-table', '.md-img', '.md-figure'] },
      }
      await html2pdf().set(opt).from(el).save()
    } catch (e) {
      message.error('PDF导出失败，请稍后重试')
    }
  }

  const exportDocxPlaceholder = () => {
    message.info('DOCX导出功能预留，后续版本支持')
  }

  const { toc, idList } = useMemo(() => buildToc(text), [text])
  const [tocCollapsed, setTocCollapsed] = useState(false)
  const headingRenderIndexRef = useRef(0)

  // 每次文本变化时重置标题渲染索引，保证id与目录顺序一致
  useEffect(() => {
    headingRenderIndexRef.current = 0
  }, [text])

  const scrollToId = (id: string) => {
    const esc = (s: string) => (window.CSS && (CSS as any).escape ? (CSS as any).escape(s) : s.replace(/[^\w-]/g, ''))
    const el = containerRef.current?.querySelector(`#${esc(id)}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  const treeData = (nodes: HeadingItem[]): DataNode[] => nodes.map(n => ({
    key: n.id,
    title: <a onClick={() => scrollToId(n.id)}>{n.text}</a>,
    children: n.children && n.children.length ? treeData(n.children) : undefined,
  }))

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <Title level={3} style={{ margin: 0 }}>报告预览</Title>
        <Space>
          <Link to="/projects"><Button>返回</Button></Link>
          <Progress percent={progress} status={running ? 'active' : (progress >= 100 ? 'success' : 'normal')} />
          {step && <Tag color="blue">{step}</Tag>}
          <Link to={`/compose/${jobId}`}><Button>重新生成报告（交互）</Button></Link>
          <Button onClick={() => setTocCollapsed(v => !v)}>{tocCollapsed ? '显示目录' : '隐藏目录'}</Button>
          <Button onClick={exportPDF} type="primary">导出PDF</Button>
          <Button onClick={downloadMarkdown}>下载Markdown</Button>
          <Button onClick={exportDocxPlaceholder} disabled>导出DOCX（预留）</Button>
        </Space>
      </div>
      <Layout style={{ background: 'transparent', minHeight: 600 }}>
        <Layout.Sider
          collapsible
          collapsed={tocCollapsed}
          onCollapse={(v) => setTocCollapsed(v)}
          width={260}
          theme="light"
          style={{
            background: '#fff',
            padding: 12,
            borderRight: '1px solid #f0f0f0',
            position: 'sticky',
            top: 64,
            height: 'calc(100vh - 64px)',
            overflow: 'auto',
            alignSelf: 'flex-start',
          }}
        >
          <Title level={5} style={{ marginTop: 0 }}>目录</Title>
          <Tree treeData={treeData(toc)} defaultExpandAll />
        </Layout.Sider>
        <Layout.Content style={{ padding: '0 16px' }}>
          {/* 将报告中的图片URL（/static/jobs/...）前置为后端基地址，确保在前端开发环境下可正确加载 */}
          <div className="md-container" ref={containerRef}>
            <ReactMarkdown
              components={{
                h1: ({ node, children, ...props }) => {
                  const idx = headingRenderIndexRef.current++
                  const id = idList[idx] || `section-${idx + 1}`
                  return <h1 id={id} className="md-h1" {...props}>{children}</h1>
                },
                h2: ({ node, children, ...props }) => {
                  const idx = headingRenderIndexRef.current++
                  const id = idList[idx] || `section-${idx + 1}`
                  return <h2 id={id} className="md-h2" {...props}>{children}</h2>
                },
                h3: ({ node, children, ...props }) => {
                  const idx = headingRenderIndexRef.current++
                  const id = idList[idx] || `section-${idx + 1}`
                  return <h3 id={id} className="md-h3" {...props}>{children}</h3>
                },
                p: ({ node, ...props }) => <p className="md-p" {...props} />,
                blockquote: ({ node, ...props }) => <blockquote className="md-quote" {...props} />,
                pre: ({ node, ...props }) => <pre className="md-code" {...props} />,
                code: ({ node, className, children, ...props }) => (
                  <code className={className} {...props}>{children}</code>
                ),
                ul: ({ node, ...props }) => <ul className="md-ul" {...props} />,
                ol: ({ node, ...props }) => <ol className="md-ol" {...props} />,
                table: ({ node, ...props }) => <table className="md-table" {...props} />,
                img: ({ node, ...props }) => {
                  const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
                  const prefix = baseApi.replace(/\/api$/, '')
                  const src = (props.src || '')
                  const finalSrc = src.startsWith('/static/') ? `${prefix}${src}` : src
                  return (
                    <div className="md-figure">
                      <img {...props} src={finalSrc} className="md-img" crossOrigin="anonymous" />
                    </div>
                  )
                },
                a: ({ node, ...props }) => <a className="md-a" target="_blank" rel="noreferrer" {...props} />,
              }}
            >
              {text}
            </ReactMarkdown>
          </div>
        </Layout.Content>
      </Layout>
    </Card>
  )
}
import type { DataNode } from 'antd/es/tree'