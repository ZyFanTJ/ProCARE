import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Badge, Button, Popover, List, Typography, Empty, Space, Tag, Avatar } from 'antd';
import { BellOutlined, CheckCircleOutlined, ClockCircleOutlined, InfoCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import './NotificationCenter.css';
const { Text, Title } = Typography;
const NotificationCenter = () => {
    const [open, setOpen] = useState(false);
    const [notifications, setNotifications] = useState([
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
                const newNotif = {
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
    const handleOpenChange = (newOpen) => {
        setOpen(newOpen);
    };
    const markAsRead = (id) => {
        setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
    };
    const deleteNotification = (id) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };
    const clearAll = () => {
        setNotifications([]);
    };
    const content = (_jsxs("div", { className: "notification-popover-content", children: [_jsxs("div", { className: "notification-header", children: [_jsx(Title, { level: 5, style: { margin: 0 }, children: "\u6D88\u606F\u901A\u77E5" }), notifications.length > 0 && (_jsx(Button, { type: "link", size: "small", onClick: clearAll, style: { padding: 0 }, children: "\u5168\u90E8\u6E05\u7A7A" }))] }), _jsx("div", { className: "notification-list-wrapper", children: _jsx(List, { itemLayout: "horizontal", dataSource: notifications, locale: { emptyText: _jsx(Empty, { image: Empty.PRESENTED_IMAGE_SIMPLE, description: "\u6682\u65E0\u65B0\u6D88\u606F" }) }, renderItem: (item) => (_jsx(List.Item, { className: `notification-item ${item.read ? 'read' : 'unread'}`, actions: [
                            !item.read && _jsx(Button, { type: "text", icon: _jsx(CheckCircleOutlined, {}), size: "small", onClick: () => markAsRead(item.id), title: "\u6807\u8BB0\u4E3A\u5DF2\u8BFB" }),
                            _jsx(Button, { type: "text", danger: true, icon: _jsx(DeleteOutlined, {}), size: "small", onClick: () => deleteNotification(item.id), title: "\u5220\u9664" })
                        ], children: _jsx(List.Item.Meta, { avatar: _jsx(Avatar, { icon: item.type === 'success' ? _jsx(CheckCircleOutlined, {}) :
                                    item.type === 'todo' ? _jsx(ClockCircleOutlined, {}) :
                                        _jsx(InfoCircleOutlined, {}), style: {
                                    backgroundColor: item.type === 'success' ? '#52c41a' :
                                        item.type === 'todo' ? '#faad14' : '#1890ff'
                                } }), title: _jsxs(Space, { children: [_jsx(Text, { strong: !item.read, children: item.title }), !item.read && _jsx(Tag, { color: "red", style: { fontSize: '10px', lineHeight: '16px', height: '18px', padding: '0 4px' }, children: "\u65B0" })] }), description: _jsxs("div", { children: [_jsx("div", { className: "notification-desc", children: item.description }), _jsx(Text, { type: "secondary", style: { fontSize: '11px' }, children: item.time })] }) }) })) }) }), _jsx("div", { className: "notification-footer", children: _jsx(Button, { type: "link", block: true, size: "small", children: "\u67E5\u770B\u5386\u53F2\u6D88\u606F" }) })] }));
    return (_jsx(Popover, { content: content, trigger: "click", open: open, onOpenChange: handleOpenChange, placement: "bottomRight", overlayClassName: "notification-popover", children: _jsx(Badge, { count: unreadCount, overflowCount: 99, size: "small", offset: [-4, 4], children: _jsx(Button, { type: "text", icon: _jsx(BellOutlined, {}), size: "large", className: "notification-btn" }) }) }));
};
export default NotificationCenter;
