const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const webRequire = createRequire(path.resolve('web/package.json'))
const ts = webRequire('typescript')
const React = webRequire('react')
const { renderToStaticMarkup } = webRequire('react-dom/server')

function load(relativePath, overrides = {}) {
  const source = fs.readFileSync(relativePath, 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText
  const module = { exports: {} }
  const requireLocal = (name) => overrides[name] ?? webRequire(name)
  new Function('require', 'module', 'exports', compiled)(requireLocal, module, module.exports)
  return module.exports
}

const model = load('web/src/lib/combinedGameActivityViewModel.ts')
const sample = {
  canonical_game_id: 1, canonical_name: 'Synthetic Alpha', steam_appid: 100,
  ccu_period_anchor_date: '2026-10-03', period_avg_ccu_7d: 100,
  chzzk_viewer_hours_observed_7d: 17, bounded_sample_caveat: 'bounded_sample',
}
const rows = [
  sample,
  { ...sample, canonical_game_id: 2, canonical_name: 'Missing', chzzk_viewer_hours_observed_7d: null },
  { ...sample, canonical_game_id: 3, canonical_name: 'Zero', chzzk_viewer_hours_observed_7d: 0 },
  { ...sample, canonical_game_id: 4, canonical_name: 'Missing Steam', period_avg_ccu_7d: null },
  { ...sample, canonical_game_id: 5, canonical_name: 'Origin', period_avg_ccu_7d: 0, chzzk_viewer_hours_observed_7d: 0 },
]
const points = model.buildCombinedActivityPoints(rows, '')
assert.deepEqual(points.map(p => [p.id, p.x, p.y]), [[1, 100, 17], [3, 100, 0], [5, 0, 0]])
assert.equal(model.buildCombinedActivityPoints(rows, 'alpha').length, 1)
assert.equal(model.buildCombinedActivityPoints(rows, 'absent').length, 0)
assert.match(points[0].label, /Synthetic Alpha.*100.*17.*2026-10-03.*bounded_sample/)

const apiCalls = []
const api = load('web/src/api/combinedActivity.ts', {
  './client': { requestJson: (...args) => { apiCalls.push(args); return Promise.resolve([]) } },
})
const signal = new AbortController().signal
api.listGameActivity(signal)
assert.deepEqual(apiCalls, [['/combined/games/activity?limit=200', { signal }]])
const { CombinedGameActivityScatter: Scatter } = load('web/src/components/CombinedGameActivityScatter.tsx', {
  '../lib/combinedGameActivityViewModel': model,
  '../api/combinedActivity': api,
})
const render = (props = {}) => renderToStaticMarkup(React.createElement(Scatter, {
  rows, loading: false, error: null, searchQuery: '', ...props,
}))
const html = render()
assert.equal((html.match(/<circle /g) ?? []).length, 3)
assert.match(html, /cx="760" cy="30"/)
assert.match(html, /cx="760" cy="340"/)
assert.match(html, /cx="100" cy="340"/)
assert.match(html, /tabindex="0" role="img" aria-label="Synthetic Alpha/)
assert.match(html, /Steam average CCU \(7d\)/)
assert.match(html, /Chzzk observed viewer-hours \(7d\)/)
assert.match(html, /not complete Chzzk population activity/)
assert.match(html, /7 KST dates ending 2026-10-03/)
assert.match(render({ loading: true }), /Loading Combined activity/)
assert.doesNotMatch(render({ loading: true }), /<circle /)
assert.match(render({ error: 'Synthetic error' }), /role="alert".*Synthetic error/)
assert.match(render({ searchQuery: 'absent' }), /No plottable activity/)
assert.match(render({ rows: [{ ...rows[1], ccu_period_anchor_date: null }] }), /Shared Steam window unavailable/)
assert.doesNotMatch(render({ rows: [rows[1]] }), /<circle /)
const zeroOnly = render({ rows: [rows[4]] })
assert.match(zeroOnly, /cx="100" cy="340"/)
assert.doesNotMatch(zeroOnly, /NaN|Infinity/)
console.log('Combined activity runtime assertions passed')
