import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button, Card, Col, Form, Input, InputNumber, Progress, Radio, Row, Space, Tag, Typography, Upload, message } from 'antd'
import type { UploadFile, UploadProps } from 'antd'
import { FilePdfOutlined, FileTextOutlined, FolderOpenOutlined, ReloadOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons'
import { fetchPaperStatus, generatePaper, type PaperStatus } from '../api/research'
import { fetchSettingsFromBackend, loadSettings } from '../utils/systemSettings'
import { resolveStaticUrl } from '../api/client'

const { Title, Text } = Typography

type PaperForm = {
  report_name?: string
  report_language: 'zh' | 'en'
  template_path?: string
  writing_requirements?: string
  llm_timeout_seconds?: number
}

export default function PaperGenerator() {
  const { jobId } = useParams()
  const [form] = Form.useForm<PaperForm>()
  const [status, setStatus] = useState<PaperStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [settings, setSettings] = useState<any>(() => loadSettings() as any)
  const activeModel = settings?.active_model || settings?.llm?.active_model || '未配置'

  const refreshStatus = async () => {
    if (!jobId) return
    try {
      const next = await fetchPaperStatus(jobId)
      setStatus(next)
    } catch {
      setStatus(null)
    }
  }

  useEffect(() => {
    refreshStatus()
    fetchSettingsFromBackend().then((remote) => {
      if (remote) setSettings(remote as any)
    })
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    if (status?.status !== 'pending' && status?.status !== 'running') return
    const timer = window.setInterval(refreshStatus, 1500)
    return () => window.clearInterval(timer)
  }, [jobId, status?.status])

  const uploadProps: UploadProps = {
    multiple: true,
    fileList,
    accept: '.pdf,.bib,.ris,.txt,.doc,.docx',
    openFileDialogOnClick: true,
    beforeUpload: () => false,
    onChange: ({ fileList: next }) => setFileList(next),
  }

  const startGeneration = async () => {
    if (!jobId) return
    let values: PaperForm
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    setLoading(true)
    try {
      const files = fileList
        .map((file) => file.originFileObj)
        .filter(Boolean) as unknown as File[]
      const next = await generatePaper(jobId, {
        llm_enabled: true,
        report_language: values.report_language || 'zh',
        report_name: values.report_name,
        template_path: values.template_path,
        writing_requirements: values.writing_requirements,
        llm_timeout_seconds: values.llm_timeout_seconds,
        reference_files: files,
      })
      setStatus(next)
      message.success('论文生成任务已启动')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      message.error(detail || (e?.response ? '论文生成启动失败' : '后端服务未连接，请确认 8000 端口已启动'))
    } finally {
      setLoading(false)
    }
  }

  const busy = loading || status?.status === 'pending' || status?.status === 'running'
  const completed = status?.status === 'completed'
  const failed = status?.status === 'failed'

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} align="center">
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>论文生成</Title>
          <Space wrap>
            <Tag color="blue">Job: {jobId}</Tag>
            <Tag color="geekblue">模型: {status?.llm_model || activeModel}</Tag>
            {status?.compile_engine && <Tag color="green">{status.compile_engine}</Tag>}
          </Space>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={refreshStatus}>刷新</Button>
          <Link to={`/project/${jobId}`}><Button>返回项目</Button></Link>
        </Space>
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card bordered={false}>
            <Form
              form={form}
              layout="vertical"
              initialValues={{ report_language: 'zh', llm_timeout_seconds: 600 }}
            >
              <Row gutter={16}>
                <Col xs={24} md={14}>
                  <Form.Item label="论文标题" name="report_name">
                    <Input placeholder="留空则由大模型自动生成" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={10}>
                  <Form.Item label="语言" name="report_language" rules={[{ required: true }]}>
                    <Radio.Group buttonStyle="solid">
                      <Radio.Button value="zh">中文</Radio.Button>
                      <Radio.Button value="en">English</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item label="LaTeX 模板路径" name="template_path">
                <Input placeholder="留空使用系统默认模板" />
              </Form.Item>

              <Form.Item label="参考文献文件">
                <Upload {...uploadProps}>
                  <Button icon={<UploadOutlined />}>选择 PDF / BibTeX 文件</Button>
                </Upload>
              </Form.Item>

              <Form.Item label="写作要求" name="writing_requirements">
                <Input.TextArea rows={4} placeholder="例如标题风格、摘要长度、结果呈现重点、讨论侧重点" />
              </Form.Item>

              <Form.Item label="模型超时秒数" name="llm_timeout_seconds">
                <InputNumber min={60} max={1800} step={60} style={{ width: 180 }} />
              </Form.Item>

              <Space wrap>
                <Button type="primary" icon={<SaveOutlined />} loading={busy} onClick={startGeneration}>
                  开始生成
                </Button>
                <Link to={`/report/${jobId}`}><Button>查看报告</Button></Link>
              </Space>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card bordered={false} title="生成状态">
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color={completed ? 'green' : failed ? 'red' : busy ? 'orange' : 'default'}>
                  {status?.status || 'not_started'}
                </Tag>
                {status?.updated_at && <Text type="secondary">{status.updated_at}</Text>}
              </Space>
              <Progress percent={completed ? 100 : busy ? 60 : failed ? 100 : 0} status={failed ? 'exception' : busy ? 'active' : completed ? 'success' : 'normal'} />
              {failed && <Text type="danger">{status?.error || '论文生成失败'}</Text>}

              <Space wrap>
                {completed && status?.pdf_url && (
                  <Button type="primary" icon={<FilePdfOutlined />} href={resolveStaticUrl(status.pdf_url)} target="_blank">
                    论文 PDF
                  </Button>
                )}
                {completed && status?.tex_url && (
                  <Button icon={<FileTextOutlined />} href={resolveStaticUrl(status.tex_url)} target="_blank">
                    TeX
                  </Button>
                )}
                {completed && status?.latex_zip_url && (
                  <Button icon={<FolderOpenOutlined />} href={resolveStaticUrl(status.latex_zip_url)} target="_blank">
                    LaTeX 项目
                  </Button>
                )}
              </Space>

              {completed && (
                <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: 12 }}>
                  <Text type="secondary">项目目录</Text>
                  <div style={{ marginTop: 4, fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
                    {status?.latex_project_dir || '-'}
                  </div>
                </div>
              )}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
