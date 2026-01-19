import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Typography, Space, Button, Badge, Carousel } from 'antd';
import { useRef } from 'react';
import { listJobs, listUploads, listReports } from '../api/research';
import { DashboardOutlined, CheckCircleOutlined, FolderOpenOutlined, FileTextOutlined, PlusCircleOutlined } from '@ant-design/icons';
import '../assets/dashboard.css';
import { loadSettings } from '../utils/systemSettings';
export default function Dashboard() {
    const [jobs, setJobs] = useState([]);
    const [files, setFiles] = useState([]);
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(false);
    const [slides, setSlides] = useState([]);
    const carouselRef = useRef(null);
    useEffect(() => {
        setLoading(true);
        Promise.all([listJobs(), listUploads(), listReports()])
            .then(([j, f, r]) => {
            setJobs(j.jobs || []);
            setFiles(f.files || []);
            setReports(r.reports || []);
        })
            .finally(() => setLoading(false));
        try {
            const s = loadSettings();
            setSlides(s.carouselSlides || []);
        }
        catch { }
    }, []);
    const jobsTotal = jobs.length;
    const jobsSuccess = jobs.filter(j => j.success === true).length;
    const filesTotal = files.length;
    const reportsTotal = reports.length;
    const sortByCreatedDesc = (arr) => [...arr].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0));
    const recentJobs = sortByCreatedDesc(jobs).slice(0, 5);
    const recentFiles = sortByCreatedDesc(files).slice(0, 5);
    const jobsColumns = [
        { title: 'Job ID', dataIndex: 'job_id', key: 'job_id' },
        { title: '主题', dataIndex: 'topic', key: 'topic' },
        { title: '成功', dataIndex: 'success', key: 'success', render: (v) => v === true ? '是' : v === false ? '否' : '未知' },
        { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v) => v ? new Date(v * 1000).toLocaleString() : '-' },
    ];
    const filesColumns = [
        { title: '文件名', dataIndex: 'name', key: 'name' },
        { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
        { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v) => v ? new Date(v * 1000).toLocaleString() : '-' },
    ];
    return (_jsxs("div", { children: [_jsxs(Card, { className: "dashboard-hero", bordered: false, style: { marginBottom: 16 }, children: [_jsxs("div", { className: "dashboard-hero__title", children: [_jsx(DashboardOutlined, { style: { marginRight: 8 } }), " \u4EEA\u8868\u76D8"] }), _jsx("div", { className: "dashboard-hero__subtitle", children: "\u6982\u89C8\u7814\u7A76\u8FDB\u5C55\u3001\u4E0A\u4F20\u4E0E\u62A5\u544A\u751F\u6210\u60C5\u51B5" }), _jsxs(Space, { style: { marginTop: 12 }, children: [_jsx(Button, { type: "primary", icon: _jsx(PlusCircleOutlined, {}), href: "/", children: "\u65B0\u5EFA\u7814\u7A76" }), _jsx(Button, { icon: _jsx(FileTextOutlined, {}), href: "/reports", children: "\u62A5\u544A\u4E2D\u5FC3" }), _jsx(Button, { icon: _jsx(FolderOpenOutlined, {}), href: "/files", children: "\u6587\u4EF6\u7BA1\u7406" })] }), !!slides?.length && (_jsx("div", { className: "dashboard-carousel", style: { marginTop: 16 }, children: _jsx(Carousel, { ref: carouselRef, autoplay: true, dots: true, pauseOnHover: true, draggable: true, swipeToSlide: true, touchMove: true, children: slides.map((s, i) => (_jsx("div", { children: _jsxs("div", { className: "dashboard-carousel__slide", children: [s.image ? _jsx("img", { src: s.image, alt: s.title || '' }) : _jsx("div", { className: "dashboard-carousel__placeholder" }), _jsxs("div", { className: "dashboard-carousel__overlay", children: [_jsx(Typography.Title, { level: 4, style: { margin: 0 }, children: s.title || '推荐' }), !!s.desc && _jsx(Typography.Paragraph, { style: { margin: 0 }, children: s.desc }), !!s.link && _jsx(Button, { size: "small", type: "primary", href: s.link, children: "\u67E5\u770B" })] }), _jsx("button", { className: "dashboard-carousel__nav dashboard-carousel__nav--prev", onClick: () => carouselRef.current?.prev(), "aria-label": "\u4E0A\u4E00\u5F20" }), _jsx("button", { className: "dashboard-carousel__nav dashboard-carousel__nav--next", onClick: () => carouselRef.current?.next(), "aria-label": "\u4E0B\u4E00\u5F20" })] }) }, i))) }) }))] }), _jsxs(Row, { gutter: 16, children: [_jsx(Col, { span: 6, children: _jsx(Card, { className: "stat-card stat-card--blue", bordered: false, children: _jsxs(Space, { align: "center", children: [_jsx(Badge, { color: "#2563eb" }), _jsx(Statistic, { title: "\u7814\u7A76\u9879\u76EE\u603B\u6570", value: jobsTotal, prefix: _jsx(DashboardOutlined, {}), valueStyle: { color: '#2563eb' } })] }) }) }), _jsx(Col, { span: 6, children: _jsx(Card, { className: "stat-card stat-card--green", bordered: false, children: _jsxs(Space, { align: "center", children: [_jsx(Badge, { color: "#389e0d" }), _jsx(Statistic, { title: "\u6210\u529F\u7814\u7A76\u6570", value: jobsSuccess, prefix: _jsx(CheckCircleOutlined, {}), valueStyle: { color: '#389e0d' } })] }) }) }), _jsx(Col, { span: 6, children: _jsx(Card, { className: "stat-card stat-card--orange", bordered: false, children: _jsxs(Space, { align: "center", children: [_jsx(Badge, { color: "#d46b08" }), _jsx(Statistic, { title: "\u4E0A\u4F20\u6587\u4EF6\u6570", value: filesTotal, prefix: _jsx(FolderOpenOutlined, {}), valueStyle: { color: '#d46b08' } })] }) }) }), _jsx(Col, { span: 6, children: _jsx(Card, { className: "stat-card stat-card--teal", bordered: false, children: _jsxs(Space, { align: "center", children: [_jsx(Badge, { color: "#14b8a6" }), _jsx(Statistic, { title: "\u62A5\u544A\u6570\u91CF", value: reportsTotal, prefix: _jsx(FileTextOutlined, {}), valueStyle: { color: '#14b8a6' } })] }) }) })] }), _jsxs(Row, { gutter: 16, style: { marginTop: 16 }, children: [_jsx(Col, { span: 12, children: _jsx(Card, { title: "\u8FD1\u671F\u7814\u7A76\u9879\u76EE", loading: loading, bordered: false, children: _jsx(Table, { rowKey: "job_id", size: "small", columns: jobsColumns, dataSource: recentJobs, pagination: false }) }) }), _jsx(Col, { span: 12, children: _jsx(Card, { title: "\u8FD1\u671F\u4E0A\u4F20\u6587\u4EF6", loading: loading, bordered: false, children: _jsx(Table, { rowKey: "name", size: "small", columns: filesColumns, dataSource: recentFiles, pagination: false }) }) })] })] }));
}
