import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Card, Table } from 'antd';
import { listUploads } from '../api/research';
export default function Files() {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        setLoading(true);
        listUploads().then((res) => setData(res.files || [])).finally(() => setLoading(false));
    }, []);
    const columns = [
        { title: '文件名', dataIndex: 'name', key: 'name' },
        { title: '大小(bytes)', dataIndex: 'size', key: 'size' },
        { title: '时间', dataIndex: 'created_ts', key: 'created_ts', render: (v) => v ? new Date(v * 1000).toLocaleString() : '-' },
        { title: '操作', key: 'action', render: (_, r) => r.url ? _jsx("a", { href: prefixUrl(r.url), target: "_blank", children: "\u4E0B\u8F7D/\u9884\u89C8" }) : '-' },
    ];
    const prefixUrl = (u) => {
        const baseApi = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
        const prefix = baseApi.replace(/\/api$/, '');
        return `${prefix}${u}`;
    };
    return (_jsx(Card, { title: "\u6587\u4EF6\u7BA1\u7406", children: _jsx(Table, { rowKey: "name", columns: columns, dataSource: data, loading: loading, pagination: { pageSize: 10 } }) }));
}
