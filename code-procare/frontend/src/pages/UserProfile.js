import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { Typography, Card, Avatar, Row, Col, Statistic, List, Tag, Button, Tabs, Space, Modal, Form, Input, message, Upload } from 'antd';
import { UserOutlined, ProjectOutlined, FileTextOutlined, SafetyCertificateOutlined, SettingOutlined, ClockCircleOutlined, EditOutlined, LogoutOutlined, PlusOutlined, LoadingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { loadSettings, saveSettingsToBackend } from '../utils/systemSettings';
import './UserProfile.css';
const { Title, Text, Paragraph } = Typography;
const UserProfile = () => {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [editModalVisible, setEditModalVisible] = useState(false);
    const [form] = Form.useForm();
    const [userInfo, setUserInfo] = useState({
        name: '研究员',
        role: '高级分析师',
        email: 'researcher@example.com',
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
        }
        catch (e) {
            console.error(e);
            message.error('保存失败');
        }
    };
    const beforeUpload = (file) => {
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
            setTempAvatar(reader.result);
            setAvatarLoading(false);
        };
        setAvatarLoading(true);
        return false; // Prevent actual upload
    };
    const uploadButton = (_jsxs("div", { children: [avatarLoading ? _jsx(LoadingOutlined, {}) : _jsx(PlusOutlined, {}), _jsx("div", { style: { marginTop: 8 }, children: "Upload" })] }));
    // Mock data for statistics
    const stats = [
        { title: '项目总数', value: 12, icon: _jsx(ProjectOutlined, {}), color: '#1890ff' },
        { title: '报告生成数', value: 45, icon: _jsx(FileTextOutlined, {}), color: '#52c41a' },
        { title: '审计日志', value: 128, icon: _jsx(SafetyCertificateOutlined, {}), color: '#faad14' },
        { title: '系统运行时间', value: '99.9%', icon: _jsx(ClockCircleOutlined, {}), color: '#722ed1' },
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
            children: (_jsx(List, { itemLayout: "horizontal", dataSource: activities, renderItem: (item) => (_jsx(List.Item, { children: _jsx(List.Item.Meta, { avatar: _jsx(Avatar, { icon: item.type === 'project' ? _jsx(ProjectOutlined, {}) :
                                item.type === 'report' ? _jsx(FileTextOutlined, {}) :
                                    item.type === 'settings' ? _jsx(SettingOutlined, {}) :
                                        _jsx(ClockCircleOutlined, {}), style: { backgroundColor: 'var(--bg-color-secondary)', color: 'var(--primary-color)' } }), title: _jsx(Text, { strong: true, children: item.title }), description: _jsx(Text, { type: "secondary", children: item.time }) }) })) })),
        },
        {
            key: '2',
            label: '偏好设置',
            children: (_jsx("div", { style: { padding: '16px 0' }, children: _jsxs(Space, { direction: "vertical", size: "large", style: { width: '100%' }, children: [_jsxs("div", { className: "preference-item", children: [_jsx(Text, { strong: true, children: "\u90AE\u4EF6\u901A\u77E5" }), _jsx(Text, { type: "secondary", style: { display: 'block' }, children: "\u63A5\u6536\u62A5\u544A\u751F\u6210\u5B8C\u6210\u7684\u90AE\u4EF6\u901A\u77E5\u3002" }), _jsx(Tag, { color: "green", children: "\u5DF2\u542F\u7528" })] }), _jsxs("div", { className: "preference-item", children: [_jsx(Text, { strong: true, children: "\u4E3B\u9898\u540C\u6B65" }), _jsx(Text, { type: "secondary", style: { display: 'block' }, children: "\u8DDF\u968F\u7CFB\u7EDF\u8BBE\u7F6E\u540C\u6B65\u4E3B\u9898\u3002" }), _jsx(Tag, { color: "blue", children: "\u81EA\u52A8" })] }), _jsxs("div", { className: "preference-item", children: [_jsx(Text, { strong: true, children: "\u6570\u636E\u4FDD\u7559" }), _jsx(Text, { type: "secondary", style: { display: 'block' }, children: "\u9879\u76EE\u6570\u636E\u4FDD\u755930\u5929\u540E\u81EA\u52A8\u6E05\u7406\u3002" }), _jsx(Tag, { color: "orange", children: "30\u5929" })] })] }) })),
        },
    ];
    return (_jsxs("div", { className: "user-profile-container fade-in", children: [_jsxs("div", { className: "profile-header-card", children: [_jsx("div", { className: "profile-cover" }), _jsx("div", { className: "profile-info-section", children: _jsxs(Row, { gutter: [24, 24], align: "bottom", children: [_jsx(Col, { xs: 24, md: 6, style: { position: 'relative' }, children: _jsx("div", { className: "profile-avatar-wrapper", children: _jsx(Avatar, { size: 120, icon: _jsx(UserOutlined, {}), src: userInfo.avatar, className: "profile-avatar" }) }) }), _jsx(Col, { xs: 24, md: 12, children: _jsxs("div", { className: "profile-text", children: [_jsx(Title, { level: 2, style: { marginBottom: 4 }, children: userInfo.name }), _jsxs(Text, { type: "secondary", style: { fontSize: '16px' }, children: [userInfo.role, " \u2022 \u52A0\u5165\u4E8E ", userInfo.joinDate] }), _jsx(Paragraph, { style: { marginTop: 12, maxWidth: 600 }, children: userInfo.bio })] }) }), _jsx(Col, { xs: 24, md: 6, style: { textAlign: 'right' }, children: _jsxs(Space, { children: [_jsx(Button, { icon: _jsx(EditOutlined, {}), onClick: handleEdit, children: "\u7F16\u8F91\u8D44\u6599" }), _jsx(Button, { icon: _jsx(LogoutOutlined, {}), danger: true, children: "\u9000\u51FA\u767B\u5F55" })] }) })] }) })] }), _jsxs(Row, { gutter: [24, 24], style: { marginTop: 24 }, children: [_jsx(Col, { xs: 24, lg: 16, children: _jsx(Card, { className: "profile-content-card", bordered: false, children: _jsx(Tabs, { defaultActiveKey: "1", items: items }) }) }), _jsxs(Col, { xs: 24, lg: 8, children: [_jsx(Row, { gutter: [16, 16], children: stats.map((stat, index) => (_jsx(Col, { span: 12, children: _jsx(Card, { bordered: false, className: "stat-card", children: _jsx(Statistic, { title: _jsx(Text, { type: "secondary", children: stat.title }), value: stat.value, prefix: _jsx("span", { style: { color: stat.color, marginRight: 8 }, children: stat.icon }), valueStyle: { fontWeight: 600 } }) }) }, index))) }), _jsx(Card, { title: "\u6280\u80FD\u4E0E\u4E13\u957F", bordered: false, style: { marginTop: 24 }, className: "skills-card", children: _jsxs("div", { className: "skills-container", children: [_jsx(Tag, { color: "magenta", children: "\u6570\u636E\u5206\u6790" }), _jsx(Tag, { color: "red", children: "Python" }), _jsx(Tag, { color: "volcano", children: "\u673A\u5668\u5B66\u4E60" }), _jsx(Tag, { color: "orange", children: "\u91D1\u878D\u5EFA\u6A21" }), _jsx(Tag, { color: "gold", children: "\u5E02\u573A\u8C03\u7814" }), _jsx(Tag, { color: "lime", children: "\u62A5\u544A\u64B0\u5199" }), _jsx(Tag, { color: "green", children: "\u6218\u7565\u89C4\u5212" }), _jsx(Tag, { color: "cyan", children: "\u6570\u636E\u53EF\u89C6\u5316" })] }) })] })] }), _jsxs(Modal, { title: "\u7F16\u8F91\u4E2A\u4EBA\u8D44\u6599", open: editModalVisible, onOk: handleSave, onCancel: () => setEditModalVisible(false), okText: "\u4FDD\u5B58", cancelText: "\u53D6\u6D88", children: [_jsx("div", { style: { display: 'flex', justifyContent: 'center', marginBottom: 24 }, children: _jsx(Upload, { name: "avatar", listType: "picture-circle", className: "avatar-uploader", showUploadList: false, beforeUpload: beforeUpload, customRequest: () => { }, children: tempAvatar ? _jsx("img", { src: tempAvatar, alt: "avatar", style: { width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' } }) : uploadButton }) }), _jsxs(Form, { form: form, layout: "vertical", children: [_jsx(Form.Item, { name: "name", label: "\u59D3\u540D", rules: [{ required: true, message: '请输入姓名' }], children: _jsx(Input, {}) }), _jsx(Form.Item, { name: "role", label: "\u804C\u4F4D", children: _jsx(Input, {}) }), _jsx(Form.Item, { name: "bio", label: "\u4E2A\u4EBA\u7B80\u4ECB", children: _jsx(Input.TextArea, { rows: 4 }) }), _jsx(Form.Item, { name: "email", label: "\u90AE\u7BB1", children: _jsx(Input, { disabled: true }) })] })] })] }));
};
export default UserProfile;
