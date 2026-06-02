import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Form, Input, Upload, Button, Space, Typography, message, Image, Tabs, InputNumber, Row, Col, Divider, Radio, Select } from 'antd';
import { InboxOutlined, SettingOutlined, DollarOutlined, BgColorsOutlined, ApiOutlined } from '@ant-design/icons';
import { DEFAULT_SETTINGS, loadSettings, saveSettingsToBackend, fetchSettingsFromBackend, resetSettingsToDefault } from '../utils/systemSettings';
import SkillsSettingsComponent from '../components/SkillsSettings';
const API_KEY_PROVIDERS = ['openai', 'anthropic', 'google', 'deepseek', 'qwen', 'minimax'];
function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}
function sanitizeSettingsForForm(settings) {
    const next = {
        ...settings,
        api_keys: { ...(settings.api_keys || {}) },
        model_costs: { ...(settings.model_costs || {}) },
    };
    return next;
}
function getCurrentThemePreference() {
    return loadSettings().theme || DEFAULT_SETTINGS.theme || 'dark';
}
function withCurrentTheme(settings) {
    return {
        ...settings,
        theme: getCurrentThemePreference(),
    };
}
export default function Settings() {
    const [form] = Form.useForm();
    const [logoPreview, setLogoPreview] = useState();
    const [faviconPreview, setFaviconPreview] = useState();
    const [carouselJson, setCarouselJson] = useState('');
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('general');
    const [persistedSettings, setPersistedSettings] = useState(loadSettings());
    useEffect(() => {
        initSettings();
    }, []);
    const initSettings = async () => {
        setLoading(true);
        try {
            const s = withCurrentTheme(loadSettings());
            setPersistedSettings(s);
            updateForm(s);
            const remote = await fetchSettingsFromBackend();
            if (remote) {
                const synced = withCurrentTheme(remote);
                setPersistedSettings(synced);
                updateForm(synced);
            }
        }
        finally {
            setLoading(false);
        }
    };
    const updateForm = (s) => {
        form.setFieldsValue(sanitizeSettingsForForm(s));
        setLogoPreview(s.logoDataUrl);
        setFaviconPreview(s.faviconDataUrl);
        try {
            setCarouselJson(JSON.stringify(s.carouselSlides || DEFAULT_SETTINGS.carouselSlides, null, 2));
        }
        catch { }
    };
    const onSave = async () => {
        try {
            await form.validateFields();
        }
        catch {
            return;
        }
        // form.getFieldsValue(true) gets all values including those in unmounted tabs
        const vals = form.getFieldsValue(true);
        let slides = DEFAULT_SETTINGS.carouselSlides;
        try {
            slides = JSON.parse(carouselJson);
        }
        catch {
            message.error('轮播配置不是合法JSON');
            return;
        }
        const existingApiKeys = persistedSettings.api_keys || {};
        const incomingApiKeys = vals.api_keys || {};
        const mergedApiKeys = { ...existingApiKeys };
        for (const provider of API_KEY_PROVIDERS) {
            const value = incomingApiKeys?.[provider];
            if (typeof value === 'string' && value.trim()) {
                mergedApiKeys[provider] = value.trim();
            }
        }
        const themeTouched = form.isFieldTouched(['theme']);
        const themeToPersist = themeTouched
            ? (vals.theme || persistedSettings.theme || getCurrentThemePreference())
            : getCurrentThemePreference();
        const merged = {
            ...persistedSettings,
            ...vals,
            theme: themeToPersist,
            api_keys: mergedApiKeys,
            logoDataUrl: logoPreview,
            faviconDataUrl: faviconPreview,
            carouselSlides: slides
        };
        setLoading(true);
        let success = false;
        try {
            success = await saveSettingsToBackend(merged);
        }
        finally {
            setLoading(false);
        }
        if (success) {
            setPersistedSettings(merged);
            message.success('系统设置已保存');
        }
        else {
            message.error('保存失败，请检查后端服务连接');
        }
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
    const onReset = async () => {
        setLoading(true);
        let defaults = null;
        try {
            defaults = await resetSettingsToDefault();
        }
        finally {
            setLoading(false);
        }
        if (defaults) {
            setPersistedSettings(defaults);
            updateForm(defaults);
            message.success('已恢复默认设置');
        }
        else {
            message.error('重置失败，请检查后端服务连接');
        }
    };
    const GeneralSettings = () => (_jsxs(_Fragment, { children: [_jsx(Form.Item, { label: "\u7CFB\u7EDF\u540D\u79F0", name: "systemName", rules: [{ required: true, message: '请输入系统名称' }], children: _jsx(Input, { placeholder: "\u4F8B\u5982\uFF1ARWS\u7814\u7A76\u7CFB\u7EDF" }) }), _jsx(Form.Item, { label: "\u9875\u5E95\u58F0\u660E\u4FE1\u606F", name: "footerText", children: _jsx(Input, { placeholder: "\u4F8B\u5982\uFF1A\u00A9 2025 \u516C\u53F8\u6216\u56E2\u961F\u540D\u79F0" }) }), _jsx(Card, { type: "inner", title: "\u7CFB\u7EDFLogo", style: { marginBottom: 12 }, children: _jsxs(Space, { children: [_jsxs(Upload.Dragger, { ...uploadLogoProps, style: { width: 320 }, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u62D6\u62FD\u6216\u70B9\u51FB\u4E0A\u4F20Logo\u56FE\u7247" }), _jsx("p", { className: "ant-upload-hint", children: "\u5EFA\u8BAE\u5C3A\u5BF8\u4E0D\u5927\u4E8E 256x256\uFF0CPNG/JPG" })] }), logoPreview ? _jsx(Image, { src: logoPreview, width: 120 }) : _jsx(Typography.Text, { type: "secondary", children: "\u5F53\u524D\u65E0Logo" })] }) }), _jsx(Card, { type: "inner", title: "\u9875\u9762\u56FE\u6807\uFF08favicon\uFF09", style: { marginBottom: 12 }, children: _jsxs(Space, { children: [_jsxs(Upload.Dragger, { ...uploadFaviconProps, style: { width: 320 }, children: [_jsx("p", { className: "ant-upload-drag-icon", children: _jsx(InboxOutlined, {}) }), _jsx("p", { className: "ant-upload-text", children: "\u62D6\u62FD\u6216\u70B9\u51FB\u4E0A\u4F20Favicon\u56FE\u7247" }), _jsx("p", { className: "ant-upload-hint", children: "\u5EFA\u8BAE\u65B9\u5F62\u5C0F\u56FE\uFF0816x16/32x32\uFF09\uFF0CPNG/ICO" })] }), faviconPreview ? _jsx(Image, { src: faviconPreview, width: 32 }) : _jsx(Typography.Text, { type: "secondary", children: "\u5F53\u524D\u65E0Favicon" })] }) }), _jsxs(Card, { type: "inner", title: "\u9996\u9875\u8F6E\u64AD\u914D\u7F6E\uFF08JSON\uFF09", style: { marginBottom: 12 }, children: [_jsx(Typography.Paragraph, { type: "secondary", children: "\u7C98\u8D34\u6570\u7EC4\uFF0C\u6BCF\u9879\u5305\u542B title\u3001desc\u3001image\u3001link \u5B57\u6BB5\u3002" }), _jsx(Input.TextArea, { value: carouselJson, onChange: (e) => setCarouselJson(e.target.value), rows: 8, placeholder: '\u4F8B\u5982\uFF1A[{"title":"\u6B22\u8FCE","desc":"\u4ECB\u7ECD...","image":"/static/banner.jpg","link":"/dashboard"}]' })] })] }));
    const AppearanceSettings = () => (_jsxs(Card, { type: "inner", title: "\u5916\u89C2\u4E0E\u8BED\u8A00", children: [_jsx(Form.Item, { label: "\u754C\u9762\u4E3B\u9898", name: "theme", initialValue: "dark", children: _jsxs(Radio.Group, { buttonStyle: "solid", children: [_jsx(Radio.Button, { value: "dark", children: "Sci-Fi (\u6DF1\u8272)" }), _jsx(Radio.Button, { value: "light", children: "Journal (\u6D45\u8272)" })] }) }), _jsx(Form.Item, { label: "\u7CFB\u7EDF\u8BED\u8A00", name: "language", initialValue: "zh", children: _jsxs(Radio.Group, { buttonStyle: "solid", children: [_jsx(Radio.Button, { value: "zh", children: "\u4E2D\u6587 (\u7B80\u4F53)" }), _jsx(Radio.Button, { value: "en", children: "English" })] }) })] }));
    const ModelSettings = () => {
        // Get keys from form current values, fallback to defaults
        const currentCosts = form.getFieldValue('model_costs') || DEFAULT_SETTINGS.model_costs || {};
        const modelKeys = Object.keys(currentCosts);
        if (!modelKeys.includes('default'))
            modelKeys.push('default');
        // Ensure "default" is at the end or specific order if needed
        modelKeys.sort((a, b) => {
            if (a === 'default')
                return 1;
            if (b === 'default')
                return -1;
            return a.localeCompare(b);
        });
        return (_jsxs(_Fragment, { children: [_jsxs(Card, { type: "inner", title: "\u6A21\u578B\u914D\u7F6E", style: { marginBottom: 24 }, children: [_jsx(Form.Item, { label: "\u5168\u5C40\u9ED8\u8BA4\u6A21\u578B", name: "active_model", help: "\u7528\u4E8E\u901A\u7528\u7684\u5BF9\u8BDD\u4E0E\u4EFB\u52A1", children: _jsx(Select, { options: [
                                    { label: 'GPT-5.4', value: 'gpt-5.4' },
                                    { label: 'Gemini 3 Pro Preview', value: 'gemini-3-pro-preview' },
                                    { label: 'Claude Sonnet 4.6', value: 'claude-sonnet-4-6' },
                                    { label: 'Qwen 3.5 Plus', value: 'qwen3.5-plus' },
                                    { label: 'MiniMax M2.5 Highspeed', value: 'minimax-m2.5-highspeed' },
                                    { label: 'DeepSeek V4 Flash', value: 'deepseek-v4-flash' }
                                ] }) }), _jsx(Divider, { orientation: "left", children: "API Keys \u914D\u7F6E" }), _jsxs(Row, { gutter: 24, children: [_jsx(Col, { span: 24, children: _jsx(Form.Item, { label: "API Base URL (OpenAI \u517C\u5BB9\u683C\u5F0F)", name: "api_base_url", help: "\u53EF\u9009\u3002\u9ED8\u8BA4\u7559\u7A7A\u5373\u53EF\u3002\u5982\u9700\u4F7F\u7528\u4E2D\u8F6C\u670D\u52A1\u6216\u672C\u5730\u6A21\u578B\uFF0C\u8BF7\u8F93\u5165\u57FA\u7840\u5730\u5740\uFF08\u4F8B\u5982 https://api.openai.com/v1\uFF09", children: _jsx(Input, { placeholder: "https://..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "OpenAI API Key", name: ['api_keys', 'openai'], children: _jsx(Input.Password, { placeholder: "sk-..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "Anthropic API Key", name: ['api_keys', 'anthropic'], children: _jsx(Input.Password, { placeholder: "sk-ant-..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "Google Gemini API Key", name: ['api_keys', 'google'], children: _jsx(Input.Password, { placeholder: "AIza..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "DeepSeek API Key", name: ['api_keys', 'deepseek'], children: _jsx(Input.Password, { placeholder: "sk-..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "Qwen API Key", name: ['api_keys', 'qwen'], children: _jsx(Input.Password, { placeholder: "sk-..." }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "MiniMax API Key", name: ['api_keys', 'minimax'], children: _jsx(Input.Password, { placeholder: "sk-..." }) }) })] })] }), _jsxs(Card, { type: "inner", title: "\u6A21\u578B\u6210\u672C\u8BBE\u7F6E (\u6BCF1M tokens\u4EF7\u683C)", children: [_jsx(Typography.Paragraph, { type: "secondary", children: "\u914D\u7F6E\u4E0D\u540C\u6A21\u578B\u7684\u8F93\u5165/\u8F93\u51FA\u4EF7\u683C\uFF08\u5355\u4F4D\uFF1A\u7F8E\u5143/$\uFF09\u3002\u7CFB\u7EDF\u5C06\u6839\u636E\u6A21\u578B\u540D\u79F0\u524D\u7F00\u5339\u914D\u89C4\u5219\u8BA1\u7B97\u6210\u672C\u3002" }), modelKeys.map(modelKey => (_jsxs("div", { style: { marginBottom: 24 }, children: [_jsx(Typography.Title, { level: 5, style: { marginTop: 0 }, children: modelKey === 'default' ? '默认回退' : `模型前缀: ${modelKey}` }), _jsxs(Row, { gutter: 16, children: [_jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "\u8F93\u5165\u4EF7\u683C ($/1M)", name: ['model_costs', modelKey, 'input_price'], rules: [{ required: true }], children: _jsx(InputNumber, { step: 0.01, min: 0, style: { width: '100%' }, prefix: "$" }) }) }), _jsx(Col, { span: 12, children: _jsx(Form.Item, { label: "\u8F93\u51FA\u4EF7\u683C ($/1M)", name: ['model_costs', modelKey, 'output_price'], rules: [{ required: true }], children: _jsx(InputNumber, { step: 0.01, min: 0, style: { width: '100%' }, prefix: "$" }) }) })] }), _jsx(Divider, { style: { margin: '12px 0' } })] }, modelKey))), _jsx(Typography.Text, { type: "secondary", children: "\u6CE8\uFF1A\u5982\u9700\u6DFB\u52A0\u66F4\u591A\u6A21\u578B\uFF0C\u8BF7\u8054\u7CFB\u7BA1\u7406\u5458\u6216\u76F4\u63A5\u4FEE\u6539\u914D\u7F6E\u6587\u4EF6\u3002\u6B64\u5904\u4EC5\u652F\u6301\u8C03\u6574\u73B0\u6709\u9884\u8BBE\u6A21\u578B\u7684\u8D39\u7387\u3002" })] })] }));
    };
    const items = [
        {
            key: 'general',
            label: _jsxs("span", { children: [_jsx(SettingOutlined, {}), " \u5E38\u89C4\u8BBE\u7F6E"] }),
            children: _jsx(GeneralSettings, {}),
        },
        {
            key: 'appearance',
            label: _jsxs("span", { children: [_jsx(BgColorsOutlined, {}), " \u5916\u89C2\u4E0E\u8BED\u8A00"] }),
            children: _jsx(AppearanceSettings, {}),
        },
        {
            key: 'models',
            label: _jsxs("span", { children: [_jsx(DollarOutlined, {}), " \u6A21\u578B\u4E0EKey"] }),
            children: _jsx(ModelSettings, {}),
        },
        {
            key: 'skills',
            label: _jsxs("span", { children: [_jsx(ApiOutlined, {}), " \u6280\u80FD (Skills)"] }),
            children: _jsx(SkillsSettingsComponent, {}),
        },
    ];
    return (_jsxs("div", { style: { height: 'calc(100vh - 100px)', display: 'flex', flexDirection: 'column' }, children: [_jsx(Typography.Title, { level: 3, style: { marginBottom: 24 }, children: "\u7CFB\u7EDF\u8BBE\u7F6E" }), _jsx(Form, { form: form, layout: "vertical", initialValues: DEFAULT_SETTINGS, style: { flex: 1, overflow: 'hidden' }, children: _jsxs("div", { style: { display: 'flex', height: '100%', gap: 24 }, children: [_jsx("div", { style: { width: 220, flexShrink: 0, background: 'var(--bg-component)', borderRadius: 8, padding: '12px 0' }, children: _jsx(Tabs, { tabPosition: "left", items: items.map(i => ({ key: i.key, label: i.label })), activeKey: activeTab, onChange: setActiveTab, style: { height: '100%' } }) }), _jsxs("div", { style: { flex: 1, overflowY: 'auto', paddingRight: 12 }, children: [items.find(i => i.key === activeTab)?.children, activeTab !== 'skills' && (_jsx("div", { style: { marginTop: 24, marginBottom: 48 }, children: _jsxs(Space, { children: [_jsx(Button, { type: "primary", onClick: onSave, loading: loading, size: "large", children: "\u4FDD\u5B58\u6240\u6709\u8BBE\u7F6E" }), _jsx(Button, { onClick: onReset, loading: loading, children: "\u91CD\u7F6E\u4E3A\u9ED8\u8BA4" })] }) }))] })] }) })] }));
}
