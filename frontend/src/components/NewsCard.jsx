const categoryStyles = {
  'AI':       { bg: 'bg-blue-50',    text: 'text-blue-700',    border: 'border-blue-100' },
  '算力':     { bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-100' },
  '协同办公': { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-100' },
  '鸿蒙':     { bg: 'bg-rose-50',    text: 'text-rose-700',    border: 'border-rose-100' },
  '信创':     { bg: 'bg-violet-50',  text: 'text-violet-700',  border: 'border-violet-100' },
}

const ANALYSIS_BLOCKS = [
  { key: 'concept',   label: '概念', icon: 'school',       accent: '#2563eb', soft: '#eff6ff' },
  { key: 'principle', label: '原理', icon: 'architecture', accent: '#7c3aed', soft: '#f5f3ff' },
  { key: 'practice',  label: '实践', icon: 'build',        accent: '#047857', soft: '#ecfdf5' },
]

export function NewsCard({ news, rank }) {
  const displayTitle = news.title_cn || news.title
  const cats = Array.isArray(news.categories) ? news.categories : (Array.isArray(news._cats) ? news._cats : [])
  const hasAnalysis = ANALYSIS_BLOCKS.some(b => news[b.key])

  return (
    <article
      className="group bg-white rounded-lg border border-transparent shadow-[20px_0_40px_rgba(49,46,129,0.04)] hover:shadow-[20px_0_40px_rgba(49,46,129,0.08)] hover:border-[var(--color-primary)]/15 transition-all duration-300 flex flex-col overflow-hidden"
    >
      {/* 头部 */}
      <header className="px-6 pt-5 pb-4">
        <div className="flex items-center gap-2 flex-wrap mb-3">
          {rank && (
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-[4px] bg-[var(--color-primary)] text-white text-[11px] font-bold shrink-0">
              {rank}
            </span>
          )}
          {cats.map((cat, i) => {
            const cs = categoryStyles[cat] || { bg: 'bg-[var(--color-surface-low)]', text: 'text-[var(--color-on-surface-variant)]', border: 'border-[var(--color-outline-variant)]/60' }
            return (
              <span
                key={i}
                className={`inline-flex items-center px-2 py-0.5 rounded-[4px] text-[11px] font-semibold tracking-wide border ${cs.bg} ${cs.text} ${cs.border}`}
              >
                {cat}
              </span>
            )
          })}
          {(news.keywords || []).slice(0, 3).map((kw, i) => (
            <span
              key={`kw-${i}`}
              className="inline-flex items-center px-2 py-0.5 rounded-[4px] text-[11px] font-medium bg-[var(--color-secondary-soft)] text-[var(--color-secondary)]"
            >
              {kw}
            </span>
          ))}
          <span className="ml-auto text-[11px] text-[var(--color-outline)] whitespace-nowrap">
            {news.institution && <span>{news.institution}</span>}
            {news.institution && news.published_at && <span className="mx-1">·</span>}
            {news.published_at && <span>{news.published_at.slice(0, 10)}</span>}
          </span>
        </div>

        <a
          href={news.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block font-display text-[17px] font-semibold text-[var(--color-on-surface)] leading-snug group-hover:text-[var(--color-primary)] transition-colors mb-2.5"
        >
          {displayTitle}
          <span className="text-[var(--color-secondary)] text-sm ml-1">↗</span>
        </a>

        {(news.llm_summary || news.summary) && (
          <p className="text-[14px] text-[var(--color-on-surface-variant)] leading-[1.65]">
            {news.llm_summary || news.summary}
          </p>
        )}
      </header>

      {/* 概念 / 原理 / 实践 */}
      {hasAnalysis && (
        <div className="border-t border-[var(--color-outline-variant)]/40 px-6 py-4 bg-[var(--color-surface-low)]/50">
          <p className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[var(--color-on-surface)] mb-3">
            关键点
          </p>
          <div className="space-y-2">
            {ANALYSIS_BLOCKS.map(block => {
              const text = news[block.key]
              if (!text) return null
              return (
                <div
                  key={block.key}
                  className="flex items-start gap-3 px-3 py-2 rounded-md border-l-[3px]"
                  style={{ borderLeftColor: block.accent, backgroundColor: block.soft }}
                >
                  <span
                    className="material-symbols-outlined shrink-0 mt-0.5"
                    style={{ fontSize: 16, color: block.accent }}
                  >
                    {block.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className="text-[10px] font-bold uppercase tracking-[0.05em] mb-0.5"
                      style={{ color: block.accent }}
                    >
                      {block.label}
                    </p>
                    <p className="text-[13px] text-[var(--color-on-surface-variant)] leading-[1.65]">
                      {text}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 评分 */}
      {news.score != null && (
        <footer className="mt-auto border-t border-[var(--color-outline-variant)]/40 px-6 py-2 flex justify-end">
          <span className="text-[11px] text-[var(--color-outline)]">
            评分 <span className="font-semibold text-[var(--color-on-surface-variant)]">{Math.min(100, Number(news.score)).toFixed(1)}</span> 分
          </span>
        </footer>
      )}
    </article>
  )
}
