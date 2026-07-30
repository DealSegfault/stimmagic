import assert from 'node:assert/strict'
import test from 'node:test'

import { advanceStroke, getStrokePoints } from '../ported/strokeSpacing.ts'

test('sub-spacing pointer events do not create extra brush dabs', () => {
  assert.deepEqual(getStrokePoints(0, 0, 2, 0, 5), [])
  assert.deepEqual(getStrokePoints(0, 0, 4.99, 0, 5), [])
})

test('stroke points are placed at the requested spatial interval', () => {
  assert.deepEqual(getStrokePoints(0, 0, 12, 0, 5), [
    { x: 5, y: 0 },
    { x: 10, y: 0 },
  ])
})

test('spacing is independent of how much path remains after the last full interval', () => {
  const points = getStrokePoints(0, 0, 11, 0, 3)
  assert.deepEqual(points, [
    { x: 3, y: 0 },
    { x: 6, y: 0 },
    { x: 9, y: 0 },
  ])
})

test('the same path produces the same dabs at dense and sparse event rates', () => {
  function sample(eventXs: number[]) {
    let lastDab: { x: number; y: number } | null = null
    const dabs: Array<{ x: number; y: number }> = []
    for (const x of eventXs) {
      const advanced = advanceStroke(lastDab, { x, y: 0 }, 5)
      lastDab = advanced.lastDab
      dabs.push(...advanced.points)
    }
    return dabs
  }

  assert.deepEqual(
    sample([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 20]),
    sample([0, 10, 20]),
  )
})
