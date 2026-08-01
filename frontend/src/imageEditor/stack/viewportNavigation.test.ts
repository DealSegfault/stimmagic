import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clampViewportPan,
  isZoomWheelGesture,
  panForWheelDelta,
  panForZoomAtPoint,
  wheelPanDelta,
} from '../ported/viewportNavigation.ts'

test('fit view retains bounded workspace slack for floating controls', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: 120, y: -80 },
      1,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: 120, y: -80 },
  )
  assert.deepEqual(
    clampViewportPan(
      { x: 500, y: -500 },
      1,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: 160, y: -150 },
  )
})

test('pan clamps independently on each viewport axis', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: 1000, y: 1000 },
      2,
      { width: 800, height: 300 },
      { width: 800, height: 600 },
    ),
    { x: 560, y: 150 },
  )
})

test('zoomed-out content can still be panned within workspace slack', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: -500, y: 500 },
      0.5,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: -160, y: 150 },
  )
})

test('zoom preserves the image point beneath the cursor', () => {
  assert.deepEqual(
    panForZoomAtPoint({ x: 0, y: 0 }, 1, 2, { x: 100, y: -50 }),
    { x: -100, y: 50 },
  )
})

test('two-axis wheel scrolling pans the canvas', () => {
  assert.deepEqual(
    panForWheelDelta({ x: 25, y: -10 }, { x: 12, y: -8 }),
    { x: 13, y: -2 },
  )
})

test('Lightroom-style zoom requires a pinch or keyboard modifier', () => {
  assert.equal(isZoomWheelGesture({ ctrlKey: false, metaKey: false }), false)
  assert.equal(isZoomWheelGesture({ ctrlKey: true, metaKey: false }), true)
  assert.equal(isZoomWheelGesture({ ctrlKey: false, metaKey: true }), true)
})

test('wheel and two-finger deltas normalize as pan input', () => {
  assert.deepEqual(
    wheelPanDelta({ x: 2.5, y: 7 }, 0, { width: 800, height: 600 }),
    { x: 2.5, y: 7 },
  )
  assert.deepEqual(
    wheelPanDelta({ x: 0, y: 3 }, 1, { width: 800, height: 600 }),
    { x: 0, y: 48 },
  )
})

test('shift-wheel pans horizontally like Lightroom', () => {
  assert.deepEqual(
    wheelPanDelta({ x: 0, y: 3 }, 1, { width: 800, height: 600 }, true),
    { x: 48, y: 0 },
  )
})
