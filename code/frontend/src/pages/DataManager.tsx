import { useState, useEffect } from 'react'
import { Card, Table, Typography, Space, Button, Modal, Descriptions, Tag, Tabs, List, Empty, Drawer, Popconfirm, message, Badge, Tooltip, Upload, Form, Input } from 'antd'
import { DeleteOutlined, EyeOutlined, FileExcelOutlined, ReloadOutlined, DatabaseOutlined, ProjectOutlined, UploadOutlined, InboxOutlined } from '@ant-design/icons'
import { fetchProfiles, fetchProfileDetail, deleteProfile, uploadExcel, analyzeProfile, previewSheetData, listUploads } from '../api/research'
import type { UploadProps } from 'antd'
import JsonTree from '../components/JsonTree'

const { Title, Text, Paragraph } = Typography

function SheetPreview({ md5, sheet }: { md5: string, sheet: string }) {
    const [data, setData] = useState<{ columns: string[], data: any[] } | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        loadData()
    }, [md5, sheet])

    const loadData = async () => {
        setLoading(true)
        setError(null)
        try {
            const res = await previewSheetData(md5, sheet)
            setData(res)
        } catch (e: any) {
            setError(e?.response?.data?.detail || '加载预览数据失败')
        } finally {
            setLoading(false)
        }
    }

    if (loading) return <div style={{ padding: 20, textAlign: 'center' }}>加载预览数据中...</div>
    if (error) return <div style={{ color: 'red', padding: 20 }}>{error}</div>
    if (!data) return <Empty description="暂无预览数据" />

    const columns = data.columns.map(c => ({
        title: c,
        dataIndex: c,
        key: c,
        render: (text: any) => <Text ellipsis={{ tooltip: true }} style={{ maxWidth: 200 }}>{text !== null ? String(text) : <Text type="secondary" italic>null</Text>}</Text>
    }))

    return (
        <Table 
            size="small"
            dataSource={data.data} 
            columns={columns} 
            scroll={{ x: 'max-content' }} 
            pagination={false}
            rowKey={(r, i) => i as any}
        />
    )
}

