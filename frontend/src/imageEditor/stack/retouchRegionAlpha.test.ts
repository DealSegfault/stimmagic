import test from 'node:test'
import assert from 'node:assert/strict'

import { retouchRegionAlpha } from './retouchRegionAlpha.ts'

test('legacy Retouch caches preserve their exact alpha at Feather 0', () => {
  const legacy = new Uint8ClampedArray([0, 64, 192, 255])
  assert.deepEqual(
    retouchRegionAlpha(legacy, legacy, 4, 1, 0),
    legacy,
  )
})

test('an opaque result cache follows its independent mask', () => {
  const result = new Uint8ClampedArray([255, 255, 255, 255])
  const mask = new Uint8ClampedArray([0, 80, 160, 255])
  assert.deepEqual(
    retouchRegionAlpha(result, mask, 4, 1, 0),
    mask,
  )
})

test('feather never invents pixels outside the available result cache', () => {
  const result = new Uint8ClampedArray([0, 0, 255, 255, 255, 0, 0])
  const mask = new Uint8ClampedArray([0, 0, 255, 255, 255, 0, 0])
  const output = retouchRegionAlpha(result, mask, 7, 1, 1)

  assert.equal(output[0], 0)
  assert.equal(output[6], 0)
  assert.ok(output[2] > 0 && output[2] < 255)
  assert.ok(output[4] > 0 && output[4] < 255)
})
