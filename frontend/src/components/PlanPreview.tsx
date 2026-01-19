import React, { useMemo } from 'react'
import { Card, List, Space, Tag, Typography } from 'antd'

type AnyObj = Record<string, any>

function stepTitle(s: any, i: number): string {
  const name = (s && typeof s === 'object') ? (s.name || s.step || s.type || `步骤 ${i + 1}`) : `步骤 ${i + 1}`
  return String(name)
}

function stepMeta(s: AnyObj): Array<{ label: string; value: string }> {
  const m: Array<{ label: string; value: string }> = []
  const target = s.target || s.sheet || s.table || ''
  if (target) m.push({ label: '目标', value: String(target) })
  const cols = s.columns || s.fields || s.features || s.concepts || []
  if (Array.isArray(cols) && cols.length) m.push({ label: '字段', value: cols.slice(0, 8).join(', ') })
  const filt = s.filters || s.where || s.criteria || ''
  if (filt && typeof filt === 'string') m.push({ label: '筛选', value: filt })
  const out = s.output || s.artifact || s.save || ''
  if (out) m.push({ label: '输出', value: String(out) })
  const model = s.model || s.analysis || s.method || ''
  if (model) m.push({ label: '方法', value: String(model) })
  return m
}

function StepItem({ s, i }: { s: any; i: number }) {
  const title = stepTitle(s, i)
  const desc = (s && typeof s === 'object') ? (s.description || s.desc || '') : (typeof s === 'string' ? s : '')
  const meta = (s && typeof s === 'object') ? stepMeta(s as AnyObj) : []
  const extraTags: string[] = []
  if (s && typeof s === 'object') {
    const target = s.target || s.sheet || ''
    if (target) extraTags.push(String(target))
    const kind = s.kind || s.type || ''
    if (kind) extraTags.push(String(kind))
  }
  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space>
          <Tag color="green">{i + 1}</Tag>
          <Typography.Text strong>{title}</Typography.Text>
          {extraTags.map((t, idx) => (<Tag key={idx} color="geekblue">{t}</Tag>))}
        </Space>
      </Space>
      {desc && <div style={{ marginTop: 6 }}><Typography.Text>{desc}</Typography.Text></div>}
      {!!meta.length && (
        <List
          size="small"
          dataSource={meta}
          renderItem={(item) => (
            <List.Item>
              <Space>
                <Typography.Text type="secondary">{item.label}:</Typography.Text>
                <Typography.Text>{item.value}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      )}
    </Card>
  )
}

export default function PlanPreview({ plan }: { plan: AnyObj }) {
  const objective = String(plan?.objective || plan?.topic || '')
  const steps: any[] = Array.isArray(plan?.steps) ? plan.steps : []
  const artifacts = plan?.artifacts || {}
  const hasArtifacts = artifacts && typeof artifacts === 'object'
  const artList = useMemo(() => {
    const arr: Array<{ k: string; v: string }> = []
    Object.entries(artifacts || {}).forEach(([k, v]) => arr.push({ k, v: String(v) }))
    return arr
  }, [artifacts])
  return (
    <div>
      {!!objective && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Typography.Text strong>研究目标</Typography.Text>
          <div style={{ marginTop: 6 }}><Typography.Text>{objective}</Typography.Text></div>
        </Card>
      )}
      <Card size="small" title="步骤">
        {steps.length ? steps.map((s, i) => (<StepItem key={i} s={s} i={i} />)) : <Typography.Text type="secondary">无步骤</Typography.Text>}
      </Card>
      {hasArtifacts && (
        <Card size="small" title="产出" style={{ marginTop: 12 }}>
          <List
            size="small"
            dataSource={artList}
            renderItem={(it) => (
              <List.Item>
                <Space>
                  <Typography.Text type="secondary">{it.k}:</Typography.Text>
                  <Typography.Text>{it.v}</Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      )}
    </div>
  )
}