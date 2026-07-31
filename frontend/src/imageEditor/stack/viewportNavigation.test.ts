import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clampViewportPan,
  panForWheelDelta,
  panForZoomAtPoint,
} from '../ported/viewportNavigation.ts'

test('fit view is always centred', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: 120, y: -80 },
      1,
      { width: 800, height: 600 },
      { width: 800, height: 600 },
    ),
    { x: 0, y: 0 },
  )
})

test('pan clamps independently on each viewport axis', () => {
  assert.deepEqual(
    clampViewportPan(
      { x: 500, y: 500 },
      2,
      { width: 800, height: 300 },
      { width: 800, height: 600 },
    ),
    { x: 400, y: 0 },
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
