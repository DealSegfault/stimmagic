import assert from 'node:assert/strict'
import test from 'node:test'

import { annotationBlockOrder } from './annotationBlockOrder.ts'

const items = [
  { id: 'a', annotate: true },
  { id: 'adjust', annotate: false },
  { id: 'b', annotate: true },
  { id: 'c', annotate: true },
  { id: 'paint', annotate: false },
  { id: 'd', annotate: true },
]

test('selected annotations move to the front as an ordered block', () => {
  assert.deepEqual(
    annotationBlockOrder(items, ['a', 'c'], 'front'),
    ['adjust', 'b', 'paint', 'd', 'a', 'c']
  )
})

test('selected annotations move to the back as an ordered block', () => {
  assert.deepEqual(
    annotationBlockOrder(items, ['b', 'd'], 'back'),
    ['b', 'd', 'a', 'adjust', 'c', 'paint']
  )
})

test('an annotation block already at the requested edge is a no-op', () => {
  assert.equal(annotationBlockOrder(items, ['c', 'd'], 'front'), null)
  assert.equal(annotationBlockOrder(items, ['a'], 'back'), null)
})
