import assert from 'node:assert/strict'
import test from 'node:test'

import {
  claimTabletWheelGesture,
  createTabletWheelGestureState,
  noteTabletPointForWheelGesture,
  releaseTabletWheelGesture,
} from '../../composables/tabletWheelGesture.ts'

test('Wacom wheel gesture stays claimed after tablet samples stop', () => {
  const state = createTabletWheelGestureState()
  noteTabletPointForWheelGesture(state, 'down', 1_000)

  assert.equal(claimTabletWheelGesture(state, 1_100, true, false), true)
  assert.equal(claimTabletWheelGesture(state, 9_000, true, false), true)
})

test('ordinary wheels do not inherit an old or parked pen', () => {
  const state = createTabletWheelGestureState()
  noteTabletPointForWheelGesture(state, 'hover', 1_000)

  assert.equal(claimTabletWheelGesture(state, 3_001, true, false), false)
  assert.equal(claimTabletWheelGesture(state, 1_100, false, false), false)
  assert.equal(claimTabletWheelGesture(state, 1_100, true, true), false)
})

test('tablet input resuming releases the Wacom wheel gesture', () => {
  const state = createTabletWheelGestureState()
  noteTabletPointForWheelGesture(state, 'down', 1_000)
  assert.equal(claimTabletWheelGesture(state, 1_100, true, false), true)

  noteTabletPointForWheelGesture(state, 'up', 1_200)
  assert.equal(state.latched, false)
  assert.equal(claimTabletWheelGesture(state, 1_250, true, false), false)

  noteTabletPointForWheelGesture(state, 'down', 1_300)
  assert.equal(claimTabletWheelGesture(state, 1_350, true, false), true)
  releaseTabletWheelGesture(state)
  assert.equal(state.latched, false)
})
