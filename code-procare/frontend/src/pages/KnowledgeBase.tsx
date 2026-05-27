import React, { useEffect, useState, useRef } from 'react'
import { Typography, Upload, message, Button, Space, Popconfirm, Empty, Spin, Segmented, Tooltip, theme } from 'antd'
import { InboxOutlined, DeleteOutlined, FileTextOutlined, ReloadOutlined, AppstoreOutlined, BarsOutlined, SearchOutlined, PlusOutlined } from '@ant-design/icons'
import { getKnowledgeFiles, uploadKnowledgeFile, deleteKnowledgeFile, getKnowledgeGraph, KnowledgeFile, KnowledgeGraphData } from '../api/knowledge'
import KnowledgeGraph from '../components/KnowledgeGraph'
import type { UploadProps } from 'antd'
import styles from './KnowledgeBase.module.css'

const { Title, Text } = Typography
const { Dragger } = Upload

export default function KnowledgeBase() {
  const { token } = theme.useToken()
  const isDark = token.colorBgBase === '#0f172a' || token.colorTextBase === '#f1f5f9'
  
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [graphData, setGraphData] = useState<KnowledgeGraphData>({ nodes: [], links: [] })
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph')
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 })
  const graphContainerRef = useRef<HTMLDivElement>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [filesRes, graphRes] = await Promise.all([
        getKnowledgeFiles(),
        getKnowledgeGraph()
      ])
      
      const fileList = Array.isArray(filesRes.files) ? filesRes.files : []
      setFiles(fileList.sort((a, b) => b.created_ts - a.created_ts))
      
      setGraphData(graphRes)
    } catch (error) {
      console.error(error)
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Resize observer for graph container
  useEffect(() => {
    if (graphContainerRef.current) {
        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                const { width, height } = entry.contentRect;
                setContainerSize({ width, height });
            }
        });
        resizeObserver.observe(graphContainerRef.current);
        return () => resizeObserver.disconnect();
    }
  }, [viewMode]);

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await uploadKnowledgeFile(file)
      message.success(`${file.name} 上传成功`)
      fetchData()
    } catch (error) {
      console.error(error)
      message.error(`${file.name} 上传失败`)
    } finally {
      setUploading(false)
    }
    return false 
  }

  const handleDelete = async (filename: string) => {
    try {
      await deleteKnowledgeFile(filename)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      console.error(error)
      message.error('删除失败')
    }
  }

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    showUploadList: false,
    beforeUpload: (file) => {
        handleUpload(file as File);
        return false;
    },
    onDrop(e) {
      console.log('Dropped files', e.dataTransfer.files)
    },
  }

  return (
    <div className={styles.container}>
      {/* Sidebar */}
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2 className={styles.title}>知识库</h2>
          <Button type="text" icon={<ReloadOutlined style={{ color: 'var(--kb-accent)' }} />} onClick={fetchData} loading={loading} />
        </div>
        
        <div className={styles.uploadArea}>
            <Dragger {...uploadProps} className={styles.uploadDragger} style={{ border: 'none', background: 'transparent' }}>
                <div className={styles.uploadBox}>
                    <PlusOutlined style={{ fontSize: 24, color: 'var(--kb-accent)', marginBottom: 8 }} />
                    <div style={{ color: 'var(--kb-accent)', fontSize: 14 }}>上传文件</div>
                    <div style={{ color: 'var(--kb-text-secondary)', fontSize: 10 }}>支持 PDF / Excel / TXT</div>
                </div>
            </Dragger>
        </div>

        <div className={styles.fileList}>
            {files.length === 0 ? (
                <Empty description={<span style={{ color: 'var(--kb-text-secondary)' }}>暂无文件</span>} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
                files.map(file => (
                    <div key={file.name} className={styles.fileItem}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, overflow: 'hidden' }}>
                            <FileTextOutlined style={{ color: 'var(--kb-accent)' }} />
                            <div style={{ overflow: 'hidden' }}>
                                <div className={styles.fileName} title={file.name}>{file.name}</div>
                                <div className={styles.fileMeta}>{(file.size / 1024).toFixed(1)} KB • {new Date(file.created_ts * 1000).toLocaleDateString()}</div>
                            </div>
                        </div>
                        <Popconfirm
                            title="确定删除文件？"
                            onConfirm={(e) => {
                                e?.stopPropagation();
                                handleDelete(file.name);
                            }}
                            okText="是"
                            cancelText="否"
                            placement="right"
                        >
                            <DeleteOutlined className={styles.deleteBtn} onClick={(e) => e.stopPropagation()} />
                        </Popconfirm>
                    </div>
                ))
            )}
        </div>
      </div>

      {/* Main Content */}
      <div className={styles.mainContent}>
        {/* Toolbar Overlay */}
        <div className={styles.toolbar}>
            <Segmented
              options={[
                { label: '知识图谱', value: 'graph', icon: <AppstoreOutlined /> },
                { label: '文件列表', value: 'list', icon: <BarsOutlined /> },
              ]}
              value={viewMode}
              onChange={(val) => setViewMode(val as 'graph' | 'list')}
              style={{ 
                  background: 'var(--kb-sidebar-bg)', 
                  border: '1px solid var(--kb-sidebar-border)', 
                  color: 'var(--kb-text)',
                  backdropFilter: 'blur(12px)' 
              }}
            />
        </div>

        {viewMode === 'graph' ? (
            <div className={styles.graphContainer} ref={graphContainerRef}>
                {graphData.nodes.length > 0 ? (
                    <KnowledgeGraph 
                        data={graphData} 
                        width={containerSize.width} 
                        height={containerSize.height}
                        isDark={isDark}
                        onNodeClick={(node) => {
                            if (node.type === 'document') {
                                message.info(`文件: ${node.name}`);
                            }
                        }}
                    />
                ) : (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--kb-text-secondary)' }}>
                        <Empty description={<span style={{ color: 'var(--kb-text-secondary)' }}>暂无图谱数据</span>} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    </div>
                )}
            </div>
        ) : (
             <div style={{ padding: 40, overflow: 'auto' }}>
                 <Title level={3} style={{ color: 'var(--kb-text)', marginBottom: 20 }}>文件详情</Title>
                 <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 20 }}>
                     {files.map(file => (
                         <div key={file.name} className={styles.card}>
                             <FileTextOutlined style={{ fontSize: 32, color: 'var(--kb-accent)', marginBottom: 15 }} />
                             <div style={{ color: 'var(--kb-text)', fontWeight: 'bold', marginBottom: 5, overflow: 'hidden', textOverflow: 'ellipsis' }}>{file.name}</div>
                             <div style={{ color: 'var(--kb-text-secondary)', fontSize: 12 }}>{(file.size / 1024).toFixed(1)} KB</div>
                             <div style={{ color: 'var(--kb-text-secondary)', fontSize: 12 }}>{new Date(file.created_ts * 1000).toLocaleString()}</div>
                         </div>
                     ))}
                 </div>
             </div>
        )}
        
        {(loading || uploading) && (
            <div className={styles.loadingOverlay}>
                <Spin size="large" tip="正在处理数据..." />
            </div>
        )}
      </div>
    </div>
  )
}
