import { useEffect, useState } from 'react'
import { Card, Form, Input, Upload, Button, Space, Typography, message, Image } from 'antd'
import type { UploadProps } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { DEFAULT_SETTINGS, loadSettings, saveSettings, SystemSettings } from '../utils/systemSettings'

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function Settings() {
  const [form] = Form.useForm<SystemSettings>()
  const [logoPreview, setLogoPreview] = useState<string | undefined>()
  const [faviconPreview, setFaviconPreview] = useState<string | undefined>()
  const [carouselJson, setCarouselJson] = useState<string>('')

  useEffect(() => {
    const s = loadSettings()
    form.setFieldsValue(s)
    setLogoPreview(s.logoDataUrl)
    setFaviconPreview(s.faviconDataUrl)
    try { setCarouselJson(JSON.stringify(s.carouselSlides || DEFAULT_SETTINGS.carouselSlides, null, 2)) } catch {}
  }, [])

  const onSave = async () => {
    const vals = await form.validateFields()
    let slides = DEFAULT_SETTINGS.carouselSlides
    try { slides = JSON.parse(carouselJson) } catch { message.error('轮播配置不是合法JSON'); return }
    const merged: SystemSettings = { ...DEFAULT_SETTINGS, ...vals, logoDataUrl: logoPreview, faviconDataUrl: faviconPreview, carouselSlides: slides }
    saveSettings(merged)
    message.success('系统设置已保存')
  }

  const uploadLogoProps: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    beforeUpload: async (file) => {
      const url = await fileToDataUrl(file)
      setLogoPreview(url)
      message.success('Logo已选择')
      return false
    },
    onRemove: () => setLogoPreview(undefined),
  }

  const uploadFaviconProps: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    beforeUpload: async (file) => {
      const url = await fileToDataUrl(file)
      setFaviconPreview(url)
      message.success('页面图标已选择')
      return false
    },
    onRemove: () => setFaviconPreview(undefined),
  }

  return (
    <div>
      <Typography.Title level={3}>系统设置</Typography.Title>
      <Card>
        <Form form={form} layout="vertical" initialValues={DEFAULT_SETTINGS}>
          <Form.Item label="系统名称" name="systemName" rules={[{ required: true, message: '请输入系统名称' }]}>
            <Input placeholder="例如：RWS研究系统" />
          </Form.Item>
          <Form.Item label="页底声明信息" name="footerText">
            <Input placeholder="例如：© 2025 公司或团队名称" />
          </Form.Item>

          <Card type="inner" title="系统Logo" style={{ marginBottom: 12 }}>
            <Space>
              <Upload.Dragger {...uploadLogoProps} style={{ width: 320 }}>
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">拖拽或点击上传Logo图片</p>
                <p className="ant-upload-hint">建议尺寸不大于 256x256，PNG/JPG</p>
              </Upload.Dragger>
              {logoPreview ? <Image src={logoPreview} width={120} /> : <Typography.Text type="secondary">当前无Logo</Typography.Text>}
            </Space>
          </Card>

          <Card type="inner" title="页面图标（favicon）" style={{ marginBottom: 12 }}>
            <Space>
              <Upload.Dragger {...uploadFaviconProps} style={{ width: 320 }}>
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p className="ant-upload-text">拖拽或点击上传Favicon图片</p>
                <p className="ant-upload-hint">建议方形小图（16x16/32x32），PNG/ICO</p>
              </Upload.Dragger>
              {faviconPreview ? <Image src={faviconPreview} width={32} /> : <Typography.Text type="secondary">当前无Favicon</Typography.Text>}
            </Space>
          </Card>

          <Card type="inner" title="首页轮播配置（JSON）" style={{ marginBottom: 12 }}>
            <Typography.Paragraph type="secondary">粘贴数组，每项包含 title、desc、image、link 字段。</Typography.Paragraph>
            <Input.TextArea
              value={carouselJson}
              onChange={(e) => setCarouselJson(e.target.value)}
              rows={8}
              placeholder='例如：[{"title":"欢迎","desc":"介绍...","image":"/static/banner.jpg","link":"/dashboard"}]'
            />
          </Card>

          <Form.Item>
            <Space>
              <Button type="primary" onClick={onSave}>保存设置</Button>
              <Button onClick={() => { const s = loadSettings(); form.setFieldsValue(s); setLogoPreview(s.logoDataUrl); setFaviconPreview(s.faviconDataUrl) }}>重置为已保存</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}