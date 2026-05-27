import React, { useEffect, useRef, useMemo } from 'react'
import { Card, Typography, Space, Collapse } from 'antd'
import { CheckCircleOutlined, CodeOutlined, ToolOutlined, RightSquareOutlined, WarningOutlined } from '@ant-design/icons'
import CodeViewer from './CodeViewer'

const { Text, Paragraph } = Typography
const { Panel } = Collapse

export type BlockType = 'text' | 'command' | 'output' | 'tool' | 'code' | 'error'

export interface LogBlock {
  id: string
  type: BlockType
  content: string[]
  language?: string
}

function parseLogs(rawText: string): LogBlock[] {
  // 1. Strip ANSI codes
  const text = rawText.replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '')
  const lines = text.split('\n')
  const blocks: LogBlock[] = []
  
  let currentBlock: Omit<LogBlock, 'id'> | null = null
  let inCodeBlock = false
  let codeLang = ''

  const commitBlock = () => {
    if (currentBlock && currentBlock.content.length > 0) {
      blocks.push({ ...currentBlock, id: `block-${blocks.length}` })
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    
    // Code block toggle
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        if (currentBlock) {
          // Remove the closing backticks line if we want to cleanly use CodeViewer
          // But let's just keep it or slice it out
        }
        commitBlock()
        currentBlock = null
        inCodeBlock = false
      } else {
        commitBlock()
        inCodeBlock = true
        codeLang = line.slice(3).trim()
        currentBlock = { type: 'code', content: [], language: codeLang }
      }
      continue
    }

    if (inCodeBlock) {
      if (!currentBlock) currentBlock = { type: 'code', content: [], language: codeLang }
      currentBlock.content.push(line)
      continue
    }

    // Tool/Model marker
    if (line.startsWith('> ') || line.trim().startsWith('→ ') || line.trim().startsWith('✱ ')) {
      commitBlock()
      blocks.push({ id: `block-${blocks.length}`, type: 'tool', content: [line] })
      continue
    }

    // Action marker
    if (line.startsWith('⚙ ')) {
      commitBlock()
      currentBlock = { type: 'tool', content: [line] }
      continue
    }

    // Command marker
    if (line.startsWith('$ ')) {
      commitBlock()
      blocks.push({ id: `block-${blocks.length}`, type: 'command', content: [line.slice(2)] })
      currentBlock = { type: 'output', content: [] }
      continue
    }

    // Error marker
    if (line.toLowerCase().includes('error:') || line.toLowerCase().includes('exception:')) {
      if (currentBlock?.type !== 'error') {
        commitBlock()
        currentBlock = { type: 'error', content: [] }
      }
      currentBlock.content.push(line)
      continue
    }

    // Blank lines
    if (line.trim() === '') {
      if (currentBlock && (currentBlock.type === 'tool' || currentBlock.type === 'command')) {
        commitBlock()
        currentBlock = null
      } else if (currentBlock) {
        currentBlock.content.push(line)
      }
      continue
    }

    // Default text
    if (!currentBlock) {
      currentBlock = { type: 'text', content: [line] }
    } else {
      currentBlock.content.push(line)
    }
  }

  commitBlock()

  // Cleanup: trim leading/trailing blank lines in blocks
  return blocks.map(b => {
    let c = [...b.content]
    while(c.length > 0 && c[0].trim() === '') c.shift()
    while(c.length > 0 && c[c.length - 1].trim() === '') c.pop()
    return { ...b, content: c }
  }).filter(b => b.content.length > 0)
}

export default function StructuredLogViewer({ log }: { log: string }) {
  const blocks = useMemo(() => parseLogs(log || ''), [log])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'auto', block: 'end' })
    }
  }, [blocks.length, log])

  const renderBlock = (block: LogBlock) => {
    const textContent = block.content.join('\n')
    
    switch (block.type) {
      case 'tool':
        return (
          <div key={block.id} style={{ marginBottom: 12, padding: '8px 12px', backgroundColor: '#f0f5ff', borderRadius: 6, borderLeft: '4px solid #1890ff' }}>
            <Space align="start">
              <ToolOutlined style={{ color: '#1890ff', marginTop: 4 }} />
              <div style={{ color: '#0050b3', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }}>
                {textContent}
              </div>
            </Space>
          </div>
        )
      
      case 'command':
        return (
          <div key={block.id} style={{ marginBottom: 0, padding: '8px 12px', backgroundColor: '#2b2b2b', borderRadius: '6px 6px 0 0', color: '#55ff55', fontFamily: 'monospace', fontSize: 13 }}>
            <Space>
              <RightSquareOutlined />
              <span>{textContent}</span>
            </Space>
          </div>
        )
        
      case 'output':
        return (
          <div key={block.id} style={{ marginBottom: 12, padding: '8px 12px', backgroundColor: '#1e1e1e', borderRadius: '0 0 6px 6px', color: '#d4d4d4', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto' }}>
            {textContent}
          </div>
        )

      case 'code':
        return (
          <div key={block.id} style={{ marginBottom: 12 }}>
            <CodeViewer code={textContent} language={block.language as any || 'python'} collapsed={false} />
          </div>
        )
        
      case 'error':
        return (
          <div key={block.id} style={{ marginBottom: 12, padding: '8px 12px', backgroundColor: '#fff2f0', borderRadius: 6, borderLeft: '4px solid #ff4d4f' }}>
            <Space align="start">
              <WarningOutlined style={{ color: '#ff4d4f', marginTop: 4 }} />
              <div style={{ color: '#cf1322', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }}>
                {textContent}
              </div>
            </Space>
          </div>
        )
        
      case 'text':
      default:
        return (
          <div key={block.id} style={{ marginBottom: 12, fontSize: 14, color: '#333', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
            {textContent}
          </div>
        )
    }
  }

  return (
    <div className="structured-log-viewer" style={{
      backgroundColor: '#fafafa',
      padding: '16px',
      borderRadius: '8px',
      border: '1px solid #f0f0f0',
      maxHeight: '600px',
      overflowY: 'auto'
    }}>
      {blocks.length === 0 && <div style={{ color: '#999', fontStyle: 'italic' }}>等待输出...</div>}
      {blocks.map(renderBlock)}
      <div ref={bottomRef} />
    </div>
  )
}
