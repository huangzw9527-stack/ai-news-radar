import { useMemo } from 'react'

function SectionHeader({ title, count }) {
  return (
    <div className="flex items-end justify-between border-b border-[var(--color-outline-variant)]/60 pb-2 mb-4">
      <h2 className="font-display text-[18px] font-semibold text-[var(--color-on-surface)]">{title}</h2>
      <span className="text-xs text-[var(--color-outline)]">{count} 条</span>
    </div>
  )
}

function HeadlineCard({ item, rank }) {
  return (
    <div className="bg-[var(--color-surface-low)] border border-[var(--color-outline-variant)]/40 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-6 h-6 bg-[var(--color-primary)] text-white text-xs font-bold rounded flex items-center justify-center shrink-0">
          {rank}
        </span>
        {item.main_category && (
          <span className="text-xs px-2 py-0.5 bg-[var(--color-primary-soft)] text-[var(--color-primary)] rounded-full font-medium">
            {item.main_category}
          </span>
        )}
      </div>
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="font-semibold text-[15px] text-[var(--color-on-surface)] hover:text-[var(--color-primary)] leading-snug block mb-2"
      >
        {item.title}
      </a>
      {item.summary && (
        <p className="text-sm text-[var(--color-on-surface-variant)] leading-relaxed mb-3 bg-[var(--color-background)] rounded px-3 py-2">
          {item.summary}
        </p>
      )}
      {item.why_matters && (
        <div className="flex items-start gap-2 bg-[var(--color-primary-soft)]/30 rounded px-3 py-2">
          <span className="material-symbols-outlined text-[var(--color-primary)] shrink-0 mt-0.5" style={{ fontSize: 14 }}>
            lightbulb
          </span>
          <p className="text-xs text-[var(--color-primary)] leading-relaxed">{item.why_matters}</p>
        </div>
      )}
      <div className="flex items-center justify-between mt-2 text-xs text-[var(--color-outline)]">
        <span>{item.source_name}{item.published_at && ` · ${item.published_at.slice(0, 10)}`}</span>
        {item.score != null && (
          <span>评分 <span className="font-semibold text-[var(--color-on-surface-variant)]">{Math.min(100, Number(item.score)).toFixed(1)}</span></span>
        )}
      </div>
    </div>
  )
}

function CategorizedItem({ item }) {
  return (
    <div className="border-l-2 border-[var(--color-outline-variant)]/60 pl-3 py-1.5">
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="text-sm font-medium text-[var(--color-on-surface)] hover:text-[var(--color-primary)] block leading-snug mb-0.5"
      >
        {item.title}
      </a>
      {item.brief && (
        <p className="text-xs text-[var(--color-on-surface-variant)] leading-relaxed">{item.brief}</p>
      )}
      <div className="flex items-center justify-between text-xs text-[var(--color-outline)]">
        <span>{item.source_name}{item.published_at && ` · ${item.published_at.slice(0, 10)}`}</span>
        {item.score != null && (
          <span>评分 <span className="font-semibold text-[var(--color-on-surface-variant)]">{Math.min(100, Number(item.score)).toFixed(1)}</span></span>
        )}
      </div>
    </div>
  )
}

function ScanItem({ item }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-outline)] shrink-0" />
      <a
        href={item.url} target="_blank" rel="noopener noreferrer"
        className="text-sm text-[var(--color-on-surface-variant)] hover:text-[var(--color-primary)] flex-1 min-w-0 truncate"
      >
        {item.title}
      </a>
      <span className="text-xs text-[var(--color-outline)] shrink-0">{item.source_name}</span>
      {item.score != null && (
        <span className="text-xs text-[var(--color-outline)] shrink-0">
          {Math.min(100, Number(item.score)).toFixed(1)}
        </span>
      )}
    </div>
  )
}

export function ReportPage({ current, collecting, progress, loading, generatingId }) {
  const briefing = current?.briefing || {}
  const headlines = briefing.headlines || []
  const categorized = briefing.categorized || []
  const scan = briefing.scan || []
  const hasBriefing = headlines.length > 0 || categorized.length > 0
  const isGenerating = current?.id === generatingId

  const grouped = useMemo(() => {
    const map = {}
    for (const item of categorized) {
      const cat = item.main_category || '其他'
      if (!map[cat]) map[cat] = []
      map[cat].push(item)
    }
    return map
  }, [categorized])

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="max-w-[900px] mx-auto px-10 py-8">
        {collecting && (
          <div className="mb-6 bg-[var(--color-primary-soft)]/40 border border-[var(--color-primary-soft-strong)]/60 rounded-lg p-5">
            <div className="flex items-center gap-2 mb-3">
              <span className="inline-block w-4 h-4 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-[var(--color-primary)]">报告生成中，请稍候…</p>
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {progress.map((msg, i) => (
                <p key={i} className="text-xs text-[var(--color-primary)]/80 font-mono">{msg}</p>
              ))}
              {progress.length === 0 && (
                <p className="text-xs text-[var(--color-primary)]/60">等待进度信息…</p>
              )}
            </div>
          </div>
        )}

        {!collecting && hasBriefing && (
          <>
            {headlines.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="头条要闻" count={headlines.length} />
                <div className="space-y-4">
                  {headlines.map((item, i) => <HeadlineCard key={i} item={item} rank={i + 1} />)}
                </div>
              </section>
            )}

            {categorized.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="分类精选" count={categorized.length} />
                {Object.entries(grouped).map(([cat, items]) => (
                  <div key={cat} className="mb-5">
                    <p className="text-xs font-semibold uppercase tracking-widest text-[var(--color-primary)] mb-3">{cat}</p>
                    <div className="space-y-3">
                      {items.map((item, i) => <CategorizedItem key={i} item={item} />)}
                    </div>
                  </div>
                ))}
              </section>
            )}

            {scan.length > 0 && (
              <section className="mb-8">
                <SectionHeader title="一句话扫描" count={scan.length} />
                <div className="space-y-0.5">
                  {scan.map((item, i) => <ScanItem key={i} item={item} />)}
                </div>
              </section>
            )}
          </>
        )}

        {!collecting && !loading && !isGenerating && !hasBriefing && (
          current?.id ? (
            <div className="flex flex-col items-center justify-center py-24 text-[var(--color-outline)]">
              <span className="material-symbols-outlined mb-3" style={{ fontSize: 40 }}>filter_alt_off</span>
              <p className="text-base mb-1">本次分析未发现符合当前监控话题的新增新闻</p>
              <p className="text-sm">可在「配置」页放宽或清空监控话题，或点侧边栏「采集新闻」抓取新内容</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-24 text-[var(--color-outline)]">
              <span className="material-symbols-outlined mb-3" style={{ fontSize: 40 }}>radar</span>
              <p className="text-base mb-1">暂无报告</p>
              <p className="text-sm">点击侧边栏「采集新闻」开始</p>
            </div>
          )
        )}

        {!collecting && loading && (
          <div className="flex items-center justify-center py-20">
            <p className="text-[var(--color-outline)] text-sm">加载中…</p>
          </div>
        )}
      </div>
    </main>
  )
}
