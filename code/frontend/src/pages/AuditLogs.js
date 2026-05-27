import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Typography, Card, Table, Statistic, Row, Col, Tag, Button, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { fetchAuditLogs, fetchAuditStats } from '../api/audit';
const { Title, Paragraph } = Typography;
export default function AuditLogs() {
    const [logs, setLogs] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const loadData = async () => {
        setLoading(true);
        try {
            const [logsData, statsData] = await Promise.all([
                fetchAuditLogs(100, 0),
                fetchAuditStats()
            ]);
            setLogs(logsData);
            setStats(statsData);
        }
        catch (error) {
            console.error("Failed to load audit data", error);
            message.error("加载审计数据失败");
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        loadData();
    }, []);
    const columns = [
        {
            title: '时间',
            dataIndex: 'timestamp',
            key: 'timestamp',
            render: (ts) => new Date(ts * 1000).toLocaleString(),
            width: 180,
        },
        {
            title: '任务ID',
            dataIndex: 'job_id',
            key: 'job_id',
            render: (text) => text ? _jsx(Tag, { color: "blue", children: text }) : _jsx(Tag, { children: "\u7CFB\u7EDF" }),
        },
        {
            title: '模型',
            dataIndex: 'model',
            key: 'model',
        },
        {
            title: 'Token消耗',
            dataIndex: 'total_tokens',
            key: 'total_tokens',
            render: (val, rec) => (_jsxs("span", { children: [val, " ", _jsxs("span", { style: { fontSize: 12, color: '#888' }, children: ["(", rec.prompt_tokens, "/", rec.completion_tokens, ")"] })] })),
        },
        {
            title: '费用 ($)',
            dataIndex: 'cost',
            key: 'cost',
            render: (val) => val.toFixed(4),
        },
        {
            title: '接口端点',
            dataIndex: 'endpoint',
            key: 'endpoint',
        },
    ];
    return (_jsxs("div", { style: { padding: 24, maxWidth: 1200, margin: '0 auto' }, children: [_jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }, children: [_jsxs("div", { children: [_jsx(Title, { level: 2, children: "\uD83D\uDEE1\uFE0F \u7CFB\u7EDF\u5BA1\u8BA1\u4E0E\u8FD0\u884C\u65E5\u5FD7" }), _jsx(Paragraph, { children: "\u67E5\u770B\u7CFB\u7EDF\u8FD0\u884C\u72B6\u6001\u3001API Token \u6D88\u8017\u7EDF\u8BA1\u4EE5\u53CA\u4EFB\u52A1\u6267\u884C\u961F\u5217\u7684\u8BE6\u7EC6\u5386\u53F2\u8BB0\u5F55\u3002" })] }), _jsx(Button, { icon: _jsx(ReloadOutlined, {}), onClick: loadData, loading: loading, children: "\u5237\u65B0" })] }), _jsxs(Row, { gutter: 16, style: { marginBottom: 24 }, children: [_jsx(Col, { span: 8, children: _jsx(Card, { children: _jsx(Statistic, { title: "\u603B\u8D39\u7528", value: stats?.total_cost, precision: 4, prefix: "$" }) }) }), _jsx(Col, { span: 8, children: _jsx(Card, { children: _jsx(Statistic, { title: "\u603BToken\u6D88\u8017", value: stats?.total_tokens }) }) }), _jsx(Col, { span: 8, children: _jsx(Card, { title: "\u6700\u9AD8\u8D39\u7528\u4EFB\u52A1", children: stats?.top_jobs?.[0] ? (_jsxs("div", { children: [_jsx("div", { style: { fontWeight: 'bold' }, children: stats.top_jobs[0].job_id }), _jsxs("div", { children: ["$", stats.top_jobs[0].cost.toFixed(4), " (", stats.top_jobs[0].tokens, " tokens)"] })] })) : '无数据' }) })] }), _jsx(Card, { title: "\u8FD1\u671FAPI\u8C03\u7528\u65E5\u5FD7", children: _jsx(Table, { dataSource: logs, columns: columns, rowKey: "id", loading: loading, pagination: { pageSize: 20 }, size: "small" }) })] }));
}
