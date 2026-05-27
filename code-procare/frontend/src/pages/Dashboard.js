import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Typography, Space, Button, Badge, Carousel, Tag } from 'antd';
import { useRef } from 'react';
import { listJobs, listUploads, listReports } from '../api/research';
import { DashboardOutlined, CheckCircleOutlined, FolderOpenOutlined, FileTextOutlined, PlusCircleOutlined, ExperimentOutlined, RightOutlined } from '@ant-design/icons';
import '../assets/dashboard.css';
import { loadSettings, DEFAULT_SETTINGS } from '../utils/systemSettings';
import { Link } from 'react-router-dom';
export default function Dashboard() {
    const [jobs, setJobs] = useState([]);
    const [files, setFiles] = useState([]);
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(false);
    const [slides, setSlides] = useState([]);
    const carouselRef = useRef(null);
    const heroContentRef = useRef(null);
    const resizeTimerRef = useRef(null);
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
            // Ensure we have valid slides, filtering out empty/null entries
            let list = (s.carouselSlides || []).filter(x => x && (x.title || x.image));
            // If no valid slides from settings, use defaults
            if (list.length === 0) {
                list = DEFAULT_SETTINGS.carouselSlides || [];
            }
            setSlides(list);
        }
        catch {
            setSlides(DEFAULT_SETTINGS.carouselSlides || []);
        }
        const ro = new ResizeObserver((entries) => {
            if (resizeTimerRef.current)
                window.clearTimeout(resizeTimerRef.current);
            resizeTimerRef.current = window.setTimeout(() => {
                window.dispatchEvent(new Event('resize'));
            }, 120);
        });
        const el = heroContentRef.current;
        if (el) {
            ro.observe(el);
        }
        return () => {
            if (resizeTimerRef.current)
                window.clearTimeout(resizeTimerRef.current);
            ro.disconnect();
        };
    }, []);
    // Force carousel refresh when slides change
    useEffect(() => {
        if (carouselRef.current && slides.length > 0) {
            // Small delay to ensure DOM is updated
            setTimeout(() => {
                carouselRef.current?.goTo(0, false);
            }, 100);
        }
    }, [slides]);
    const jobsTotal = jobs.length;
    const jobsSuccess = jobs.filter(j => j.success === true).length;
    const filesTotal = files.length;
    const reportsTotal = reports.length;
    const successRate = jobsTotal > 0 ? Math.round((jobsSuccess / jobsTotal) * 100) : 0;
    const sortByCreatedDesc = (arr) => [...arr].sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0));
    const recentJobs = sortByCreatedDesc(jobs).slice(0, 5);
    const recentFiles = sortByCreatedDesc(files).slice(0, 5);
    const jobsColumns = [
        {
            title: '项目 ID',
            dataIndex: 'job_id',
            key: 'job_id',
            render: (v) => _jsx(Link, { to: `/project/${v}`, style: { fontFamily: 'var(--font-mono)', fontWeight: 500 }, children: v })
        },
        {
            title: '研究主题',
            dataIndex: 'topic',
            key: 'topic',
            ellipsis: true,
            render: (v) => v || _jsx("span", { style: { color: 'var(--text-muted)', fontStyle: 'italic' }, children: "\u672A\u547D\u540D\u4E3B\u9898" })
        },
        {
            title: '状态',
            dataIndex: 'success',
            key: 'success',
            width: 100,
            render: (v) => (v === true ? _jsx(Tag, { color: "success", style: { border: 0 }, children: "\u6210\u529F" }) :
                v === false ? _jsx(Tag, { color: "error", style: { border: 0 }, children: "\u5931\u8D25" }) :
                    _jsx(Tag, { color: "processing", style: { border: 0 }, children: "\u8FDB\u884C\u4E2D" }))
        },
        {
            title: '创建时间',
            dataIndex: 'created_ts',
            key: 'created_ts',
            width: 160,
            render: (v) => _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 13 }, children: v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-' })
        },
    ];
    const filesColumns = [
        {
            title: '文件名',
            dataIndex: 'name',
            key: 'name',
            render: (v) => _jsx("span", { style: { fontFamily: 'var(--font-mono)' }, children: v })
        },
        {
            title: '大小',
            dataIndex: 'size',
            key: 'size',
            width: 100,
            render: (v) => _jsx("span", { style: { color: 'var(--text-muted)' }, children: v ? (v / 1024).toFixed(1) + ' KB' : '-' })
        },
        {
            title: '上传时间',
            dataIndex: 'created_ts',
            key: 'created_ts',
            width: 160,
            render: (v) => _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 13 }, children: v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-' })
        },
    ];
    return (_jsxs("div", { className: "dashboard-container", children: [_jsx(Card, { className: "sci-fi-card dashboard-hero", bordered: false, style: { marginBottom: 24 }, children: _jsxs("div", { className: "dashboard-hero__content", ref: heroContentRef, children: [_jsxs("div", { children: [_jsxs("div", { className: "dashboard-hero__title", style: { color: 'var(--neon-cyan)', textShadow: '0 0 10px rgba(6, 182, 212, 0.5)' }, children: [_jsx(DashboardOutlined, { style: { marginRight: 12 } }), " \u79D1\u7814\u63A7\u5236\u53F0"] }), _jsx("div", { className: "dashboard-hero__subtitle", style: { fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }, children: "SYSTEM STATUS: ONLINE | \u667A\u80FD\u5316\u7814\u7A76\u52A9\u7406\u5DF2\u5C31\u7EEA" }), _jsxs(Space, { style: { marginTop: 24 }, size: 16, children: [_jsx(Link, { to: "/wizard", children: _jsx(Button, { type: "primary", size: "large", icon: _jsx(PlusCircleOutlined, {}), className: "hero-btn-primary", children: "\u53D1\u8D77\u65B0\u7814\u7A76" }) }), _jsx(Link, { to: "/reports", children: _jsx(Button, { ghost: true, size: "large", icon: _jsx(FileTextOutlined, {}), className: "hero-btn-secondary", children: "\u67E5\u9605\u62A5\u544A\u5E93" }) }), _jsx(Link, { to: "/data-manager", children: _jsx(Button, { ghost: true, size: "large", icon: _jsx(FolderOpenOutlined, {}), className: "hero-btn-tertiary", children: "\u6570\u636E\u5F52\u6863" }) })] })] }), !!slides?.length && (_jsx("div", { className: "dashboard-carousel-wrapper", children: _jsx(Carousel, { ref: carouselRef, autoplay: true, autoplaySpeed: 8000, dots: { className: 'custom-dots' }, pauseOnHover: true, draggable: true, effect: "fade", children: slides.map((s, i) => (_jsx("div", { children: _jsxs("div", { className: "dashboard-carousel__slide", children: [s.image ? _jsx("img", { src: s.image, alt: s.title || '' }) : _jsx("div", { className: "dashboard-carousel__placeholder" }), _jsxs("div", { className: "dashboard-carousel__overlay", children: [_jsx(Typography.Title, { level: 4, style: { margin: 0, color: '#fff', fontFamily: 'var(--font-display)', fontSize: 18 }, children: s.title || '功能模块' }), !!s.desc && _jsx(Typography.Paragraph, { style: { margin: '4px 0 0', color: 'rgba(255,255,255,0.8)', fontSize: 13 }, children: s.desc }), !!s.link && _jsx(Button, { size: "small", type: "primary", ghost: true, href: s.link, style: { marginTop: 8 }, children: "\u8FDB\u5165" })] })] }) }, i))) }) }))] }) }), _jsxs(Row, { gutter: [24, 24], children: [_jsx(Col, { span: 6, children: _jsxs(Card, { className: "sci-fi-card stat-card", variant: "borderless", children: [_jsx(Statistic, { title: _jsx("span", { className: "stat-label", children: "\u7814\u7A76\u9879\u76EE\u603B\u6570" }), value: jobsTotal, prefix: _jsx(ExperimentOutlined, { style: { color: 'var(--neon-cyan)' } }), valueStyle: { color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 } }), _jsx("div", { className: "stat-footer", children: _jsx(Badge, { color: "var(--neon-cyan)", status: "processing", text: _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 12 }, children: "\u6D3B\u8DC3\u4E2D" }) }) })] }) }), _jsx(Col, { span: 6, children: _jsxs(Card, { className: "sci-fi-card stat-card", variant: "borderless", children: [_jsx(Statistic, { title: _jsx("span", { className: "stat-label", children: "\u8FD0\u884C\u6210\u529F\u7387" }), value: successRate, suffix: "%", prefix: _jsx(CheckCircleOutlined, { style: { color: 'var(--neon-green)' } }), valueStyle: { color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 } }), _jsx("div", { className: "stat-footer", children: _jsx(Badge, { color: "var(--neon-green)", status: "processing", text: _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 12 }, children: "\u7CFB\u7EDF\u7A33\u5B9A" }) }) })] }) }), _jsx(Col, { span: 6, children: _jsxs(Card, { className: "sci-fi-card stat-card", variant: "borderless", children: [_jsx(Statistic, { title: _jsx("span", { className: "stat-label", children: "\u6570\u636E\u8D44\u4EA7\u5F52\u6863" }), value: filesTotal, prefix: _jsx(FolderOpenOutlined, { style: { color: 'var(--neon-purple)' } }), valueStyle: { color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 } }), _jsx("div", { className: "stat-footer", children: _jsx(Badge, { color: "var(--neon-purple)", status: "processing", text: _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 12 }, children: "\u5B58\u50A8\u6B63\u5E38" }) }) })] }) }), _jsx(Col, { span: 6, children: _jsxs(Card, { className: "sci-fi-card stat-card", variant: "borderless", children: [_jsx(Statistic, { title: _jsx("span", { className: "stat-label", children: "\u5DF2\u751F\u6210\u62A5\u544A" }), value: reportsTotal, prefix: _jsx(FileTextOutlined, { style: { color: '#F59E0B' } }), valueStyle: { color: 'var(--text-primary)', fontFamily: 'var(--font-display)', fontWeight: 700 } }), _jsx("div", { className: "stat-footer", children: _jsx(Badge, { color: "#F59E0B", status: "processing", text: _jsx("span", { style: { color: 'var(--text-muted)', fontSize: 12 }, children: "\u6301\u7EED\u4EA7\u51FA" }) }) })] }) })] }), _jsxs(Row, { gutter: [24, 24], style: { marginTop: 24 }, children: [_jsx(Col, { span: 14, children: _jsx(Card, { title: _jsxs(_Fragment, { children: [_jsx(DashboardOutlined, {}), " \u8FD1\u671F\u7814\u7A76\u6D3B\u52A8"] }), className: "sci-fi-card table-card", loading: loading, variant: "borderless", extra: _jsx(Link, { to: "/projects", children: _jsxs(Button, { type: "text", className: "view-all-btn", children: ["\u67E5\u770B\u5168\u90E8 ", _jsx(RightOutlined, {})] }) }), children: _jsx(Table, { rowKey: "job_id", size: "middle", columns: jobsColumns, dataSource: recentJobs, pagination: false, className: "dashboard-table" }) }) }), _jsx(Col, { span: 10, children: _jsx(Card, { title: _jsxs(_Fragment, { children: [_jsx(FolderOpenOutlined, {}), " \u6700\u65B0\u4E0A\u4F20\u6570\u636E"] }), className: "sci-fi-card table-card", loading: loading, variant: "borderless", extra: _jsx(Link, { to: "/data-manager", children: _jsxs(Button, { type: "text", className: "view-all-btn", children: ["\u67E5\u770B\u5168\u90E8 ", _jsx(RightOutlined, {})] }) }), children: _jsx(Table, { rowKey: "name", size: "middle", columns: filesColumns, dataSource: recentFiles, pagination: false, className: "dashboard-table" }) }) })] })] }));
}
