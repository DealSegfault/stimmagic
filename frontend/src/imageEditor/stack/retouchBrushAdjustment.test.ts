import assert from 'node:assert/strict'
import test from 'node:test'
import { retouchBrushAdjustmentParams } from './retouchBrushAdjustment.ts'

const settings = {
  exposure: 18,
  range: 'midtones' as const,
  strength: 25,
  saturate: true,
}

test('retouch brush params use the persisted adjustment controls', () => {
  assert.deepEqual(retouchBrushAdjustmentParams('dodge', settings), { exposure: 18 })
  assert.deepEqual(retouchBrushAdjustmentParams('burn', settings), { exposure: -18 })
  assert.deepEqual(retouchBrushAdjustmentParams('sponge', settings), { saturation: 25 })
  assert.deepEqual(retouchBrushAdjustmentParams('blur', settings), { blur: 10 })
  assert.deepEqual(retouchBrushAdjustmentParams('sharpen', settings), { sharpen: 25 })
})

test('dodge and burn preserve range targeting', () => {
  assert.deepEqual(retouchBrushAdjustmentParams('dodge', {
    ...settings,
    range: 'shadows',
  }), { shadows: 18 })
  assert.deepEqual(retouchBrushAdjustmentParams('burn', {
    ...settings,
    range: 'highlights',
  }), { highlights: -18 })
})

test('desaturating sponge and non-adjustment tools map correctly', () => {
  assert.deepEqual(retouchBrushAdjustmentParams('sponge', {
    ...settings,
    saturate: false,
  }), { saturation: -25 })
  assert.equal(retouchBrushAdjustmentParams('heal', settings), null)
})
