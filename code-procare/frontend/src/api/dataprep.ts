import { api } from './client'

export interface DataFile {
  name: string
  path: string
  size: number
  mtime: number
}

export interface ColumnInfo {
  name: string
  type: string
  nulls: number
  unique: number
}

export interface PreviewData {
  info: {
    rows: number
    cols: number
    columns: ColumnInfo[]
  }
  preview: any[]
}

export interface Operation {
  type: 'fillna' | 'dropna' | 'rename' | 'astype' | 'drop_col'
  params: any
}

export const listFiles = async (): Promise<{ files: DataFile[] }> => {
  const res = await api.get('/dataprep/files')
  return res.data
}

export const previewData = async (filePath: string): Promise<PreviewData> => {
  const res = await api.post('/dataprep/preview', { file_path: filePath })
  return res.data
}

export const applyOps = async (filePath: string, operations: Operation[], saveAs?: string) => {
  const res = await api.post('/dataprep/apply', { 
    file_path: filePath, 
    operations, 
    save_as: saveAs 
  })
  return res.data
}
