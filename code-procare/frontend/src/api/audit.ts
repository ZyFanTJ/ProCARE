
import { api } from './client'

export interface AuditLog {
  id: number
  timestamp: number
  job_id: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost: number
  endpoint: string
}

export interface AuditStats {
  total_cost: number
  total_tokens: number
  top_jobs: {
    job_id: string
    cost: number
    tokens: number
  }[]
}

export async function fetchAuditLogs(limit: number = 100, offset: number = 0) {
  const res = await api.get('/audit/logs', { params: { limit, offset } })
  return res.data as AuditLog[]
}

export async function fetchAuditStats() {
  const res = await api.get('/audit/stats')
  return res.data as AuditStats
}
