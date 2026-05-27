import React, { useEffect, useRef } from 'react'

function ansiToHtml(text: string) {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/\u001b\[0m/g, '</span>')
  html = html.replace(/\u001b\[1m/g, '<span style="font-weight: bold">')
  html = html.replace(/\u001b\[30m/g, '<span style="color: #888">')
  html = html.replace(/\u001b\[31m/g, '<span style="color: #ff5555">')
  html = html.replace(/\u001b\[32m/g, '<span style="color: #55ff55">')
  html = html.replace(/\u001b\[33m/g, '<span style="color: #ffff55">')
  html = html.replace(/\u001b\[34m/g, '<span style="color: #5555ff">')
  html = html.replace(/\u001b\[35m/g, '<span style="color: #ff55ff">')
  html = html.replace(/\u001b\[36m/g, '<span style="color: #55ffff">')
  html = html.replace(/\u001b\[37m/g, '<span style="color: #bbbbbb">')
  html = html.replace(/\u001b\[90m/g, '<span style="color: #888888">')
  html = html.replace(/\u001b\[91m/g, '<span style="color: #ff5555">')
  html = html.replace(/\u001b\[92m/g, '<span style="color: #55ff55">')
  html = html.replace(/\u001b\[93m/g, '<span style="color: #ffff55">')
  html = html.replace(/\u001b\[94m/g, '<span style="color: #5555ff">')
  html = html.replace(/\u001b\[95m/g, '<span style="color: #ff55ff">')
  html = html.replace(/\u001b\[96m/g, '<span style="color: #55ffff">')
  html = html.replace(/\u001b\[97m/g, '<span style="color: #ffffff">')
  // Strip any remaining ANSI codes
  html = html.replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '')

  return html
}

export default function TerminalViewer({ log }: { log: string }) {
  // 确保所有打开的 span 被闭合，防止污染其他 DOM
  const htmlLog = '<span>' + ansiToHtml(log || '') + '</span>'
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [log])

  return (
    <div style={{
      backgroundColor: '#1e1e1e',
      color: '#d4d4d4',
      padding: '16px',
      borderRadius: '8px',
      fontFamily: '"Fira Code", "Courier New", monospace',
      fontSize: '14px',
      lineHeight: '1.5',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-all',
      maxHeight: '400px',
      overflowY: 'auto'
    }}>
      <div dangerouslySetInnerHTML={{ __html: htmlLog }} />
      <div ref={bottomRef} />
    </div>
  )
}
