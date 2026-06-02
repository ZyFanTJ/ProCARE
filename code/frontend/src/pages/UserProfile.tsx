import React, { useState, useEffect } from 'react';
import { Typography, Card, Avatar, Row, Col, Statistic, List, Tag, Button, Divider, Tabs, Space, Modal, Form, Input, message, Upload } from 'antd';
import { UserOutlined, ProjectOutlined, FileTextOutlined, SafetyCertificateOutlined, SettingOutlined, ClockCircleOutlined, EditOutlined, LogoutOutlined, PlusOutlined, LoadingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { loadSettings, saveSettingsToBackend } from '../utils/systemSettings';
import './UserProfile.css';

const { Title, Text, Paragraph } = Typography;

const UserProfile: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [form] = Form.useForm();
  
  const [userInfo, setUserInfo] = useState({
    name: '研究员',
    role: '高级分析师',
    email: 'anonymous@example.invalid',
    joinDate: '2023-10-15',
    bio: '致力于通过数据驱动的研究发现洞见。专精于金融建模与市场分析。',
    avatar: '',
  });

  useEffect(() => {
    // Load profile from system settings
    const settings = loadSettings();
    if (settings.userProfile) {
        setUserInfo(prev => ({
            ...prev,
            ...settings.userProfile,
            // Keep defaults if fields are missing in settings
            name: settings.userProfile?.name || prev.name,
            role: settings.userProfile?.role || prev.role,
            email: settings.userProfile?.email || prev.email,
            bio: settings.userProfile?.bio || prev.bio,
            avatar: settings.userProfile?.avatar || prev.avatar
        }));
    }
    setLoading(false);
  }, []);

  const [avatarLoading, setAvatarLoading] = useState(false);
  const [tempAvatar, setTempAvatar] = useState('');

  const handleEdit = () => {
    form.setFieldsValue(userInfo);
    setTempAvatar(userInfo.avatar);
    setEditModalVisible(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const newInfo = { ...userInfo, ...values, avatar: tempAvatar };
      setUserInfo(newInfo);
      
      // Persist to backend
      const settings = loadSettings();
      const newSettings = {
        ...settings,
        userProfile: {
            name: newInfo.name,
            role: newInfo.role,
            email: newInfo.email,
            bio: newInfo.bio,
            avatar: newInfo.avatar
        }
      };
      await saveSettingsToBackend(newSettings);
      
      setEditModalVisible(false);
      message.success('个人资料已更新');
    } catch (e) {
      console.error(e);
      message.error('保存失败');
    }
  };

  const beforeUpload = (file: File) => {
    const isJpgOrPng = file.type === 'image/jpeg' || file.type === 'image/png';
    if (!isJpgOrPng) {
      message.error('您只能上传 JPG/PNG 格式的文件！');
      return Upload.LIST_IGNORE;
    }
    const isLt2M = file.size / 1024 / 1024 < 2;
    if (!isLt2M) {
      message.error('图片大小必须小于 2MB！');
      return Upload.LIST_IGNORE;
    }
    
    // Convert to base64 for preview
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
        setTempAvatar(reader.result as string);
        setAvatarLoading(false);
    };
    setAvatarLoading(true);
    return false; // Prevent actual upload
  };

  const uploadButton = (
    <div>
      {avatarLoading ? <LoadingOutlined /> : <PlusOutlined />}
      <div style={{ marginTop: 8 }}>Upload</div>
    </div>
  );

  // Mock data for statistics
  const stats = [
    { title: '项目总数', value: 12, icon: <ProjectOutlined />, color: '#1890ff' },
    { title: '报告生成数', value: 45, icon: <FileTextOutlined />, color: '#52c41a' },
    { title: '审计日志', value: 128, icon: <SafetyCertificateOutlined />, color: '#faad14' },
    { title: '系统运行时间', value: '99.9%', icon: <ClockCircleOutlined />, color: '#722ed1' },
  ];

  // Mock data for recent activity
  const activities = [
    { title: '创建了新项目 "2024市场分析"', time: '2小时前', type: 'project' },
    { title: '生成了 "Q3财务报告"', time: '5小时前', type: 'report' },
    { title: '更新了系统设置', time: '1天前', type: 'settings' },
    { title: '上传了3个新数据集', time: '2天前', type: 'data' },
    { title: '完成了审计复核', time: '3天前', type: 'audit' },
  ];

  useEffect(() => {
    // Load profile from system settings
    const settings = loadSettings();
    if (settings.userProfile) {
        setUserInfo(prev => ({
            ...prev,
            ...settings.userProfile,
            // Keep defaults if fields are missing in settings
            name: settings.userProfile?.name || prev.name,
            role: settings.userProfile?.role || prev.role,
            email: settings.userProfile?.email || prev.email,
            bio: settings.userProfile?.bio || prev.bio,
            avatar: settings.userProfile?.avatar || prev.avatar
        }));
    }
    setLoading(false);
  }, []);

  const items = [
    {
      key: '1',
      label: '最近活动',
      children: (
        <List
          itemLayout="horizontal"
          dataSource={activities}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                avatar={
                  <Avatar 
                    icon={
                      item.type === 'project' ? <ProjectOutlined /> :
                      item.type === 'report' ? <FileTextOutlined /> :
                      item.type === 'settings' ? <SettingOutlined /> :
                      <ClockCircleOutlined />
                    } 
                    style={{ backgroundColor: 'var(--bg-color-secondary)', color: 'var(--primary-color)' }}
                  />
                }
                title={<Text strong>{item.title}</Text>}
                description={<Text type="secondary">{item.time}</Text>}
              />
            </List.Item>
          )}
        />
      ),
    },
    {
      key: '2',
      label: '偏好设置',
      children: (
        <div style={{ padding: '16px 0' }}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <div className="preference-item">
              <Text strong>邮件通知</Text>
              <Text type="secondary" style={{ display: 'block' }}>接收报告生成完成的邮件通知。</Text>
              <Tag color="green">已启用</Tag>
            </div>
            <div className="preference-item">
              <Text strong>主题同步</Text>
              <Text type="secondary" style={{ display: 'block' }}>跟随系统设置同步主题。</Text>
              <Tag color="blue">自动</Tag>
            </div>
            <div className="preference-item">
              <Text strong>数据保留</Text>
              <Text type="secondary" style={{ display: 'block' }}>项目数据保留30天后自动清理。</Text>
              <Tag color="orange">30天</Tag>
            </div>
          </Space>
        </div>
      ),
    },
  ];

  return (
    <div className="user-profile-container fade-in">
      <div className="profile-header-card">
        <div className="profile-cover"></div>
        <div className="profile-info-section">
          <Row gutter={[24, 24]} align="bottom">
            <Col xs={24} md={6} style={{ position: 'relative' }}>
              <div className="profile-avatar-wrapper">
                <Avatar 
                  size={120} 
                  icon={<UserOutlined />} 
                  src={userInfo.avatar}
                  className="profile-avatar"
                />
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="profile-text">
                <Title level={2} style={{ marginBottom: 4 }}>{userInfo.name}</Title>
                <Text type="secondary" style={{ fontSize: '16px' }}>{userInfo.role} • 加入于 {userInfo.joinDate}</Text>
                <Paragraph style={{ marginTop: 12, maxWidth: 600 }}>
                  {userInfo.bio}
                </Paragraph>
              </div>
            </Col>
            <Col xs={24} md={6} style={{ textAlign: 'right' }}>
              <Space>
                <Button icon={<EditOutlined />} onClick={handleEdit}>编辑资料</Button>
                <Button icon={<LogoutOutlined />} danger>退出登录</Button>
              </Space>
            </Col>
          </Row>
        </div>
      </div>

      <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={16}>
          <Card className="profile-content-card" bordered={false}>
            <Tabs defaultActiveKey="1" items={items} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Row gutter={[16, 16]}>
            {stats.map((stat, index) => (
              <Col span={12} key={index}>
                <Card bordered={false} className="stat-card">
                  <Statistic
                    title={<Text type="secondary">{stat.title}</Text>}
                    value={stat.value}
                    prefix={<span style={{ color: stat.color, marginRight: 8 }}>{stat.icon}</span>}
                    valueStyle={{ fontWeight: 600 }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
          
          <Card title="技能与专长" bordered={false} style={{ marginTop: 24 }} className="skills-card">
            <div className="skills-container">
              <Tag color="magenta">数据分析</Tag>
              <Tag color="red">Python</Tag>
              <Tag color="volcano">机器学习</Tag>
              <Tag color="orange">金融建模</Tag>
              <Tag color="gold">市场调研</Tag>
              <Tag color="lime">报告撰写</Tag>
              <Tag color="green">战略规划</Tag>
              <Tag color="cyan">数据可视化</Tag>
            </div>
          </Card>
        </Col>
      </Row>

      <Modal
        title="编辑个人资料"
        open={editModalVisible}
        onOk={handleSave}
        onCancel={() => setEditModalVisible(false)}
        okText="保存"
        cancelText="取消"
      >
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
          <Upload
            name="avatar"
            listType="picture-circle"
            className="avatar-uploader"
            showUploadList={false}
            beforeUpload={beforeUpload as any}
            customRequest={() => {}} // Dummy to prevent XHR
          >
            {tempAvatar ? <img src={tempAvatar} alt="avatar" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }} /> : uploadButton}
          </Upload>
        </div>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="职位">
            <Input />
          </Form.Item>
          <Form.Item name="bio" label="个人简介">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="email" label="邮箱">
            <Input disabled />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UserProfile;
