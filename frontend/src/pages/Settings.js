import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Form, Input, Upload, Button, Space, Typography, message, Image } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { DEFAULT_SETTINGS, loadSettings, saveSettings } from '../utils/systemSettings';
function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}
export default function Settings() {
    const [form] = Form.useForm();
    const [logoPreview, setLogoPreview] = useState();
    const [faviconPreview, setFaviconPreview] = useState();
    const [carouselJson, setCarouselJson] = useState('');
    useEffect(() => {
        const s = loadSettings();
        form.setFieldsValue(s);
        setLogoPreview(s.logoDataUrl);
        setFaviconPreview(s.faviconDataUrl);
        try {
            setCarouselJson(JSON.stringify(s.carouselSlides || DEFAULT_SETTINGS.carouselSlides, null, 2));
        }
        catch { }
    }, []);
    const onSave = async () => {
        const vals = await form.validateFields();
        let slides = DEFAULT_SETTINGS.carouselSlides;
        try {
            slides = JSON.parse(carouselJson);
        }
        catch {
            message.error('轮播配置不是合法JSON');
            return;
        }
        const merged = { ...DEFAULT_SETTINGS, ...vals, logoDataUrl: logoPreview, faviconDataUrl: faviconPreview, carouselSlides: slides };
        saveSettings(merged);
        message.success('系统设置已保存');
    };
    const uploadLogoProps = {
        name: 'file',
        multiple: false,
        maxCount: 1,
        beforeUpload: async (file) => {
            const url = await fileToDataUrl(file);
            setLogoPreview(url);
            message.success('Logo已选择');
            return false;
        },
        onRemove: () => setLogoPreview(undefined),
    };
    const uploadFaviconProps = {
        name: 'file',
        multiple: false,
        maxCount: 1,
        beforeUpload: async (file) => {
            const url = await fileToDataUrl(file);
            setFaviconPreview(url);
            message.success('页面图标已选择');
            return false;
        },
        onRemove: () => setFaviconPreview(undefined),
    };
    return (_jsxs("div", { children: [_jsx(Typography.Title, { level: 3, children: "\u7CFB\u7EDF\u8BBE\u7F6E" }), _jsx(Card, { children: _jsxs(Form, { form: form, layout: "vertical", initialValues: DEFAULT_SETTINGS, children: [_jsx(Form.Item, { label: "\u7CFB\u7EDF\u540D\u79F0", name: "systemName", rules: [{ required: true, message: '请输入系统名称' }], children: _jsx(Input, { placeholder: "\u4F8B\u5982\uFF1ARWS\u7814\u7A76\u7CFB\u7EDF" }) }), _jsx(Form.Item, { label: "\u9875\u5E95\u58F0\u660E\u4FE1\u606F", name: "footerText", children: _jsx(Input, { placeholder: "\u4F8B\u5982\uFF1A\u00A9 2025 \u516C\u53F8\u6216\u56E2\u961F\u540D\u79F0" }) }), _jsx(Card, { type: "inner", title: "\u7CFB\u7EDFLogo", style: { marginBottom: 12 }, children: _jsxs(Space, { children: [_jsxs(Upload.Dragger, { ...uploadLogoProps, style: { width: 320 }, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u62D6\u62FD\u6216\u70B9\u51FB\u4E0A\u4F20Logo\u56FE\u7247" }), _jsx("p", { className: "ant-upload-hint", children: "\u5EFA\u8BAE\u5C3A\u5BF8\u4E0D\u5927\u4E8E 256x256\uFF0CPNG/JPG" })] }), logoPreview ? _jsx(Image, { src: logoPreview, width: 120 }) : _jsx(Typography.Text, { type: "secondary", children: "\u5F53\u524D\u65E0Logo" })] }) }), _jsx(Card, { type: "inner", title: "\u9875\u9762\u56FE\u6807\uFF08favicon\uFF09", style: { marginBottom: 12 }, children: _jsxs(Space, { children: [_jsxs(Upload.Dragger, { ...uploadFaviconProps, style: { width: 320 }, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u62D6\u62FD\u6216\u70B9\u51FB\u4E0A\u4F20Favicon\u56FE\u7247" }), _jsx("p", { className: "ant-upload-hint", children: "\u5EFA\u8BAE\u65B9\u5F62\u5C0F\u56FE\uFF0816x16/32x32\uFF09\uFF0CPNG/ICO" })] }), faviconPreview ? _jsx(Image, { src: faviconPreview, width: 32 }) : _jsx(Typography.Text, { type: "secondary", children: "\u5F53\u524D\u65E0Favicon" })] }) }), _jsxs(Card, { type: "inner", title: "\u9996\u9875\u8F6E\u64AD\u914D\u7F6E\uFF08JSON\uFF09", style: { marginBottom: 12 }, children: [_jsx(Typography.Paragraph, { type: "secondary", children: "\u7C98\u8D34\u6570\u7EC4\uFF0C\u6BCF\u9879\u5305\u542B title\u3001desc\u3001image\u3001link \u5B57\u6BB5\u3002" }), _jsx(Input.TextArea, { value: carouselJson, onChange: (e) => setCarouselJson(e.target.value), rows: 8, placeholder: '\u4F8B\u5982\uFF1A[{"title":"\u6B22\u8FCE","desc":"\u4ECB\u7ECD...","image":"/static/banner.jpg","link":"/dashboard"}]' })] }), _jsx(Form.Item, { children: _jsxs(Space, { children: [_jsx(Button, { type: "primary", onClick: onSave, children: "\u4FDD\u5B58\u8BBE\u7F6E" }), _jsx(Button, { onClick: () => { const s = loadSettings(); form.setFieldsValue(s); setLogoPreview(s.logoDataUrl); setFaviconPreview(s.faviconDataUrl); }, children: "\u91CD\u7F6E\u4E3A\u5DF2\u4FDD\u5B58" })] }) })] }) })] }));
}
