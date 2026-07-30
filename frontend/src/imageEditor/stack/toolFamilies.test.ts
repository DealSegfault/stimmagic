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

test('Retouch starts with region repair tools while Paint keeps its working engines', () => {
  assert.deepEqual(
    familyById('retouch').subTools.map(tool => tool.id),
    [
      'heal', 'clone', 'patch', 'remove', 'repaint',
      'light', 'color', 'detail', 'mixer', 'point', 'grade',
    ],
  )
  assert.equal(familyById('retouch').subTools.find(tool => tool.id === 'remove')?.icon, undefined)
  assert.equal(familyById('retouch').subTools.find(tool => tool.id === 'repaint')?.icon, undefined)
  assert.ok(PAINT_ENGINES.some(engine => engine.id === 'heal'))
  assert.deepEqual(
    TOOL_FAMILIES.filter(family => family.id === 'retouch').map(family => family.defaultSub),
    ['heal'],
  )
})

test('masked replacement is Repaint under Retouch, not Inpaint under Generate', () => {
  assert.deepEqual(
    familyById('generate').subTools.map(tool => tool.id),
    ['expand'],
  )
  assert.equal(familyById('generate').defaultSub, 'expand')
})
