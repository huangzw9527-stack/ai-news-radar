// Completion detection for report generation.
//
// Bug fix: completion must be keyed on a report ROW having appeared, NOT on
// the briefing being non-empty. "仅分析" can legitimately produce a valid but
// empty report (no news matched the configured topic); the old content-gate
// never fired onGenerationComplete for that case, so the UI span "生成中"
// forever. Reports come from /api/reports ordered created_at DESC, so
// list[0] is the newest.

const SKEW_MS = 5000 // tolerate small client/server clock skew

export function isGenerationDone(reportList, genTimeMs) {
  if (!Array.isArray(reportList) || reportList.length === 0) return false
  const newest = reportList[0]
  if (!newest || !newest.created_at) return false
  const t = new Date(newest.created_at).getTime()
  if (Number.isNaN(t)) return false
  return t >= genTimeMs - SKEW_MS
}

export function pickLatestReport(reportList, generatingId) {
  if (!Array.isArray(reportList)) return null
  return reportList.find(r => r && r.id !== generatingId) || null
}
