import React, { useMemo, useState } from 'react'

type NodeValue = any

function isObject(v: any) { return v && typeof v === 'object' && !Array.isArray(v) }
function isArray(v: any) { return Array.isArray(v) }

function summarize(value: NodeValue): string {
  try {
    if (isArray(value)) return `[${value.length}]`
    if (isObject(value)) return `{${Object.keys(value).length}}`
    if (typeof value === 'string') return JSON.stringify(value.length > 40 ? value.slice(0, 40) + '…' : value)
    if (value === null) return 'null'
    return String(value)
  } catch { return '' }
}

export default function JsonTree({ data, defaultCollapsed = true }: { data: NodeValue; defaultCollapsed?: boolean }) {
  const rootKey = 'root'
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const toggle = (path: string) => setOpen((prev) => ({ ...prev, [path]: !prev[path] }))

  const renderNode = (key: string, value: NodeValue, path: string, depth: number): React.ReactNode => {
    const collapsible = isObject(value) || isArray(value)
    const opened = open[path] ?? !defaultCollapsed
    const pad = { paddingLeft: depth * 12 }
    const label = (
      <span>
        <span style={{ color: '#9ca3af' }}>{key}</span>
        <span style={{ color: '#6b7280' }}>: </span>
        {!collapsible && <span style={{ color: typeof value === 'string' ? '#22d3ee' : '#93c5fd' }}>{summarize(value)}</span>}
        {collapsible && <span style={{ color: '#a3a3a3' }}>{summarize(value)}</span>}
      </span>
    )
    return (
      <div key={path} style={pad}>
        {collapsible ? (
          <div style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => toggle(path)}>
            <span style={{ display: 'inline-block', width: 14 }}>{opened ? '▾' : '▸'}</span>
            {label}
          </div>
        ) : (
          <div>{label}</div>
        )}
        {collapsible && opened && (
          <div>
            {isArray(value)
              ? (value as any[]).map((v, i) => renderNode(`[${i}]`, v, `${path}[${i}]`, depth + 1))
              : Object.entries(value || {}).map(([k, v]) => renderNode(k, v, `${path}.${k}`, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  const tree = useMemo(() => {
    return renderNode(rootKey, data, rootKey, 0)
  }, [data, open, defaultCollapsed])

  return (
    <div style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', fontSize: 13, background: '#0b1220', color: '#e5e7eb', borderRadius: 8, padding: 8 }}>
      {tree}
    </div>
  )
}