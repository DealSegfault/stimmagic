import test from 'node:test'
import assert from 'node:assert/strict'

import { featherAlpha } from './featherAlpha.ts'

test('feathering turns a hard mask edge into fractional alpha', () => {
  const hard = new Uint8ClampedArray([
    0, 0, 0, 255, 255, 255, 0, 0, 0,
  ])

  const feathered = featherAlpha(hard, 9, 1, 1)

  assert.ok(feathered.some(alpha => alpha > 0 && alpha < 255))
  assert.ok(feathered[2] > 0, 'the feather reaches outside the hard selection')
  assert.ok(feathered[6] > 0, 'the feather is symmetric')
})

test('feathering preserves a constant mask', () => {
  const solid = new Uint8ClampedArray(25).fill(255)

  assert.deepEqual(
    featherAlpha(solid, 5, 5, 3),
    solid,
  )
})
