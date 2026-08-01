import assert from 'node:assert/strict'
import test from 'node:test'

import { familyById, PAINT_ENGINES, TOOL_FAMILIES } from './toolFamilies.ts'

test('Paint and Retouch are distinct top-level families', () => {
  assert.equal(familyById('paint').label, 'Paint')
  assert.equal(familyById('retouch').label, 'Retouch')
  assert.notEqual(familyById('paint').key, familyById('retouch').key)
})

test('family shortcuts are unique', () => {
  const keys = TOOL_FAMILIES.map(family => family.key)
  assert.equal(new Set(keys).size, keys.length)
})

test('Adjust keeps the stable Levels family id and shortcut', () => {
  assert.equal(familyById('levels').label, 'Adjust')
  assert.equal(familyById('levels').key, 'l')
})

/**
 * Filters was never a second pipeline — its steps executed as the same
 * `adjust` op — but the second doorway is what kept them from consulting a
 * selection. One parametric family, one selection-aware path.
 */
test('Adjust is the only parametric adjustment family', () => {
  assert.equal(TOOL_FAMILIES.filter(family => family.id === 'levels').length, 1)
  for (const label of ['Filters', 'Effects', 'Looks']) {
    assert.ok(
      !TOOL_FAMILIES.some(family => family.label === label),
      `'${label}' should live inside Adjust, not beside it`,
    )
  }
})

test('Retouch is the non-generative photo-prep family', () => {
  const subs = familyById('retouch').subTools.map(tool => tool.id)
  // Repairs plus the photographic brushes — every tool authors a region.
  for (const expected of [
    'heal', 'clone', 'patch', 'dodge', 'burn', 'sponge', 'blur', 'sharpen',
  ]) {
    assert.ok(subs.includes(expected), `retouch should offer '${expected}'`)
  }
  // The model verbs moved to Generate; Retouch must not regrow them.
  for (const gone of ['remove', 'repaint', 'cutout', 'expand']) {
    assert.ok(!subs.includes(gone), `retouch should not offer '${gone}'`)
  }
  // The six masked-adjustment doorways live under Adjust (selection-aware
  // clicks); Retouch's brushes seed those region kinds but are not them.
  for (const gone of ['light', 'color', 'detail', 'mixer', 'point', 'grade']) {
    assert.ok(!subs.includes(gone), `retouch should not offer '${gone}'`)
  }
  assert.equal(familyById('retouch').defaultSub, 'heal')
})

test('Generate holds every model-backed verb, as labeled chips', () => {
  const generate = familyById('generate')
  assert.equal(generate.label, 'Generate')
  assert.equal(generate.key, 'g')
  assert.deepEqual(
    generate.subTools.map(tool => tool.id),
    ['remove', 'cutout', 'repaint', 'expand'],
  )
  for (const tool of generate.subTools) {
    assert.equal(tool.labeled, true, `'${tool.id}' should show its label`)
  }
  // The model verbs have exactly one home.
  for (const verb of ['remove', 'cutout', 'repaint', 'expand']) {
    const homes = TOOL_FAMILIES.filter(family =>
      family.subTools.some(tool => tool.id === verb),
    )
    assert.deepEqual(homes.map(family => family.id), ['generate'])
  }
})

test('Paint is illustration-only: no pixel-reading engines remain', () => {
  assert.deepEqual(PAINT_ENGINES.map(engine => engine.id), ['paint', 'erase', 'fill', 'gradient'])
  assert.ok(PAINT_ENGINES.every(engine => !engine.readsPixels))
})
