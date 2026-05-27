import { useEffect, useState } from 'react'
import { Card, Form, Input, Upload, Button, Space, Typography, message, Image, Tabs, InputNumber, Row, Col, Divider, Radio, Select } from 'antd'
import type { UploadProps } from 'antd'
import { InboxOutlined, SettingOutlined, DollarOutlined, BgColorsOutlined, ApiOutlined } from '@ant-design/icons'
import { DEFAULT_SETTINGS, loadSettings, saveSettingsToBackend, fetchSettingsFromBackend, resetSettingsToDefault, SystemSettings } from '../utils/systemSettings'
import SkillsSettingsComponent from '../components/SkillsSettings'

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
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('general')

  useEffect(() => {
    initSettings()
  }, [])

  const initSettings = async () => {
    setLoading(true)
    // First load from local
    let s = loadSettings()
    updateForm(s)
    
    // Then try fetch from backend
    const remote = await fetchSettingsFromBackend()
    if (remote) {
      updateForm(remote)
    }
    setLoading(false)
  }

  const updateForm = (s: SystemSettings) => {
    form.setFieldsValue(s)
    setLogoPreview(s.logoDataUrl)
    setFaviconPreview(s.faviconDataUrl)
    try { 
      setCarouselJson(JSON.stringify(s.carouselSlides || DEFAULT_SETTINGS.carouselSlides, null, 2)) 
    } catch {}
  }

  const onSave = async () => {
    try {
      await form.validateFields()
    } catch {
      return
    }
    
    // form.getFieldsValue(true) gets all values including those in unmounted tabs
    const vals = form.getFieldsValue(true)
    let slides = DEFAULT_SETTINGS.carouselSlides
    try { slides = JSON.parse(carouselJson) } catch { message.error('轮播配置不是合法JSON'); return }
    
    // Merge with current settings to prevent losing unmounted fields' values
    const currentSettings = loadSettings()
    
    const merged: SystemSettings = { 
        ...currentSettings,
        ...vals, 
        logoDataUrl: logoPreview, 
        faviconDataUrl: faviconPreview, 
        carouselSlides: slides 
    }
    
    setLoading(true)
    const success = await saveSettingsToBackend(merged)
    setLoading(false)
    
    if (success) {
      message.success('系统设置已保存')
    } else {
      message.error('保存失败，请检查后端服务连接')
    }
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

  const onReset = async () => {
    setLoading(true)
    const defaults = await resetSettingsToDefault()
    setLoading(false)
    if (defaults) {
      updateForm(defaults)
      message.success('已恢复默认设置')
    } else {
      message.error('重置失败，请检查后端服务连接')
    }
  }

  const GeneralSettings = () => (
    <>
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
    </>
  )

  const AppearanceSettings = () => (
    <Card type="inner" title="外观与语言">
      <Form.Item label="界面主题" name="theme" initialValue="dark">
        <Radio.Group buttonStyle="solid">
          <Radio.Button value="dark">Sci-Fi (深色)</Radio.Button>
          <Radio.Button value="light">Journal (浅色)</Radio.Button>
        </Radio.Group>
      </Form.Item>
      <Form.Item label="系统语言" name="language" initialValue="zh">
        <Radio.Group buttonStyle="solid">
          <Radio.Button value="zh">中文 (简体)</Radio.Button>
          <Radio.Button value="en">English</Radio.Button>
        </Radio.Group>
      </Form.Item>
    </Card>
  )

  const ModelSettings = () => {
    // Get keys from form current values, fallback to defaults
    const currentCosts = form.getFieldValue('model_costs') || DEFAULT_SETTINGS.model_costs || {}
    const modelKeys = Object.keys(currentCosts)
    if (!modelKeys.includes('default')) modelKeys.push('default')
    
    // Ensure "default" is at the end or specific order if needed
    modelKeys.sort((a, b) => {
        if (a === 'default') return 1
        if (b === 'default') return -1
        return a.localeCompare(b)
    })

    return (
      <>
        <Card type="inner" title="模型配置" style={{ marginBottom: 24 }}>
          <Form.Item label="全局默认模型" name="active_model" help="用于通用的对话与任务">
            <Select options={[
              { label: 'GPT-5.4', value: 'gpt-5.4' },
              { label: 'Gemini 3 Pro Preview', value: 'gemini-3-pro-preview' },
              { label: 'Claude Sonnet 4.6', value: 'claude-sonnet-4-6' },
              { label: 'Qwen 3.5 Plus', value: 'qwen3.5-plus' },
              { label: 'MiniMax M2.5 Highspeed', value: 'minimax-m2.5-highspeed' },
              { label: 'DeepSeek V4 Flash', value: 'deepseek-v4-flash' }
            ]} />
          </Form.Item>
          
          <Divider orientation="left">API Keys 配置</Divider>
          <Row gutter={24}>
            <Col span={24}>
              <Form.Item label="API Base URL (OpenAI 兼容格式)" name="api_base_url" help="可选。默认留空即可。如需使用中转服务或本地模型，请输入基础地址（例如 https://api.openai.com/v1）">
                <Input placeholder="https://..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="OpenAI API Key" name={['api_keys', 'openai']}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Anthropic API Key" name={['api_keys', 'anthropic']}>
                <Input.Password placeholder="sk-ant-..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Google Gemini API Key" name={['api_keys', 'google']}>
                <Input.Password placeholder="AIza..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="DeepSeek API Key" name={['api_keys', 'deepseek']}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Qwen API Key" name={['api_keys', 'qwen']}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="MiniMax API Key" name={['api_keys', 'minimax']}>
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card type="inner" title="模型成本设置 (每1M tokens价格)">
          <Typography.Paragraph type="secondary">
            配置不同模型的输入/输出价格（单位：美元/$）。系统将根据模型名称前缀匹配规则计算成本。
          </Typography.Paragraph>
          
          {modelKeys.map(modelKey => (
            <div key={modelKey} style={{ marginBottom: 24 }}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>
                {modelKey === 'default' ? '默认回退' : `模型前缀: ${modelKey}`}
              </Typography.Title>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item 
                    label="输入价格 ($/1M)" 
                    name={['model_costs', modelKey, 'input_price']}
                    rules={[{ required: true }]}
                  >
                    <InputNumber step={0.01} min={0} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item 
                    label="输出价格 ($/1M)" 
                    name={['model_costs', modelKey, 'output_price']}
                    rules={[{ required: true }]}
                  >
                    <InputNumber step={0.01} min={0} style={{ width: '100%' }} prefix="$" />
                  </Form.Item>
                </Col>
              </Row>
              <Divider style={{ margin: '12px 0' }} />
            </div>
          ))}
          
          <Typography.Text type="secondary">
            注：如需添加更多模型，请联系管理员或直接修改配置文件。此处仅支持调整现有预设模型的费率。
          </Typography.Text>
        </Card>
      </>
  )}

  const items = [
    {
      key: 'general',
      label: <span><SettingOutlined /> 常规设置</span>,
      children: <GeneralSettings />,
    },
    {
      key: 'appearance',
      label: <span><BgColorsOutlined /> 外观与语言</span>,
      children: <AppearanceSettings />,
    },
    {
      key: 'models',
      label: <span><DollarOutlined /> 模型与Key</span>,
      children: <ModelSettings />,
    },
    {
      key: 'skills',
      label: <span><ApiOutlined /> 技能 (Skills)</span>,
      children: <SkillsSettingsComponent />,
    },
  ];

  return (
    <div style={{ height: 'calc(100vh - 100px)', display: 'flex', flexDirection: 'column' }}>
      <Typography.Title level={3} style={{ marginBottom: 24 }}>系统设置</Typography.Title>
      
      <Form form={form} layout="vertical" initialValues={DEFAULT_SETTINGS} style={{ flex: 1, overflow: 'hidden' }}>
        <div style={{ display: 'flex', height: '100%', gap: 24 }}>
            <div style={{ width: 220, flexShrink: 0, background: 'var(--bg-component)', borderRadius: 8, padding: '12px 0' }}>
                <Tabs 
                    tabPosition="left" 
                    items={items.map(i => ({ key: i.key, label: i.label }))}
                    activeKey={activeTab}
                    onChange={setActiveTab}
                    style={{ height: '100%' }}
                />
            </div>
            
            <div style={{ flex: 1, overflowY: 'auto', paddingRight: 12 }}>
                {items.find(i => i.key === activeTab)?.children}
                
                {activeTab !== 'skills' && (
                  <div style={{ marginTop: 24, marginBottom: 48 }}>
                      <Space>
                          <Button type="primary" onClick={onSave} loading={loading} size="large">保存所有设置</Button>
                          <Button onClick={onReset} loading={loading}>重置为默认</Button>
                      </Space>
                  </div>
                )}
            </div>
        </div>
      </Form>
    </div>
  )
}
