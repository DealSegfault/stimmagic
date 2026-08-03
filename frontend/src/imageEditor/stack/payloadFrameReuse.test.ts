import assert from 'node:assert/strict'
import test from 'node:test'

import { canReusePositionedPayload } from './positionedPayload.ts'

const IDENTITY = [1, 0, 0, 1, 0, 0] as const

test('a top-left compact payload still expands onto the full stage', () => {
  const compactMask = { width: 896, height: 520 } as CanvasImageSource
  assert.equal(
    canReusePositionedPayload(compactMask, [...IDENTITY], 896, 1152),
    false,
  )
})

test('an identity-positioned full-frame payload can be reused', () => {
  const fullMask = { width: 896, height: 1152 } as CanvasImageSource
  assert.equal(
    canReusePositionedPayload(fullMask, [...IDENTITY], 896, 1152),
    true,
  )
})

test('a transformed payload always needs a stage canvas', () => {
  const fullMask = { width: 896, height: 1152 } as CanvasImageSource
  assert.equal(
    canReusePositionedPayload(fullMask, [1, 0, 0, 1, 3, 0], 896, 1152),
    false,
  )
})

test('decoded image dimensions take precedence over element attributes', () => {
  const image = {
    naturalWidth: 896,
    naturalHeight: 520,
    width: 896,
    height: 1152,
  } as unknown as CanvasImageSource
  assert.equal(
    canReusePositionedPayload(image, [...IDENTITY], 896, 1152),
    false,
  )
})
