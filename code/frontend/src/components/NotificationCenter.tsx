import React, { useState, useEffect } from 'react';
import { Badge, Button, Popover, List, Typography, Empty, Space, Tag, Avatar } from 'antd';
import { BellOutlined, CheckCircleOutlined, ClockCircleOutlined, InfoCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import './NotificationCenter.css';

const { Text, Title } = Typography;

interface Notification {
  id: string;
  title: string;
  description: string;
  type: 'info' | 'success' | 'warning' | 'todo';
  time: string;
  read: boolean;
}

const NotificationCenter: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([
    {
      id: '1',
      title: '报告生成完成',
      description: '《Q3财务分析》报告已准备好审阅。',
      type: 'success',
      time: '2分钟前',
      read: false,
    },
    {
      id: '2',
      title: '新数据待审阅',
      description: '新数据集 "Sales_2024.csv" 需要您的关注。',
      type: 'todo',
      time: '1小时前',
      read: false,
    },
  ]);

  // Simulate incoming notifications
  useEffect(() => {
    const timer = setInterval(() => {
      if (Math.random() > 0.7) {
        const newNotif: Notification = {
          id: Date.now().toString(),
          title: '系统更新',
          description: '项目 #1024 的后台分析已完成。',
          type: 'info',
          time: '刚刚',
          read: false,
        };
        setNotifications(prev => [newNotif, ...prev]);
      }
    }, 30000); // Check every 30s

    return () => clearInterval(timer);
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
  };

  const markAsRead = (id: string) => {
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  };

  const deleteNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  const content = (
    <div className="notification-popover-content">
      <div className="notification-header">
        <Title level={5} style={{ margin: 0 }}>消息通知</Title>
        {notifications.length > 0 && (
          <Button type="link" size="small" onClick={clearAll} style={{ padding: 0 }}>
            全部清空
          </Button>
        )}
      </div>
      <div className="notification-list-wrapper">
        <List
          itemLayout="horizontal"
          dataSource={notifications}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无新消息" /> }}
          renderItem={(item) => (
            <List.Item
              className={`notification-item ${item.read ? 'read' : 'unread'}`}
              actions={[
                !item.read && <Button type="text" icon={<CheckCircleOutlined />} size="small" onClick={() => markAsRead(item.id)} title="标记为已读" />,
                <Button type="text" danger icon={<DeleteOutlined />} size="small" onClick={() => deleteNotification(item.id)} title="删除" />
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Avatar 
                    icon={
                      item.type === 'success' ? <CheckCircleOutlined /> :
                      item.type === 'todo' ? <ClockCircleOutlined /> :
                      <InfoCircleOutlined />
                    }
                    style={{ 
                      backgroundColor: 
                        item.type === 'success' ? '#52c41a' : 
                        item.type === 'todo' ? '#faad14' : '#1890ff' 
                    }}
                  />
                }
                title={
                  <Space>
                    <Text strong={!item.read}>{item.title}</Text>
                    {!item.read && <Tag color="red" style={{ fontSize: '10px', lineHeight: '16px', height: '18px', padding: '0 4px' }}>新</Tag>}
                  </Space>
                }
                description={
                  <div>
                    <div className="notification-desc">{item.description}</div>
                    <Text type="secondary" style={{ fontSize: '11px' }}>{item.time}</Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </div>
      <div className="notification-footer">
        <Button type="link" block size="small">查看历史消息</Button>
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={handleOpenChange}
      placement="bottomRight"
      overlayClassName="notification-popover"
    >
      <Badge count={unreadCount} overflowCount={99} size="small" offset={[-4, 4]}>
        <Button type="text" icon={<BellOutlined />} size="large" className="notification-btn" />
      </Badge>
    </Popover>
  );
};

export default NotificationCenter;
