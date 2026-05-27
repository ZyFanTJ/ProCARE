import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button, Card, Col, Form, Input, InputNumber, Progress, Radio, Row, Space, Tag, Typography, Upload, message } from 'antd';
import { FilePdfOutlined, FileTextOutlined, FolderOpenOutlined, ReloadOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons';
import { fetchPaperStatus, generatePaper } from '../api/research';
import { fetchSettingsFromBackend, loadSettings } from '../utils/systemSettings';
const { Title, Text } = Typography;
export default function PaperGenerator() {
    const { jobId } = useParams();
    const [form] = Form.useForm();
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(false);
    const [fileList, setFileList] = useState([]);
    const [settings, setSettings] = useState(() => loadSettings());
    const activeModel = settings?.active_model || settings?.llm?.active_model || '未配置';
    const staticPrefix = useMemo(() => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        return baseApi ? baseApi.replace(/\/api$/, '') : '';
    }, []);
    const resolveStaticUrl = (url) => {
        if (!url)
            return '';
        return url.startsWith('/static/') ? `${staticPrefix}${url}` : url;
    };
    const refreshStatus = async () => {
        if (!jobId)
            return;
        try {
            const next = await fetchPaperStatus(jobId);
            setStatus(next);
        }
        catch {
            setStatus(null);
        }
    };
    useEffect(() => {
        refreshStatus();
        fetchSettingsFromBackend().then((remote) => {
            if (remote)
                setSettings(remote);
        });
    }, [jobId]);
    useEffect(() => {
        if (!jobId)
            return;
        if (status?.status !== 'pending' && status?.status !== 'running')
            return;
        const timer = window.setInterval(refreshStatus, 1500);
        return () => window.clearInterval(timer);
    }, [jobId, status?.status]);
    const uploadProps = {
        multiple: true,
        fileList,
        accept: '.pdf,.bib,.ris,.txt,.doc,.docx',
        openFileDialogOnClick: true,
        beforeUpload: () => false,
        onChange: ({ fileList: next }) => setFileList(next),
    };
    const startGeneration = async () => {
        if (!jobId)
            return;
        let values;
        try {
            values = await form.validateFields();
        }
        catch {
            return;
        }
        setLoading(true);
        try {
            const files = fileList
                .map((file) => file.originFileObj)
                .filter(Boolean);
            const next = await generatePaper(jobId, {
                llm_enabled: true,
                report_language: values.report_language || 'zh',
                report_name: values.report_name,
                template_path: values.template_path,
                writing_requirements: values.writing_requirements,
                llm_timeout_seconds: values.llm_timeout_seconds,
                reference_files: files,
            });
            setStatus(next);
            message.success('论文生成任务已启动');
        }
        catch (e) {
            const detail = e?.response?.data?.detail;
            message.error(detail || (e?.response ? '论文生成启动失败' : '后端服务未连接，请确认 8000 端口已启动'));
        }
        finally {
            setLoading(false);
        }
    };
    const busy = loading || status?.status === 'pending' || status?.status === 'running';
    const completed = status?.status === 'completed';
    const failed = status?.status === 'failed';
    return (_jsxs("div", { children: [_jsxs(Space, { style: { width: '100%', justifyContent: 'space-between', marginBottom: 16 }, align: "center", children: [_jsxs("div", { children: [_jsx(Title, { level: 3, style: { marginBottom: 4 }, children: "\u8BBA\u6587\u751F\u6210" }), _jsxs(Space, { wrap: true, children: [_jsxs(Tag, { color: "blue", children: ["Job: ", jobId] }), _jsxs(Tag, { color: "geekblue", children: ["\u6A21\u578B: ", status?.llm_model || activeModel] }), status?.compile_engine && _jsx(Tag, { color: "green", children: status.compile_engine })] })] }), _jsxs(Space, { children: [_jsx(Button, { icon: _jsx(ReloadOutlined, {}), onClick: refreshStatus, children: "\u5237\u65B0" }), _jsx(Link, { to: `/project/${jobId}`, children: _jsx(Button, { children: "\u8FD4\u56DE\u9879\u76EE" }) })] })] }), _jsxs(Row, { gutter: [16, 16], children: [_jsx(Col, { xs: 24, xl: 14, children: _jsx(Card, { bordered: false, children: _jsxs(Form, { form: form, layout: "vertical", initialValues: { report_language: 'zh', llm_timeout_seconds: 600 }, children: [_jsxs(Row, { gutter: 16, children: [_jsx(Col, { xs: 24, md: 14, children: _jsx(Form.Item, { label: "\u8BBA\u6587\u6807\u9898", name: "report_name", children: _jsx(Input, { placeholder: "\u9ED8\u8BA4\u4F7F\u7528\u7814\u7A76\u4E3B\u9898" }) }) }), _jsx(Col, { xs: 24, md: 10, children: _jsx(Form.Item, { label: "\u8BED\u8A00", name: "report_language", rules: [{ required: true }], children: _jsxs(Radio.Group, { buttonStyle: "solid", children: [_jsx(Radio.Button, { value: "zh", children: "\u4E2D\u6587" }), _jsx(Radio.Button, { value: "en", children: "English" })] }) }) })] }), _jsx(Form.Item, { label: "LaTeX \u6A21\u677F\u8DEF\u5F84", name: "template_path", children: _jsx(Input, { placeholder: "\u7559\u7A7A\u4F7F\u7528\u7CFB\u7EDF\u9ED8\u8BA4\u6A21\u677F" }) }), _jsx(Form.Item, { label: "\u53C2\u8003\u6587\u732E\u6587\u4EF6", children: _jsx(Upload, { ...uploadProps, children: _jsx(Button, { icon: _jsx(UploadOutlined, {}), children: "\u9009\u62E9 PDF / BibTeX \u6587\u4EF6" }) }) }), _jsx(Form.Item, { label: "\u5199\u4F5C\u8981\u6C42", name: "writing_requirements", children: _jsx(Input.TextArea, { rows: 4, placeholder: "\u4F8B\u5982\u6807\u9898\u98CE\u683C\u3001\u6458\u8981\u957F\u5EA6\u3001\u7ED3\u679C\u5448\u73B0\u91CD\u70B9\u3001\u8BA8\u8BBA\u4FA7\u91CD\u70B9" }) }), _jsx(Form.Item, { label: "\u6A21\u578B\u8D85\u65F6\u79D2\u6570", name: "llm_timeout_seconds", children: _jsx(InputNumber, { min: 60, max: 1800, step: 60, style: { width: 180 } }) }), _jsxs(Space, { wrap: true, children: [_jsx(Button, { type: "primary", icon: _jsx(SaveOutlined, {}), loading: busy, onClick: startGeneration, children: "\u5F00\u59CB\u751F\u6210" }), _jsx(Link, { to: `/report/${jobId}`, children: _jsx(Button, { children: "\u67E5\u770B\u62A5\u544A" }) })] })] }) }) }), _jsx(Col, { xs: 24, xl: 10, children: _jsx(Card, { bordered: false, title: "\u751F\u6210\u72B6\u6001", children: _jsxs(Space, { direction: "vertical", size: 14, style: { width: '100%' }, children: [_jsxs(Space, { wrap: true, children: [_jsx(Tag, { color: completed ? 'green' : failed ? 'red' : busy ? 'orange' : 'default', children: status?.status || 'not_started' }), status?.updated_at && _jsx(Text, { type: "secondary", children: status.updated_at })] }), _jsx(Progress, { percent: completed ? 100 : busy ? 60 : failed ? 100 : 0, status: failed ? 'exception' : busy ? 'active' : completed ? 'success' : 'normal' }), failed && _jsx(Text, { type: "danger", children: status?.error || '论文生成失败' }), _jsxs(Space, { wrap: true, children: [completed && status?.pdf_url && (_jsx(Button, { type: "primary", icon: _jsx(FilePdfOutlined, {}), href: resolveStaticUrl(status.pdf_url), target: "_blank", children: "\u8BBA\u6587 PDF" })), completed && status?.tex_url && (_jsx(Button, { icon: _jsx(FileTextOutlined, {}), href: resolveStaticUrl(status.tex_url), target: "_blank", children: "TeX" })), completed && status?.latex_zip_url && (_jsx(Button, { icon: _jsx(FolderOpenOutlined, {}), href: resolveStaticUrl(status.latex_zip_url), target: "_blank", children: "LaTeX \u9879\u76EE" }))] }), completed && (_jsxs("div", { style: { borderTop: '1px solid var(--border-color)', paddingTop: 12 }, children: [_jsx(Text, { type: "secondary", children: "\u9879\u76EE\u76EE\u5F55" }), _jsx("div", { style: { marginTop: 4, fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }, children: status?.latex_project_dir || '-' })] }))] }) }) })] })] }));
}
