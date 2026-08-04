import assert from 'node:assert/strict'
import test from 'node:test'

import { captureAdjustmentScope } from './adjustmentScope.ts'
import type { GradientMask } from './types.ts'

test('Adjust activation snapshots matching gradient geometry before later housekeeping', () => {
  const selection = { pixels: [1, 2, 3] }
  const gradient: GradientMask = {
    kind: 'radial', cx: 20, cy: 30, rx: 10, ry: 12, feather: 60, invert: false,
  }
  const captured = captureAdjustmentScope(
    selection,
    source => ({ pixels: [...source.pixels] }),
    gradient,
    'frame-a',
    'frame-a',
  )

  gradient.cx = 999

  assert.deepEqual(captured, {
    kind: 'gradient',
    gradient: {
      kind: 'radial', cx: 20, cy: 30, rx: 10, ry: 12, feather: 60, invert: false,
    },
  })
})

test('Adjust activation keeps raster scope when gradient geometry is stale', () => {
  const selection = { selected: true }
  const captured = captureAdjustmentScope(
    selection,
    source => ({ ...source }),
    {
      kind: 'linear', x1: 0, y1: 0, x2: 20, y2: 20, softness: 55,
    },
    'old-frame',
    'current-frame',
  )
  selection.selected = false

  assert.deepEqual(captured, {
    kind: 'raster',
    mask: { selected: true },
  })
})

test('Adjust activation has no scope when no selection is active', () => {
  assert.equal(
    captureAdjustmentScope(null, value => value, null, null, null),
    null,
  )
})

test('Adjust activation carries semantic identity while the selection is that gesture', () => {
  const captured = captureAdjustmentScope(
    { selected: true },
    source => ({ ...source }),
    null,
    null,
    'frame-a',
    { prompt: 'sky' },
    'frame-a',
  )
  assert.deepEqual(captured, {
    kind: 'raster',
    mask: { selected: true },
    semantic: { prompt: 'sky' },
  })
})

test('Adjust activation drops semantic identity pinned to another frame', () => {
  const captured = captureAdjustmentScope(
    { selected: true },
    source => ({ ...source }),
    null,
    null,
    'current-frame',
    { intent: 'subject' },
    'old-frame',
  )
  assert.deepEqual(captured, { kind: 'raster', mask: { selected: true } })
})
