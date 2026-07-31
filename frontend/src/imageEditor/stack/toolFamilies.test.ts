import assert from 'node:assert/strict'
import test from 'node:test'

import { familyById, PAINT_ENGINES, TOOL_FAMILIES } from './toolFamilies.ts'

test('Paint and Retouch are distinct top-level families', () => {
  assert.equal(familyById('paint').label, 'Paint')
  assert.equal(familyById('retouch').label, 'Retouch')
  assert.notEqual(familyById('paint').key, familyById('retouch').key)
})

test('Adjust keeps the stable Levels family id and shortcut', () => {
  assert.equal(familyById('levels').label, 'Adjust')
  assert.equal(familyById('levels').key, 'l')
})

test('Retouch is repairs only — the adjustment surface lives under Adjust', () => {
  const subs = familyById('retouch').subTools.map(tool => tool.id)
  assert.ok(subs.includes('heal') && subs.includes('clone') && subs.includes('patch'))
  assert.ok(subs.includes('remove') && subs.includes('repaint'))
  // The six masked-adjustment doorways were merged into the Adjust family
  // (selection-aware clicks, plan §14); Retouch must not regrow them.
  for (const gone of ['light', 'color', 'detail', 'mixer', 'point', 'grade']) {
    assert.ok(!subs.includes(gone), `retouch should not offer '${gone}'`)
  }
  assert.ok(PAINT_ENGINES.some(engine => engine.id === 'heal'))
  assert.deepEqual(
    TOOL_FAMILIES.filter(family => family.id === 'retouch').map(family => family.defaultSub),
    ['heal'],
  )
})

test('the retired Generate family and Expand tool are absent', () => {
  assert.ok(!TOOL_FAMILIES.some(family => family.id === ('generate' as string)))
  assert.ok(!TOOL_FAMILIES.some(family =>
    family.subTools.some(tool => tool.id === 'expand'),
  ))
})
