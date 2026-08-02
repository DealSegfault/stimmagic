import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clampViewportPan,
  isZoomWheelGesture,
  panForDragDelta,
  panForWheelDelta,
  panForZoomAtPoint,
  stabilizeWacomWheelDelta,
  wheelPanDelta,
} from '../ported/viewportNavigation.ts'

test('fit view can move throughout the workspace while keeping a visible grip', () => {
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
      { x: 1000, y: -1000 },
      1,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: 736, y: -536 },
  )
})

test('pan clamps independently on each viewport axis', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: 2000, y: 1000 },
      2,
      { width: 800, height: 300 },
      { width: 800, height: 600 },
    ),
    { x: 1136, y: 536 },
  )
})

test('drag reversal responds immediately after pushing beyond a pan bound', () => {
  const content = { width: 800, height: 600 }
  const viewport = { width: 800, height: 600 }

  const atBottomEdge = panForDragDelta(
    { x: 0, y: 530 },
    { x: 0, y: 100 },
    1,
    content,
    viewport,
  )
  assert.deepEqual(atBottomEdge, { x: 0, y: 536 })

  assert.deepEqual(
    panForDragDelta(
      atBottomEdge,
      { x: 0, y: -5 },
      1,
      content,
      viewport,
    ),
    { x: 0, y: 531 },
  )
})

test('zoomed-out content can still be pushed around without losing it', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: -500, y: 500 },
      0.5,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: -500, y: 386 },
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

test('Wacom wheel panning is slowed and large spikes are bounded per event', () => {
  assert.deepEqual(
    stabilizeWacomWheelDelta({ x: 10, y: -20 }),
    { x: 1.2, y: -2.4 },
  )
  assert.deepEqual(
    stabilizeWacomWheelDelta({ x: 200, y: -200 }),
    { x: 4, y: -4 },
  )
})
