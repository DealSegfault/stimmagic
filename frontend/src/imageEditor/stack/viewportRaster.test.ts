import assert from 'node:assert/strict'
import test from 'node:test'
import {
  fittedBrushScale,
  overlayBackingSize,
  zoomedBrushSize,
} from './viewportRaster.ts'

test('overlay backing size is fitted-view sized and density capped', () => {
  assert.deepEqual(overlayBackingSize(800, 600, 1), { width: 800, height: 600 })
  assert.deepEqual(overlayBackingSize(800, 600, 2), { width: 1600, height: 1200 })
  assert.deepEqual(overlayBackingSize(800, 600, 3), { width: 1600, height: 1200 })
})

test('brush footprint stays fixed in source space while its screen ring zooms', () => {
  const sourceWidth = 4000
  const fittedWidth = 1000
  const brushSize = 40

  assert.equal(fittedBrushScale(sourceWidth, fittedWidth, 1), 4)
  assert.equal(fittedBrushScale(sourceWidth, fittedWidth * 4, 4), 4)
  assert.equal(zoomedBrushSize(brushSize, 1), 40)
  assert.equal(zoomedBrushSize(brushSize, 4), 160)
})
