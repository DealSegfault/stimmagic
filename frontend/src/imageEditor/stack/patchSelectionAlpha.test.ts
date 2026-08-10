import assert from 'node:assert/strict'
import test from 'node:test'

import { patchSelectionAlpha } from '../ported/pixelOps.ts'

function rgbaAlpha(values: number[]): Uint8ClampedArray {
  const data = new Uint8ClampedArray(values.length * 4)
  values.forEach((alpha, pixel) => {
    data[pixel * 4] = 255
    data[pixel * 4 + 1] = 255
    data[pixel * 4 + 2] = 255
    data[pixel * 4 + 3] = alpha
  })
  return data
}

test('zero edge blend preserves selection alpha exactly', () => {
  const selection = [0, 48, 255, 192, 0]

  assert.deepEqual(
    patchSelectionAlpha(rgbaAlpha(selection), selection.length, 1, 0),
    new Uint8ClampedArray(selection),
  )
})

test('adaptive edge blending keeps a full-strength core in a narrow patch', () => {
  const coverage = patchSelectionAlpha(
    rgbaAlpha([0, 255, 255, 255, 255, 255, 0]),
    7,
    1,
  )

  assert.equal(coverage[3], 255)
  assert.ok(coverage[1] > 0 && coverage[1] < 255)
  assert.ok(coverage[5] > 0 && coverage[5] < 255)
})

test('patch edge blending stays inside the selection footprint', () => {
  const coverage = patchSelectionAlpha(
    rgbaAlpha([0, 0, 255, 255, 255, 255, 255, 0, 0]),
    9,
    1,
  )

  assert.equal(coverage[0], 0)
  assert.equal(coverage[1], 0)
  assert.equal(coverage[7], 0)
  assert.equal(coverage[8], 0)
  assert.ok(coverage[2] > 0)
  assert.ok(coverage[6] > 0)
})

test('a wide patch has a soft seam and an opaque interior', () => {
  const selection = [
    ...new Array(3).fill(0),
    ...new Array(41).fill(255),
    ...new Array(3).fill(0),
  ]
  const coverage = patchSelectionAlpha(rgbaAlpha(selection), selection.length, 1)

  assert.ok(coverage[3] > 0 && coverage[3] < 255)
  assert.equal(coverage[23], 255)
  assert.ok(coverage[43] > 0 && coverage[43] < 255)
})
