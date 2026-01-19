export type CarouselSlide = { title?: string; desc?: string; image?: string; link?: string }

export type SystemSettings = {
  systemName: string
  logoDataUrl?: string
  faviconDataUrl?: string
  footerText?: string
  carouselSlides?: CarouselSlide[]
}

const LS_KEY = 'system_settings'

export const DEFAULT_SETTINGS: SystemSettings = {
  systemName: 'RWS研究系统',
  logoDataUrl: '/logo.png',
  faviconDataUrl: '/favicon.ico',
  footerText: '© 2025 AI4RWS System',
  carouselSlides: [
    { title: 'AI4Research', desc: '智能研究助手，让数据分析更高效', image: '/bg4.png', link: '/dashboard' },
    { title: '报告生成', desc: '一键组合章节，快速输出Markdown/PDF', image: '/bg6.png', link: '/reports' },
  ],
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

export function saveSettings(s: SystemSettings) {
  localStorage.setItem(LS_KEY, JSON.stringify(s))
  const ev = new CustomEvent('system-settings-updated', { detail: s })
  window.dispatchEvent(ev)
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
}

export function onSettingsChange(handler: (s: SystemSettings) => void) {
  const fn = (e: Event) => {
    const ce = e as CustomEvent<SystemSettings>
    handler(ce.detail)
  }
  window.addEventListener('system-settings-updated', fn as EventListener)
  return () => window.removeEventListener('system-settings-updated', fn as EventListener)
}