import axios from 'axios'

export type CarouselSlide = { title?: string; desc?: string; image?: string; link?: string }

export type ModelCost = {
  input_price: number
  output_price: number
}

export type ModelCosts = {
  [key: string]: ModelCost
}

export type SystemSettings = {
  systemName: string
  logoDataUrl?: string
  faviconDataUrl?: string
  footerText?: string
  carouselSlides?: CarouselSlide[]
  model_costs?: ModelCosts
  active_model?: string
  api_keys?: {
    openai?: string
    anthropic?: string
    google?: string
    deepseek?: string
    qwen?: string
    minimax?: string
    [key: string]: string | undefined
  }
  api_base_url?: string
  language?: 'zh' | 'en'
  theme?: 'light' | 'dark'
  userProfile?: {
    name?: string
    role?: string
    email?: string
    bio?: string
    avatar?: string
  }
}

const LS_KEY = 'system_settings'
const API_BASE = '/api/settings'
const REQUEST_TIMEOUT_MS = 15000
const SENSITIVE_API_KEY_PROVIDERS = ['openai', 'anthropic', 'google', 'deepseek', 'qwen', 'minimax'] as const

export const DEFAULT_SETTINGS: SystemSettings = {
  systemName: 'RWS研究系统',
  logoDataUrl: '/logo.png',
  faviconDataUrl: '/favicon.ico',
  footerText: '2026 AI4RWS System',
  carouselSlides: [
      { title: 'AI4Research', desc: '智能研究助手，让数据分析更高效。', image: '/bg.png', link: '/dashboard' },
      { title: 'AI4Research', desc: '立即开始新的 RWS 研究项目。', image: '/bg2.png', link: '/' },
      { title: 'RWS 专业报告精修', desc: '一键组合报告章节，快速导出 Markdown/PDF。', image: '/bg_report.png', link: '/reports' },
  ],
  model_costs: {
      "default": { "input_price": 5, "output_price": 20 }
  },
  active_model: 'gemini-3-pro-preview',
  api_keys: {},
  api_base_url: '',
  language: 'zh',
  theme: 'dark',
  userProfile: {
    name: '研究员',
    role: '高级分析师',
    email: 'anonymous@example.invalid',
    bio: '致力于通过数据驱动的研究发现洞见。',
    avatar: ''
  }
}

export function loadSettings(): SystemSettings {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettingsLocal(s: SystemSettings) {
  const sanitized = sanitizeSettingsForLocalStorage(s)
  localStorage.setItem(LS_KEY, JSON.stringify(sanitized))
  const ev = new CustomEvent('system-settings-updated', { detail: sanitized })
  window.dispatchEvent(ev)
}

// Deprecated: use saveSettingsToBackend instead
export function saveSettings(s: SystemSettings) {
  saveSettingsLocal(s)
}

export async function fetchSettingsFromBackend(): Promise<SystemSettings | null> {
  try {
    const res = await axios.get(API_BASE, { timeout: REQUEST_TIMEOUT_MS })
    if (res.data) {
      return { ...DEFAULT_SETTINGS, ...res.data }
    }
  } catch (e) {
    console.error("Failed to fetch settings from backend", e)
  }
  return null
}

export async function saveSettingsToBackend(s: SystemSettings): Promise<boolean> {
  try {
    const remote = await fetchBackendSettingsRaw()
    const payload = mergeSettingsForBackendSave(s, remote)
    await axios.post(API_BASE, payload, { timeout: REQUEST_TIMEOUT_MS })
    saveSettingsLocal(payload)
    return true
  } catch (e) {
    console.error("Failed to save settings to backend", e)
    return false
  }
}

export async function resetSettingsToDefault(): Promise<SystemSettings | null> {
  try {
    const res = await axios.post(`${API_BASE}/reset`, undefined, { timeout: REQUEST_TIMEOUT_MS })
    if (res.data && res.data.settings) {
      const defaults = { ...DEFAULT_SETTINGS, ...res.data.settings }
      saveSettingsLocal(defaults)
      return defaults
    }
  } catch (e) {
    console.error("Failed to reset settings", e)
  }
  return null
}

export function applySettings(s: SystemSettings) {
  if (s.systemName) {
    document.title = `${s.systemName} - AI4Research`
  }
  {
    let link = document.querySelector("link[rel='icon']") as HTMLLinkElement | null
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = s.faviconDataUrl || '/favicon.ico'
  }
  if (s.theme) {
    document.documentElement.setAttribute('data-theme', s.theme)
  }
}

function sanitizeSettingsForLocalStorage(s: SystemSettings): SystemSettings {
  const next: SystemSettings = { ...s }
  if (next.api_keys) {
    next.api_keys = {}
    for (const provider of SENSITIVE_API_KEY_PROVIDERS) {
      const value = s.api_keys?.[provider]
      if (value && String(value).trim()) {
        next.api_keys[provider] = ''
      }
    }
  }
  return next
}

async function fetchBackendSettingsRaw(): Promise<SystemSettings | null> {
  try {
    const res = await axios.get(API_BASE, { timeout: REQUEST_TIMEOUT_MS })
    if (res.data && typeof res.data === 'object') {
      return { ...DEFAULT_SETTINGS, ...res.data }
    }
  } catch (e) {
    console.warn('Failed to fetch current backend settings before save', e)
  }
  return null
}

function mergeSettingsForBackendSave(
  next: SystemSettings,
  current: SystemSettings | null,
): SystemSettings {
  const mergedApiKeys: NonNullable<SystemSettings['api_keys']> = {
    ...(current?.api_keys || {}),
  }

  for (const provider of SENSITIVE_API_KEY_PROVIDERS) {
    const value = next.api_keys?.[provider]
    if (typeof value === 'string' && value.trim()) {
      mergedApiKeys[provider] = value.trim()
    }
  }

  return {
    ...(current || {}),
    ...next,
    api_keys: mergedApiKeys,
  }
}

export function onSettingsChange(handler: (s: SystemSettings) => void) {
  const fn = (e: Event) => {
    const ce = e as CustomEvent<SystemSettings>
    handler(ce.detail)
  }
  window.addEventListener('system-settings-updated', fn as EventListener)
  return () => window.removeEventListener('system-settings-updated', fn as EventListener)
}

