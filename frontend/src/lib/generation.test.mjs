// Run: node src/lib/generation.test.mjs
// No test framework — plain node:assert. Covers the "仅分析 stuck 生成中" bug:
// a successfully-saved report with an EMPTY briefing must still count as "done".
import assert from 'node:assert/strict'
import { isGenerationDone, pickLatestReport } from './generation.js'

const GEN = 'GENERATING'
const t0 = Date.parse('2026-05-16T15:47:00.000Z')

let passed = 0
const it = (name, fn) => { fn(); passed++; console.log('  ok -', name) }

// --- isGenerationDone ---
it('no reports yet -> not done', () => {
  assert.equal(isGenerationDone([], t0), false)
})

it('only a stale old report (created before gen start) -> not done', () => {
  const list = [{ id: 'old', created_at: '2026-05-16T14:00:00.000Z' }]
  assert.equal(isGenerationDone(list, t0), false)
})

it('THE BUG: newest report saved at/after gen start but EMPTY briefing -> done', () => {
  const list = [{
    id: 'new', created_at: '2026-05-16T15:47:34.930Z',
    briefing: '{"headlines":[],"categorized":[],"scan":[]}',
  }]
  assert.equal(isGenerationDone(list, t0), true)
})

it('newest report with content saved after gen start -> done', () => {
  const list = [{
    id: 'new', created_at: '2026-05-16T15:48:00.000Z',
    briefing: '{"headlines":[{}],"categorized":[],"scan":[]}',
  }]
  assert.equal(isGenerationDone(list, t0), true)
})

it('5s clock-skew tolerance: report 3s before gen start still counts', () => {
  const list = [{ id: 'new', created_at: new Date(t0 - 3000).toISOString() }]
  assert.equal(isGenerationDone(list, t0), true)
})

it('robust to bad input', () => {
  assert.equal(isGenerationDone(null, t0), false)
  assert.equal(isGenerationDone([{ id: 'x' }], t0), false) // missing created_at
})

// --- pickLatestReport ---
it('skips the GENERATING placeholder, returns newest real report', () => {
  const list = [{ id: GEN }, { id: 'r1' }, { id: 'r2' }]
  assert.equal(pickLatestReport(list, GEN)?.id, 'r1')
})

it('returns null when only the placeholder exists', () => {
  assert.equal(pickLatestReport([{ id: GEN }], GEN), null)
})

it('returns null / handles bad input', () => {
  assert.equal(pickLatestReport([], GEN), null)
  assert.equal(pickLatestReport(null, GEN), null)
})

console.log(`\n${passed} passed`)
