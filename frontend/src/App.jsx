import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef, useCallback } from 'react'
import axios from 'axios'
import { ReportPage } from './pages/ReportPage'
import { ConfigPage } from './pages/ConfigPage'
import { isGenerationDone, pickLatestReport } from './lib/generation'
import './index.css'

const GENERATING_ID = '__generating__'

function formatTime(isoStr) {
  if (!isoStr) return { date: '', time: '' }
  const d = new Date(isoStr)
  const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return { date, time }
}

function triggerLabel(trigger) {
  if (trigger === 'manual') return '手动采集'
  if (trigger === 'analyze_only') return '仅分析'
  return '定时'
}

function Sidebar({ reports, current, onLoadReport, onDelete, onCollect, collecting }) {
  const [hoveredId, setHoveredId] = useState(null)

  return (
    <aside className="fixed left-0 top-0 h-screen w-[var(--spacing-sidebar)] bg-white border-r border-[var(--color-outline-variant)]/40 flex flex-col z-40 shadow-[20px_0_40px_rgba(49,46,129,0.04)]">
      {/* Logo */}
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-primary)] flex items-center justify-center text-white">
            <span className="material-symbols-outlined" style={{ fontSize: 22 }}>radar</span>
          </div>
          <div>
            <h1 className="font-display text-[15px] font-bold text-[var(--color-primary)] leading-tight">AI 资讯雷达</h1>
            <p className="text-[11px] text-[var(--color-outline)]">分析报告 · Insight Radar</p>
          </div>
        </div>
        <button
          onClick={onCollect}
          disabled={collecting}
          className="w-full bg-[var(--color-primary)] text-white py-2.5 rounded-md text-sm font-medium hover:bg-[var(--color-primary-container)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 shadow-sm"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add</span>
          {collecting ? '采集中…' : '采集新闻'}
        </button>
      </div>

      {/* History label */}
      <div className="px-6 pt-2 pb-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-outline)]">历史报告</p>
      </div>

      {/* Reports list */}
      <nav className="flex-1 overflow-y-auto sidebar-scroll px-3 pb-4">
        {reports.length === 0 && (
          <p className="px-3 py-2 text-xs text-[var(--color-outline)]">暂无报告</p>
        )}
        {reports.map(r => {
          const isGenerating = r._generating || r.id === GENERATING_ID
          const t = formatTime(r.created_at)
          const isActive = current?.id === r.id

          return (
            <div
              key={r.id}
              className="relative group mb-1"
              onMouseEnter={() => !isGenerating && setHoveredId(r.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <button
                onClick={() => !isGenerating && onLoadReport(r.id)}
                className={[
                  'w-full text-left px-3 py-2.5 rounded-md text-sm transition-colors flex items-center gap-3',
                  isActive
                    ? 'bg-[var(--color-primary-soft)]/60 text-[var(--color-primary)] font-medium border-l-[3px] border-[var(--color-primary)] pl-[calc(0.75rem-3px)]'
                    : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-low)] border-l-[3px] border-transparent pl-[calc(0.75rem-3px)]',
                  isGenerating ? 'cursor-default' : 'cursor-pointer',
                ].join(' ')}
              >
                <span
                  className="material-symbols-outlined shrink-0"
                  style={{ fontSize: 18, color: isActive ? 'var(--color-primary)' : 'var(--color-outline)' }}
                >
                  {isGenerating ? 'hourglass_top' : 'description'}
                </span>
                {isGenerating ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-3.5 h-3.5 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin" />
                    <span className="text-[var(--color-primary)]">生成中…</span>
                  </span>
                ) : (
                  <span className="flex flex-col leading-tight min-w-0">
                    <span className="truncate">{t.date}</span>
                    <span className="text-[11px] text-[var(--color-outline)]">{t.time} · {triggerLabel(r.trigger)}</span>
                  </span>
                )}
              </button>

              {hoveredId === r.id && !isGenerating && (
                <button
                  onClick={(e) => onDelete(e, r.id)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 flex items-center justify-center rounded-full bg-[var(--color-error-container)] text-[var(--color-error)] hover:opacity-80 transition-opacity"
                  title="删除报告"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
                </button>
              )}
            </div>
          )
        })}
      </nav>

      {/* Footer links */}
      <div className="border-t border-[var(--color-outline-variant)]/40 px-3 py-3">
        <NavLink
          to="/config"
          className={({ isActive }) => [
            'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
            isActive
              ? 'bg-[var(--color-surface-low)] text-[var(--color-primary)]'
              : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-low)]',
          ].join(' ')}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>settings</span>
          设置
        </NavLink>
      </div>
    </aside>
  )
}

