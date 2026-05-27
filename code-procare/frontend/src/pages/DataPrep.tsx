import { useState, useEffect } from 'react'
import { Typography, Card, Upload, Table, Button, Space, message, Select, Modal, Form, Input, InputNumber, Tooltip, List, Tabs, Tag, Spin, Row, Col, Popconfirm } from 'antd'
import { InboxOutlined, ClearOutlined, SaveOutlined, ReloadOutlined, DeleteOutlined, EditOutlined, FileExcelOutlined, ArrowRightOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { listFiles, previewData, applyOps, DataFile, PreviewData, Operation } from '../api/dataprep'
import { uploadExcel } from '../api/research' // Reuse upload

const { Title, Text, Paragraph } = Typography
const { Dragger } = Upload
const { Option } = Select

export default function DataPrep() {
  const [files, setFiles] = useState<DataFile[]>([])
  const [currentFile, setCurrentFile] = useState<DataFile | null>(null)
  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)

  // Operation State
  const [opType, setOpType] = useState<string>('fillna')
  const [opParams, setOpParams] = useState<any>({})
  
  const refreshFiles = async () => {
    try {
      const res = await listFiles()
      setFiles(res.files)
      // If current file exists, refresh it? Or just keep it.
    } catch (e) {
      message.error('加载文件列表失败')
    }
  }

  useEffect(() => {
    refreshFiles()
  }, [])

  const loadFile = async (file: DataFile) => {
    setLoading(true)
    setCurrentFile(file)
    try {
      const res = await previewData(file.path)
      setPreview(res)
      // Reset params when file changes
      setOpParams({})
    } catch (e) {
      message.error('加载预览失败')
    } finally {
      setLoading(false)
    }
  }

  const handleUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    try {
      // Reuse the research upload API which saves to the same uploads dir
      await uploadExcel(file as File)
      message.success('上传成功')
      refreshFiles()
      onSuccess && onSuccess("ok")
    } catch (e) {
      message.error('上传失败')
      onError && onError(e as any)
    }
  }

  const handleApply = async () => {
    if (!currentFile) return
    
    // Validate params
    if (opType === 'fillna' && opParams.value === undefined) {
       message.warning('请输入填充值')
       return
    }
    if (opType === 'rename' && (!opParams.old || !opParams.new)) {
       message.warning('请输入新旧列名')
       return
    }
    
    setProcessing(true)
    try {
        let actualParams = { ...opParams }
        if (opType === 'rename') {
            actualParams = { columns: { [opParams.old]: opParams.new } }
        }
        
        const op: Operation = {
            type: opType as any,
            params: actualParams
        }
        
        const res = await applyOps(currentFile.path, [op])
        message.success('操作已应用，生成新文件')
        
        // Refresh list and switch to new file
        await refreshFiles()
        // Find the new file (by path or name)
        // Since we don't know the exact object ref, we find by path
        const newFile = (await listFiles()).files.find(f => f.path === res.path)
        if (newFile) {
            loadFile(newFile)
        }
        
    } catch (e: any) {
        message.error(e.response?.data?.detail || '操作失败')
    } finally {
        setProcessing(false)
    }
  }

  const renderOpForm = () => {
    if (!preview) return <EmptyState text="请先选择文件" />
    const colOptions = preview.info.columns.map(c => <Option key={c.name} value={c.name}>{c.name}</Option>)

    return (
        <Form layout="vertical">
            <Form.Item label="选择操作">
                <Select value={opType} onChange={v => { setOpType(v); setOpParams({}) }}>
                    <Option value="fillna">填充缺失值 (Fill NA)</Option>
                    <Option value="dropna">删除缺失行 (Drop NA)</Option>
                    <Option value="rename">重命名列 (Rename)</Option>
                    <Option value="astype">类型转换 (Convert Type)</Option>
                    <Option value="drop_col">删除列 (Drop Column)</Option>
                </Select>
            </Form.Item>

            {opType === 'fillna' && (
                <>
                    <Form.Item label="目标列 (可选，留空则填充所有)">
                        <Select allowClear placeholder="所有列" onChange={v => setOpParams({ ...opParams, column: v })} value={opParams.column}>
                            {colOptions}
                        </Select>
                    </Form.Item>
                    <Form.Item label="填充值">
                        <Input placeholder="例如: 0, Unknown" onChange={e => setOpParams({ ...opParams, value: e.target.value })} value={opParams.value} />
                    </Form.Item>
                </>
            )}

            {opType === 'dropna' && (
                <Form.Item label="依据列 (可选，留空则检查所有)">
                     <Select mode="multiple" allowClear placeholder="所有列" onChange={v => setOpParams({ ...opParams, subset: v })} value={opParams.subset}>
                        {colOptions}
                    </Select>
                </Form.Item>
            )}

            {opType === 'rename' && (
                <>
                    <Form.Item label="原列名">
                        <Select onChange={v => setOpParams({ ...opParams, old: v })} value={opParams.old}>
                            {colOptions}
                        </Select>
                    </Form.Item>
                    <Form.Item label="新列名">
                        <Input onChange={e => setOpParams({ ...opParams, new: e.target.value })} value={opParams.new} />
                    </Form.Item>
                </>
            )}

            {opType === 'astype' && (
                <>
                    <Form.Item label="目标列">
                         <Select onChange={v => setOpParams({ ...opParams, column: v })} value={opParams.column}>
                            {colOptions}
                        </Select>
                    </Form.Item>
                    <Form.Item label="目标类型">
                        <Select onChange={v => setOpParams({ ...opParams, dtype: v })} value={opParams.dtype}>
                            <Option value="str">文本 (String)</Option>
                            <Option value="int">整数 (Integer)</Option>
                            <Option value="float">浮点数 (Float)</Option>
                            <Option value="bool">布尔值 (Boolean)</Option>
                        </Select>
                    </Form.Item>
                </>
            )}

            {opType === 'drop_col' && (
                 <Form.Item label="选择列">
                     <Select mode="multiple" onChange={v => setOpParams({ ...opParams, columns: v })} value={opParams.columns}>
                        {colOptions}
                    </Select>
                </Form.Item>
            )}

            <Button type="primary" block icon={<ThunderboltOutlined />} onClick={handleApply} loading={processing}>
                立即应用并另存
            </Button>
        </Form>
    )
  }

  const columnsInfoCols = [
      { title: '列名', dataIndex: 'name', key: 'name', render: (t: string) => <b>{t}</b> },
      { title: '类型', dataIndex: 'type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
      { title: '缺失值', dataIndex: 'nulls', key: 'nulls', render: (n: number) => n > 0 ? <Text type="danger">{n}</Text> : <Text type="success">0</Text> },
      { title: '唯一值', dataIndex: 'unique', key: 'unique' },
  ]

  // Dynamic preview columns
  const previewCols = preview ? preview.info.columns.map(c => ({
      title: c.name,
      dataIndex: c.name,
      key: c.name,
      width: 150,
      render: (text: any) => text === null || text === undefined ? <Text type="secondary" italic>null</Text> : String(text)
  })) : []

  return (
    <div style={{ height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-color)' }}>
            <Title level={4} style={{ margin: 0 }}>🧹 数据清洗工坊</Title>
        </div>
        
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
            {/* Left: File List */}
            <div style={{ width: 280, borderRight: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', background: 'var(--bg-subtle)' }}>
                <div style={{ padding: 16 }}>
                    <Dragger 
                        showUploadList={false} 
                        customRequest={handleUpload}
                        style={{ padding: 16, background: 'var(--bg-color)' }}
                    >
                        <p className="ant-upload-drag-icon" style={{ marginBottom: 8 }}><InboxOutlined style={{ fontSize: 24 }} /></p>
                        <p className="ant-upload-text" style={{ fontSize: 12 }}>上传文件</p>
                    </Dragger>
                </div>
                <div style={{ flex: 1, overflow: 'auto', padding: '0 16px 16px' }}>
                    <List
                        size="small"
                        dataSource={files}
                        renderItem={item => (
                            <List.Item 
                                onClick={() => loadFile(item)}
                                className={currentFile?.path === item.path ? 'file-item-active' : 'file-item'}
                                style={{ 
                                    cursor: 'pointer', 
                                    borderRadius: 6, 
                                    padding: '8px 12px',
                                    marginBottom: 4,
                                    background: currentFile?.path === item.path ? 'var(--primary-color-bg)' : 'transparent',
                                    border: currentFile?.path === item.path ? '1px solid var(--primary-color)' : '1px solid transparent'
                                }}
                            >
                                <div style={{ width: '100%' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <FileExcelOutlined style={{ color: '#1d7324' }} />
                                        <Text ellipsis style={{ flex: 1, fontWeight: 500 }}>{item.name}</Text>
                                    </div>
                                    <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
                                        <span>{(item.size / 1024).toFixed(1)} KB</span>
                                        <span>{new Date(item.mtime * 1000).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </List.Item>
                        )}
                    />
                </div>
            </div>

            {/* Middle: Preview */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16 }}>
                {loading ? <div style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }}><Spin size="large" /></div> : 
                 preview ? (
                     <Tabs defaultActiveKey="sample" items={[
                         {
                             key: 'sample',
                             label: '数据预览 (前20行)',
                             children: (
                                 <Table 
                                     dataSource={preview.preview} 
                                     columns={previewCols} 
                                     scroll={{ x: 'max-content', y: 'calc(100vh - 250px)' }}
                                     pagination={false}
                                     size="small"
                                     bordered
                                     rowKey={(r, i) => i as number}
                                 />
                             )
                         },
                         {
                             key: 'info',
                             label: '字段信息',
                             children: (
                                 <Table 
                                     dataSource={preview.info.columns} 
                                     columns={columnsInfoCols} 
                                     pagination={false}
                                     rowKey="name"
                                 />
                             )
                         }
                     ]} />
                 ) : (
                     <EmptyState text="请从左侧选择一个文件查看" />
                 )
                }
            </div>

            {/* Right: Operations */}
            <div style={{ width: 320, borderLeft: '1px solid var(--border-color)', padding: 16, background: 'var(--bg-subtle)', overflow: 'auto' }}>
                <Title level={5}>🛠️ 操作面板</Title>
                <Card size="small" style={{ marginTop: 16 }}>
                    {renderOpForm()}
                </Card>
                
                {preview && (
                    <div style={{ marginTop: 24 }}>
                        <Title level={5} style={{ fontSize: 14 }}>📊 统计概览</Title>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
                            <StatCard label="总行数" value={preview.info.rows} />
                            <StatCard label="总列数" value={preview.info.cols} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
            <InboxOutlined style={{ fontSize: 48, marginBottom: 16, opacity: 0.5 }} />
            <span>{text}</span>
        </div>
    )
}

function StatCard({ label, value }: { label: string; value: number | string }) {
    return (
        <div style={{ background: 'var(--bg-color)', padding: 12, borderRadius: 6, border: '1px solid var(--border-color)', textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</div>
            <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{value}</div>
        </div>
    )
}
