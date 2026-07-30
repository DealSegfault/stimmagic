import assert from 'node:assert/strict'
import test from 'node:test'

import { combineAdjustments } from '../ported/colorMatrix.ts'

test('positive local tint moves red and blue toward magenta', () => {
  const matrix = combineAdjustments({ tint: 100 })
  assert.equal(matrix[4], 24)
  assert.equal(matrix[9], 0)
  assert.equal(matrix[14], 24)
})

test('negative local tint moves green without changing neutral channel gains', () => {
  const matrix = combineAdjustments({ tint: -100 })
  assert.equal(matrix[4], 0)
  assert.equal(matrix[9], 24)
  assert.equal(matrix[14], 0)
  assert.deepEqual([matrix[0], matrix[6], matrix[12]], [1, 1, 1])
})