export default function DataManager() {
  const [profiles, setProfiles] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [currentProfile, setCurrentProfile] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  
  // Upload modal states
  const [uploadVisible, setUploadVisible] = useState(false)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [form] = Form.useForm()

  // Files tab states
  const [files, setFiles] = useState<Array<any>>([])
  const [filesLoading, setFilesLoading] = useState(false)

  const loadProfiles = async () => {
    setLoading(true)
    try {
      const data = await fetchProfiles()
      setProfiles(data)
    } catch (e) {
      message.error('加载画像列表失败')
    } finally {
      setLoading(false)
    }
  }

  const loadFiles = async () => {
    setFilesLoading(true)
    try {
      const res = await listUploads()
      setFiles(res.files || [])
    } catch (e) {
      message.error('加载文件列表失败')
    } finally {
      setFilesLoading(false)
    }
  }

  useEffect(() => {
    loadProfiles()
    loadFiles()
  }, [])

  const prefixUrl = (u: string) => {
    const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    const prefix = baseApi.replace(/\/api$/, '')
    return `${prefix}${u}`
  }

  const handleUploadSubmit = async () => {
    try {
      const values = await form.validateFields()
      const file = values.file?.[0]?.originFileObj
      if (!file) {
        message.error('请选择文件')
        return
      }

      setUploadLoading(true)
      try {
        const res = await uploadExcel(file, values.description)
        if (res.profile_reused) {
           message.success(`检测到已有画像 (MD5: ${res.md5?.slice(0, 8)})，已复用`)
        } else {
           message.success('上传并生成画像成功')
        }
        setUploadVisible(false)
        form.resetFields()
        loadProfiles()
        loadFiles()
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '上传失败')
      } finally {
        setUploadLoading(false)
      }
    } catch (e) {
      // validation failed
    }
  }

  const normFile = (e: any) => {
    if (Array.isArray(e)) {
      return e
    }
    return e?.fileList
  }

  const handleView = async (md5: string) => {
    setDetailLoading(true)
    setDetailVisible(true)
    try {
      const data = await fetchProfileDetail(md5)
      setCurrentProfile(data)
    } catch (e) {
      message.error('加载详情失败')
      setDetailVisible(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDelete = async (md5: string) => {
    try {
      await deleteProfile(md5)
      message.success('删除成功')
      loadProfiles()
    } catch (e) {
      message.error('删除失败')
    }
  }

  const handleAnalyze = async () => {
    if (!currentProfile?.md5) return
    setAnalyzing(true)
    // Keep loading message with duration 0 so it stays until updated or destroyed
    message.loading({ content: 'AI 正在深度分析数据语义...', key: 'analyzing', duration: 0 })
    
    try {
      await analyzeProfile(currentProfile.md5, (msg) => {
          if (msg.status === 'processing') {
             // Update the loading message content
             message.loading({ content: msg.message || 'AI 分析中...', key: 'analyzing', duration: 0 })
          } else if (msg.status === 'completed') {
             // Success message replaces the loading one
             message.success({ content: 'AI 画像分析完成', key: 'analyzing' })
             if (msg.profile) {
                 setCurrentProfile(msg.profile)
             }
             loadProfiles()
          } else if (msg.status === 'error') {
             message.error({ content: msg.message || '分析失败', key: 'analyzing' })
          }
      })
    } catch (e: any) {
      console.error(e)
      message.error({ content: e.message || '分析失败', key: 'analyzing' })
    } finally {
      setAnalyzing(false)
    }
  }

  const filesColumns = [
    { title: '文件名', dataIndex: 'name', key: 'name' },
    { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
    { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-' },
    { title: '操作', key: 'action', render: (_: any, r: any) => r.url ? <a href={prefixUrl(r.url)} target="_blank">下载/预览</a> : '-' },
  ]

  const columns = [
    {
      title: '文件名',
      dataIndex: 'path',
      key: 'path',
      render: (path: string) => {
        const name = path.split(/[/\\]/).pop()
        return (
          <Space>
            <FileExcelOutlined style={{ color: '#1890ff' }} />
            <Text strong>{name}</Text>
          </Space>
        )
      }
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string) => text || <Text type="secondary">无描述</Text>
    },
    {
      title: '表单数量',
      dataIndex: 'sheet_count',
      key: 'sheet_count',
      render: (count: number) => <Tag color="blue">{count} 个表</Tag>
    },
    {
      title: '画像覆盖',
      dataIndex: 'profile_count',
      key: 'profile_count',
      render: (count: number, record: any) => {
          const percent = record.sheet_count > 0 ? Math.round(count / record.sheet_count * 100) : 0
          return <Badge count={`${percent}%`} style={{ backgroundColor: percent === 100 ? '#52c41a' : '#faad14' }} />
      }
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (t: string) => new Date(t).toLocaleString()
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <Space size="middle">
          <Button type="link" icon={<EyeOutlined />} onClick={() => handleView(record.md5)}>查看详情</Button>
          <Popconfirm title="确定删除此缓存画像吗？" onConfirm={() => handleDelete(record.md5)}>
             <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  // 渲染Sheet详情
  const renderSheetProfile = (sheetName: string, profile: any) => {
    if (!profile) return <Empty description="暂无该Sheet的详细画像" />

    const { high_structural, low_structural, high_knowledge, low_knowledge, ambiguity_flags } = profile.heterogeneous_profile || {}
    const legacy = !profile.heterogeneous_profile

    if (legacy) {
       // Fallback for legacy profile structure
       return <JsonTree data={profile} defaultCollapsed={false} />
    }

    const aiReady = !!(high_knowledge && Object.keys(high_knowledge).length > 0)

    const dtypes = low_structural?.dtypes || {}
    const missing = low_structural?.missing_rate || {}
    const unique = low_structural?.unique_rate || {}
    
    const fieldColumns = [
        { title: '字段名', dataIndex: 'name', key: 'name', width: 150, fixed: 'left' as const },
        { title: '类型', dataIndex: 'type', key: 'type', render: (t: string) => <Tag color={t==='object'?'orange':t==='int64'?'blue':'cyan'}>{t}</Tag> },
        { title: '缺失率', dataIndex: 'missing', key: 'missing', render: (v: number) => <Text type={v>0.5?'danger':v>0?'warning':'secondary'}>{(v*100).toFixed(1)}%</Text> },
        { title: '唯一率', dataIndex: 'unique', key: 'unique', render: (v: number) => `${(v*100).toFixed(1)}%` },
        { title: '语义映射 (LLM)', dataIndex: 'mapping', key: 'mapping', render: (v: string) => v ? <Tag color="purple">{v}</Tag> : <Text type="secondary">-</Text> },
        { title: '校验', dataIndex: 'validation', key: 'validation', render: (v: string) => !aiReady ? <Text type="secondary">-</Text> : (v && v.includes('Ambiguous') ? <Badge status="warning" text={v} /> : <Text type="success">OK</Text>) }
    ]

    const fieldData = Object.keys(dtypes).map(k => ({
        key: k,
        name: k,
        type: dtypes[k],
        missing: missing[k],
        unique: unique[k],
        mapping: low_knowledge?.ontology_mapping?.[k],
        validation: low_knowledge?.validation_status?.[k]
    }))

    return (
        <div style={{ height: 'calc(100vh - 200px)', overflow: 'auto' }}>
            {/* 顶部：高层知识卡片 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                <Card size="small" title={<Space><ProjectOutlined /><span>研究设计角色</span></Space>} style={{ background: '#f9f9f9' }}>
                    {!aiReady ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="待 AI 分析 (请点击右上角执行)" /> : (
                        <>
                            <Paragraph>{high_knowledge?.study_design_schema || '未识别'}</Paragraph>
                            <Space direction="vertical" style={{ width: '100%' }}>
                                <div><Text strong>暴露因素 (Exposure):</Text> {high_knowledge?.variable_roles?.exposure?.join(', ') || '-'}</div>
                                <div><Text strong>结局变量 (Outcome):</Text> {high_knowledge?.variable_roles?.outcome?.join(', ') || '-'}</div>
                                <div><Text strong>协变量 (Covariate):</Text> {high_knowledge?.variable_roles?.covariate?.join(', ') || '-'}</div>
                            </Space>
                        </>
                    )}
                </Card>
                <Card size="small" title={<Space><DatabaseOutlined /><span>数据质量概览</span></Space>} style={{ background: '#f9f9f9' }}>
                    <Descriptions column={1} size="small">
                        <Descriptions.Item label="行数">{high_structural?.rows}</Descriptions.Item>
                        <Descriptions.Item label="列数">{high_structural?.columns}</Descriptions.Item>
                        <Descriptions.Item label="候选主键">{high_structural?.candidate_keys?.join(', ') || '无'}</Descriptions.Item>
                        <Descriptions.Item label="疑似问题字段">
                            {ambiguity_flags?.length ? <Text type="danger">{ambiguity_flags.join(', ')}</Text> : <Text type="success">无明显异常</Text>}
                        </Descriptions.Item>
                    </Descriptions>
                </Card>
            </div>

            {/* 中部：字段详情表格 */}
            <Table 
                dataSource={fieldData} 
                columns={fieldColumns} 
                pagination={false} 
                size="small" 
                scroll={{ y: 400 }}
                bordered
            />
        </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
            <Title level={3}>数据资产管理</Title>
            <Paragraph type="secondary">管理所有已分析的 Excel 数据画像，包括结构统计与 AI 生成的语义知识。</Paragraph>
        </div>
        <Space>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadVisible(true)}>上传新数据</Button>
          <Button icon={<ReloadOutlined />} onClick={loadProfiles}>刷新列表</Button>
        </Space>
      </div>

      <Card>
        <Tabs 
          defaultActiveKey="profiles"
          items={[
            {
              key: 'profiles',
              label: '数据画像 (Profiles)',
              children: (
                <Table 
                  loading={loading}
                  dataSource={profiles}
                  columns={columns}
                  rowKey="md5"
                  pagination={{ pageSize: 10 }}
                />
              )
            },
            {
              key: 'files',
              label: '原始文件',
              children: (
                <Table 
                  rowKey="name" 
                  columns={filesColumns} 
                  dataSource={files} 
                  loading={filesLoading} 
                  pagination={{ pageSize: 10 }} 
                />
              )
            }
          ]}
        />
      </Card>

      <Drawer
        title="数据画像详情"
        width="80%"
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        destroyOnClose
        extra={
            <Button 
              type="primary" 
              icon={<DatabaseOutlined />} 
              loading={analyzing}
              onClick={handleAnalyze}
            >
              执行 AI 深度画像
            </Button>
        }
      >
        {detailLoading ? <div style={{ textAlign: 'center', padding: 50 }}>加载中...</div> : (
            currentProfile && (
                <div>
                    <Descriptions title="基础信息" bordered size="small" column={2}>
                        <Descriptions.Item label="文件名">{currentProfile.path?.split(/[/\\]/).pop()}</Descriptions.Item>
                        <Descriptions.Item label="MD5">{currentProfile.md5}</Descriptions.Item>
                        <Descriptions.Item label="完整路径" span={2}>{currentProfile.path}</Descriptions.Item>
                        <Descriptions.Item label="描述" span={2}>{currentProfile.description || '-'}</Descriptions.Item>
                    </Descriptions>
                    
                    <div style={{ marginTop: 24, height: 'calc(100vh - 250px)', display: 'flex', flexDirection: 'column' }}>
                        <Title level={5} style={{ marginBottom: 16 }}>工作表画像</Title>
                        <Tabs
                            tabPosition="left"
                            style={{ height: '100%' }}
                            items={(currentProfile.sheets || []).map((sheet: string) => ({
                                key: sheet,
                                label: (
                                    <span>
                                        {sheet}
                                        {currentProfile.profile?.[sheet] && <Badge status="success" style={{ marginLeft: 8 }} />}
                                    </span>
                                ),
                                children: (
                                    <div style={{ height: '100%', overflowY: 'auto', paddingRight: 16 }}>
                                        <Tabs
                                            type="card"
                                            items={[
                                                {
                                                    key: 'profile',
                                                    label: '画像信息',
                                                    children: renderSheetProfile(sheet, currentProfile.profile?.[sheet])
                                                },
                                                {
                                                    key: 'preview',
                                                    label: '数据预览',
                                                    children: <SheetPreview md5={currentProfile.md5} sheet={sheet} />
                                                }
                                            ]}
                                        />
                                    </div>
                                )
                            }))}
                        />
                    </div>
                </div>
            )
        )}
      </Drawer>

      <Modal
        title="上传新数据"
        open={uploadVisible}
        onCancel={() => setUploadVisible(false)}
        onOk={form.submit}
        confirmLoading={uploadLoading}
        okText="上传并分析"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={handleUploadSubmit}>
          <Form.Item label="文件描述" name="description">
            <Input.TextArea rows={3} placeholder="简要描述数据来源、用途等信息" />
          </Form.Item>
          <Form.Item label="Excel 文件" name="file" valuePropName="fileList" getValueFromEvent={normFile} rules={[{ required: true, message: '请选择文件' }]}>
            <Upload.Dragger accept=".xlsx,.xls" maxCount={1} beforeUpload={() => false}>
               <p className="ant-upload-drag-icon"><InboxOutlined /></p>
               <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
            </Upload.Dragger>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