function TopBar({ onAnalyze, onDownload, collecting, hasReport, onReportRoute }) {
  return (
    <header className="sticky top-0 z-30 bg-white/85 backdrop-blur border-b border-[var(--color-outline-variant)]/40">
      <div className="flex items-center justify-between px-10 py-3">
        <nav className="flex items-center gap-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) => [
              'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
              isActive
                ? 'text-[var(--color-primary)] bg-[var(--color-primary-soft)]/50'
                : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-low)]',
            ].join(' ')}
          >
            报告
          </NavLink>
          <NavLink
            to="/config"
            className={({ isActive }) => [
              'px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
              isActive
                ? 'text-[var(--color-primary)] bg-[var(--color-primary-soft)]/50'
                : 'text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-low)]',
            ].join(' ')}
          >
            配置
          </NavLink>
        </nav>

        {onReportRoute && (
          <div className="flex items-center gap-2">
            <button
              onClick={onAnalyze}
              disabled={collecting}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-sm font-medium bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-container)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>analytics</span>
              仅分析
            </button>
            <button
              onClick={onDownload}
              disabled={!hasReport}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-sm font-medium border border-[var(--color-outline-variant)] text-[var(--color-on-surface-variant)] hover:bg-[var(--color-surface-low)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>download</span>
              下载报告
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const onReportRoute = location.pathname === '/'

  const [reports, setReports] = useState([])
  const [current, setCurrent] = useState(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState([])
  const [collecting, setCollecting] = useState(false)
  const pollRef = useRef(null)
  const reportsRef = useRef(reports)
  reportsRef.current = reports

  const loadReport = useCallback((id) => {
    if (id === GENERATING_ID) return
    setLoading(true)
    axios.get(`/api/reports/${id}`).then(r => {
      setCurrent(r.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const refreshReports = useCallback(() => {
    return axios.get('/api/reports').then(r => {
      setReports(r.data)
      return r.data
    })
  }, [])

  const onGenerationComplete = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    setCollecting(false)

    refreshReports().then(list => {
      const latest = pickLatestReport(list, GENERATING_ID)
      if (latest) loadReport(latest.id)
    })
  }, [refreshReports, loadReport])

  const startGenerating = useCallback((triggerLabelStr, apiCall) => {
    setCollecting(true)
    setProgress([])

    setCurrent({ id: GENERATING_ID })
    setReports(prev => {
      const cleaned = prev.filter(r => r.id !== GENERATING_ID)
      return [{
        id: GENERATING_ID,
        created_at: new Date().toISOString(),
        trigger: triggerLabelStr,
        top10_ids: '[]',
        _generating: true,
      }, ...cleaned]
    })

    apiCall().catch(e => {
      console.error('API error:', e)
      onGenerationComplete()
    })

    pollRef.current = setInterval(() => {
      axios.get('/api/reports').then(r => {
        const generatingItem = reportsRef.current.find(rr => rr.id === GENERATING_ID)
        if (generatingItem) {
          const genTime = new Date(generatingItem.created_at).getTime()
          if (isGenerationDone(r.data, genTime)) {
            onGenerationComplete()
          }
        }
      }).catch(() => {})
    }, 5000)
  }, [onGenerationComplete])

  const triggerCollect = useCallback(() => {
    if (!onReportRoute) navigate('/')
    startGenerating('manual', () => axios.post('/api/collect'))
  }, [startGenerating, onReportRoute, navigate])

  const triggerAnalyze = useCallback(() => {
    startGenerating('analyze_only', () => axios.post('/api/analyze'))
  }, [startGenerating])

  const deleteReport = useCallback(async (e, reportId) => {
    e.stopPropagation()
    e.preventDefault()
    try {
      await axios.delete(`/api/reports/${reportId}`)
      setReports(prev => {
        const filtered = prev.filter(r => r.id !== reportId)
        if (current?.id === reportId) {
          const next = filtered.find(r => r.id !== GENERATING_ID)
          if (next) loadReport(next.id)
          else setCurrent(null)
        }
        return filtered
      })
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.error || err.message))
    }
  }, [current?.id, loadReport])

  const downloadReport = useCallback(() => {
    const briefing = current?.briefing
    if (!briefing) return
    const { headlines = [], categorized = [], scan = [] } = briefing
    if (!headlines.length && !categorized.length) return

    const reportDate = formatTime(current.created_at)

    const headlinesHTML = headlines.map((item, i) => `
    <div class="headline-card">
      <div class="tags">
        <span class="rank">${i + 1}</span>
        ${item.main_category ? `<span class="cat-tag">${item.main_category}</span>` : ''}
      </div>
      <a class="title" href="${item.url}" target="_blank">${item.title} <span style="color:#6860ef">↗</span></a>
      ${item.summary ? `<div class="summary">${item.summary}</div>` : ''}
      ${item.why_matters ? `<div class="why-matters">💡 ${item.why_matters}</div>` : ''}
      <div class="meta">${item.source_name}${item.published_at ? ' · ' + item.published_at.slice(0,10) : ''}</div>
    </div>`).join('')

    const groups = {}
    for (const item of categorized) {
      const cat = item.main_category || '其他'
      if (!groups[cat]) groups[cat] = []
      groups[cat].push(item)
    }
    const categorizedHTML = Object.entries(groups).map(([cat, items]) => `
    <div class="cat-group">
      <p class="cat-header">${cat}</p>
      ${items.map(item => `
        <div class="cat-item">
          <a class="cat-title" href="${item.url}" target="_blank">${item.title}</a>
          ${item.brief ? `<p class="cat-brief">${item.brief}</p>` : ''}
          <p class="meta">${item.source_name}${item.published_at ? ' · ' + item.published_at.slice(0,10) : ''}</p>
        </div>`).join('')}
    </div>`).join('')

    const scanHTML = scan.map(item => `
    <div class="scan-item">
      · <a href="${item.url}" target="_blank">${item.title}</a>
      <span class="scan-source">${item.source_name}</span>
    </div>`).join('')

    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AI News Radar · ${reportDate.date}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'PingFang SC','Microsoft YaHei',sans-serif; background:#f7f9fb; color:#191c1e; line-height:1.6; }
  .container { max-width:820px; margin:0 auto; padding:24px 16px; }
  .header { background:#1a146b; padding:24px; color:#fff; border-radius:12px; margin-bottom:24px; }
  .header h1 { font-size:20px; font-weight:700; }
  .header p { font-size:12px; opacity:0.8; margin-top:4px; }
  h2 { font-size:16px; font-weight:700; border-bottom:2px solid #1a146b; padding-bottom:6px; margin-bottom:16px; color:#191c1e; }
  section { margin-bottom:28px; }
  .headline-card { background:#fff; border-radius:8px; border:1px solid #eceef0; padding:16px; margin-bottom:12px; }
  .tags { display:flex; align-items:center; gap:6px; margin-bottom:8px; }
  .rank { width:22px; height:22px; background:#1a146b; color:#fff; font-size:11px; border-radius:4px; display:inline-flex; align-items:center; justify-content:center; font-weight:700; }
  .cat-tag { font-size:11px; padding:2px 8px; border-radius:12px; background:#e3dfff; color:#4e45d5; font-weight:600; }
  a.title { display:block; font-size:15px; font-weight:700; color:#191c1e; text-decoration:none; margin-bottom:8px; }
  .summary { background:#f7f9fb; border-radius:6px; padding:10px 12px; font-size:13px; color:#474651; margin-bottom:8px; }
  .why-matters { background:#ede9fe; border-radius:6px; padding:8px 12px; font-size:12px; color:#4e45d5; margin-bottom:8px; }
  .meta { font-size:11px; color:#777682; }
  .cat-group { margin-bottom:16px; }
  .cat-header { font-size:11px; font-weight:700; color:#1a146b; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px; }
  .cat-item { border-left:2px solid #e3dfff; padding-left:10px; margin-bottom:10px; }
  a.cat-title { font-size:14px; font-weight:600; color:#191c1e; text-decoration:none; display:block; margin-bottom:2px; }
  .cat-brief { font-size:12px; color:#474651; }
  .scan-item { font-size:13px; color:#474651; padding:4px 0; display:flex; gap:8px; align-items:baseline; }
  .scan-item a { color:#1a146b; text-decoration:none; flex:1; }
  .scan-source { font-size:11px; color:#777682; white-space:nowrap; }
  .footer { text-align:center; padding:20px 0; font-size:11px; color:#777682; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>AI News Radar · 每日简报</h1>
    <p>${reportDate.date} ${reportDate.time}</p>
  </div>
  ${headlines.length ? `<section><h2>头条要闻</h2>${headlinesHTML}</section>` : ''}
  ${categorized.length ? `<section><h2>分类精选</h2>${categorizedHTML}</section>` : ''}
  ${scan.length ? `<section><h2>一句话扫描</h2>${scanHTML}</section>` : ''}
  <div class="footer">AI News Radar · 由 AI 自动生成</div>
</div>
</body>
</html>`

    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AI-News-Radar-${reportDate.date}.html`
    a.click()
    URL.revokeObjectURL(url)
  }, [current])

  // Initial load + WebSocket
  useEffect(() => {
    refreshReports().then(data => {
      const firstValid = data.find(rep => {
        try {
          const b = typeof rep.briefing === 'string' ? JSON.parse(rep.briefing) : (rep.briefing || {})
          return (b.headlines?.length || 0) + (b.categorized?.length || 0) > 0
        } catch { return false }
      })
      if (firstValid) loadReport(firstValid.id)
      else if (data.length > 0) loadReport(data[0].id)
    })

    const wsUrl = `ws://${location.hostname}:8000/ws/progress`
    let ws
    try {
      ws = new WebSocket(wsUrl)
      ws.onmessage = e => {
        const msg = e.data
        setProgress(p => [...p.slice(-20), msg])
        if (msg.includes('完成') && msg.includes('报告ID')) {
          onGenerationComplete()
        }
      }
      ws.onerror = () => {}
    } catch (e) {}

    return () => {
      if (ws) ws.close()
      if (pollRef.current) clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const hasReport = !!(current?.briefing?.headlines?.length || current?.briefing?.categorized?.length)

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Sidebar
        reports={reports}
        current={current}
        onLoadReport={loadReport}
        onDelete={deleteReport}
        onCollect={triggerCollect}
        collecting={collecting}
      />

      <div className="ml-[var(--spacing-sidebar)] min-h-screen flex flex-col">
        <TopBar
          onAnalyze={triggerAnalyze}
          onDownload={downloadReport}
          collecting={collecting}
          hasReport={hasReport}
          onReportRoute={onReportRoute}
        />
        <Routes>
          <Route
            path="/"
            element={
              <ReportPage
                current={current}
                collecting={collecting}
                progress={progress}
                loading={loading}
                generatingId={GENERATING_ID}
              />
            }
          />
          <Route path="/config" element={<ConfigPage />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}
