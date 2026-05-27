import { api } from './client'

export interface KnowledgeFile {
  name: string
  size: number
  created_ts: number
  modified_ts: number
}

export const getKnowledgeFiles = async () => {
  const res = await api.get<{ files: KnowledgeFile[] }>('/knowledge_base')
  return res.data
}

export const uploadKnowledgeFile = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/knowledge_base/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export const deleteKnowledgeFile = async (filename: string) => {
  const res = await api.delete(`/knowledge_base/${filename}`)
  return res.data
}

export interface GraphNode {
  id: string
  name: string
  type: 'document' | 'tag' | 'keyword'
  val: number
  group: number
}

export interface GraphLink {
  source: string
  target: string
  value: number
}

export interface KnowledgeGraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

export const getKnowledgeGraph = async () => {
  const res = await api.get<KnowledgeGraphData>('/knowledge_graph')
  return res.data
}
