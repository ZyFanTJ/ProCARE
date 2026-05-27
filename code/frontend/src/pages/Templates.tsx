
import React, { useEffect, useState } from 'react'
import { Typography, Checkbox, Button, Space, message, Tag, theme, Tooltip, Empty, Popconfirm } from 'antd'
import { 
  FileTextOutlined, 
  SaveOutlined, 
  DeleteOutlined, 
  ArrowUpOutlined, 
  ArrowDownOutlined, 
  EyeOutlined, 
  CheckCircleOutlined, 
  ReloadOutlined,
  AppstoreOutlined 
} from '@ant-design/icons'
import styles from './Templates.module.css'

const { Title, Text } = Typography

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
  const { token } = theme.useToken()
  const isDark = token.colorBgBase === '#0f172a' || token.colorTextBase === '#f1f5f9'
  
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
    saveTemplate()
    message.info('模板已应用。后续生成报告将参考所选章节。')
  }

  const resetTemplate = () => {
    const defaults = CANDIDATE_SECTIONS.filter(s => s.default).map(s => s.id)
    setSelected(defaults)
    setOrder(defaults)
    message.info('已重置为默认模板')
  }

  const selectedSet = new Set(selected)
  const orderedSelected = order.filter(id => selectedSet.has(id))

  const grouped = CANDIDATE_SECTIONS.reduce((acc: Record<string, SectionItem[]>, s) => {
    const k = s.category || '其他'
    acc[k] = acc[k] || []
    acc[k].push(s)
    return acc
  }, {})

  // Order categories to keep "核心" first
  const sortedCategories = Object.keys(grouped).sort((a, b) => {
    if (a === '核心') return -1;
    if (b === '核心') return 1;
    return a.localeCompare(b);
  });

  return (
    <div className={styles.container}>
      {/* Left Panel: Selection */}
      <div className={styles.selectionPanel}>
        <div className={styles.panelHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AppstoreOutlined style={{ fontSize: 20, color: 'var(--tpl-accent)' }} />
            <h2 className={styles.title}>模板章节选择</h2>
          </div>
          <Tooltip title="重置默认">
             <Button type="text" icon={<ReloadOutlined style={{ color: 'var(--tpl-text-secondary)' }} />} onClick={resetTemplate} />
          </Tooltip>
        </div>

        <div className={styles.scrollArea}>
          {sortedCategories.map(cat => (
            <div key={cat} className={styles.categoryGroup}>
              <div className={styles.categoryTitle}>{cat}</div>
              {grouped[cat].map(item => {
                 const checked = selectedSet.has(item.id)
                 return (
                   <div 
                     key={item.id} 
                     className={`${styles.sectionItem} ${checked ? styles.active : ''}`}
                     onClick={() => toggle(item.id, !checked)}
                   >
                     <Checkbox checked={checked} style={{ pointerEvents: 'none' }} />
                     <div className={styles.sectionInfo}>
                       <div className={styles.sectionTitle}>{item.title}</div>
                       {item.desc && <div className={styles.sectionDesc}>{item.desc}</div>}
                     </div>
                   </div>
                 )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Right Panel: Preview */}
      <div className={styles.previewPanel}>
        <div className={styles.toolbar}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <EyeOutlined style={{ fontSize: 20, color: 'var(--tpl-accent)' }} />
            <h2 className={styles.title} style={{ fontSize: 16 }}>文档预览</h2>
            <Tag color={isDark ? "cyan" : "blue"} style={{ marginLeft: 10 }}>{orderedSelected.length} 个章节</Tag>
          </div>
          <Space>
             <Button icon={<SaveOutlined />} onClick={saveTemplate}>保存草稿</Button>
             <Button type="primary" icon={<CheckCircleOutlined />} onClick={applyTemplate}>应用模板</Button>
          </Space>
        </div>

        <div className={styles.paperPreview}>
          <div className={styles.paper}>
            <div className={styles.paperHeader}>
              <div className={styles.paperTitle}>研究报告模板</div>
              <div className={styles.paperMeta}>生成结构预览 • {new Date().toLocaleDateString()}</div>
            </div>

            {orderedSelected.length === 0 ? (
               <Empty description="未选择任何章节" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
               orderedSelected.map((id, index) => {
                 const item = CANDIDATE_SECTIONS.find(s => s.id === id)
                 if (!item) return null
                 return (
                   <div key={id} className={styles.previewItem}>
                     <div className={styles.previewIndex}>{String(index + 1).padStart(2, '0')}</div>
                     <div className={styles.previewContent}>
                       <div className={styles.previewTitle}>{item.title}</div>
                       <div className={styles.previewDesc}>{item.desc}</div>
                     </div>
                     <div className={styles.previewActions}>
                        <Button 
                          size="small" 
                          icon={<ArrowUpOutlined />} 
                          disabled={index === 0}
                          onClick={() => move(id, 'up')}
                        />
                        <Button 
                          size="small" 
                          icon={<ArrowDownOutlined />} 
                          disabled={index === orderedSelected.length - 1}
                          onClick={() => move(id, 'down')}
                        />
                        <Popconfirm title="确认移除该章节？" onConfirm={() => toggle(id, false)}>
                           <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                     </div>
                   </div>
                 )
               })
            )}
            
            <div style={{ textAlign: 'center', marginTop: 40, color: 'var(--tpl-text-secondary)', fontSize: 12 }}>
               --- 文档结构结束 ---
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
