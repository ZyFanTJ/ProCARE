import { useEffect, useState } from 'react'
import { Card, Typography, Checkbox, List, Button, Space, message, Tag } from 'antd'

export type SectionItem = { id: string; title: string; desc?: string; default?: boolean; category?: string }

export const CANDIDATE_SECTIONS: SectionItem[] = [
  { id: 'abstract', title: '摘要', desc: '研究目的、数据来源与主要结论', default: true, category: '核心' },
  { id: 'background', title: '背景与目标', desc: '研究背景、动机与目标', default: true, category: '核心' },
  { id: 'data', title: '数据说明', desc: '数据结构与字段画像', default: true, category: '核心' },
  { id: 'methods', title: '方法', desc: '数据清洗、匹配、统计与可视化方法', default: true, category: '核心' },
  { id: 'results', title: '结果', desc: '按图表逐项描述与解读', default: true, category: '核心' },
  { id: 'discussion', title: '讨论', desc: '解释现象与机制，比较既往研究', default: true, category: '核心' },
  { id: 'limitations', title: '局限性', desc: '数据质量、偏倚与方法约束', default: true, category: '核心' },
  { id: 'outlook', title: '展望', desc: '后续研究方向与方法升级', default: true, category: '核心' },
  { id: 'conclusion', title: '结论', desc: '主要发现与意义', default: true, category: '核心' },
  { id: 'appendix', title: '附录（可复现性）', desc: '代码、图表列表与日志摘要', default: true, category: '核心' },
  { id: 'cohort', title: '研究对象与纳入排除标准', desc: '研究人群定义与筛选', category: '方法扩展' },
  { id: 'ethics', title: '伦理声明', desc: '伦理审查与合规说明', category: '规范' },
  { id: 'sap', title: '统计分析计划（SAP）', desc: '分析步骤与统计设定', category: '方法扩展' },
  { id: 'sensitivity', title: '敏感性分析', desc: '不同设定的稳健性验证', category: '方法扩展' },
  { id: 'subgroups', title: '子群分析', desc: '分层比较与交互作用', category: '方法扩展' },
  { id: 'missing', title: '缺失值处理策略', desc: '缺失机制与处理方法', category: '数据质量' },
  { id: 'bias', title: '偏倚控制', desc: '选择/信息/混杂偏倚控制', category: '方法扩展' },
  { id: 'dq', title: '数据质量评估', desc: '一致性、完整性与可信度', category: '数据质量' },
  { id: 'references', title: '参考文献', desc: '文献引用与DOI/PMID', category: '规范' },
  { id: 'acks', title: '致谢', desc: '贡献与支持单位', category: '规范' },
]

const STORAGE_KEY = 'rws_report_template'

export default function Templates() {
  const [selected, setSelected] = useState<string[]>([])
  const [order, setOrder] = useState<string[]>([])

  useEffect(() => {
    // 载入历史模板或默认模板
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        const obj = JSON.parse(saved)
        setSelected(obj.selected || [])
        setOrder(obj.order || [])
      } catch {}
    } else {
      const defaults = CANDIDATE_SECTIONS.filter(s => s.default).map(s => s.id)
      setSelected(defaults)
      setOrder(defaults)
    }
  }, [])

  const toggle = (id: string, checked: boolean) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (checked) next.add(id); else next.delete(id)
      const arr = Array.from(next)
      // 同步顺序（新增时追加到末尾）
      setOrder(o => checked ? (o.includes(id) ? o : [...o, id]) : o.filter(x => x !== id))
      return arr
    })
  }

  const move = (id: string, dir: 'up' | 'down') => {
    setOrder(prev => {
      const idx = prev.indexOf(id)
      if (idx < 0) return prev
      const arr = [...prev]
      const swapWith = dir === 'up' ? idx - 1 : idx + 1
      if (swapWith < 0 || swapWith >= arr.length) return prev
      const tmp = arr[swapWith]; arr[swapWith] = arr[idx]; arr[idx] = tmp
      return arr
    })
  }

  const saveTemplate = () => {
    const payload = { selected, order }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    message.success('模板已保存')
  }

  const applyTemplate = () => {
    // 此处预留与后端的集成：可在执行前发送选中的章节集合，驱动报告生成策略
    // 目前先保存到本地，供后续流程读取
    saveTemplate()
    message.info('模板已应用。后续生成报告将参考所选章节（需后端集成）。')
  }

  const selectedSet = new Set(selected)
  const orderedSelected = order.filter(id => selectedSet.has(id))

  const grouped = CANDIDATE_SECTIONS.reduce((acc: Record<string, SectionItem[]>, s) => {
    const k = s.category || '其他'
    acc[k] = acc[k] || []
    acc[k].push(s)
    return acc
  }, {})

  return (
    <div>
      <Typography.Title level={3}>模板管理</Typography.Title>
      <Card>
        <Typography.Paragraph>
          请选择需要生成的报告章节。系统将根据所选章节组织大模型逐步填充内容。你可以保存并应用此模板，用于后续报告生成。
        </Typography.Paragraph>
        <Space style={{ marginBottom: 12 }}>
          <Button onClick={() => { setSelected(CANDIDATE_SECTIONS.map(s => s.id)); setOrder(CANDIDATE_SECTIONS.map(s => s.id)) }}>全选</Button>
          <Button onClick={() => { setSelected([]); setOrder([]) }}>清空</Button>
          <Button type="primary" onClick={saveTemplate}>保存模板</Button>
          <Button onClick={applyTemplate}>应用到报告生成（预留）</Button>
        </Space>

        {Object.keys(grouped).map((cat) => (
          <Card key={cat} type="inner" title={<span>{cat} <Tag color="blue">{grouped[cat].length}项</Tag></span>} style={{ marginBottom: 12 }}>
            <List
              dataSource={grouped[cat]}
              renderItem={(item) => {
                const checked = selectedSet.has(item.id)
                const pos = order.indexOf(item.id)
                return (
                  <List.Item>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                      <Checkbox checked={checked} onChange={(e) => toggle(item.id, e.target.checked)}>
                        <Typography.Text strong>{item.title}</Typography.Text>
                        {item.desc && <Typography.Text type="secondary" style={{ marginLeft: 8 }}>{item.desc}</Typography.Text>}
                      </Checkbox>
                      {checked && (
                        <Space>
                          <Button size="small" onClick={() => move(item.id, 'up')} disabled={pos <= 0}>上移</Button>
                          <Button size="small" onClick={() => move(item.id, 'down')} disabled={pos < 0 || pos >= order.length - 1}>下移</Button>
                          <Tag>顺序: {pos + 1}</Tag>
                        </Space>
                      )}
                    </div>
                  </List.Item>
                )
              }}
            />
          </Card>
        ))}

        <Card type="inner" title="已选择的章节顺序预览" style={{ marginTop: 12 }}>
          {orderedSelected.length ? (
            <Space wrap>
              {orderedSelected.map((id, i) => {
                const s = CANDIDATE_SECTIONS.find(x => x.id === id)
                return <Tag key={id} color="green">{i + 1}. {s?.title || id}</Tag>
              })}
            </Space>
          ) : (
            <Typography.Text type="secondary">尚未选择任何章节</Typography.Text>
          )}
        </Card>
      </Card>
    </div>
  )
}