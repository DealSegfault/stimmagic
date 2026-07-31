import test from 'node:test'
import assert from 'node:assert/strict'

import {
  antialiasMaskAlpha,
  createWandMaskAlpha,
  resizeMaskAlpha,
  rgbaDifference,
  srgbToLab,
} from './wandMask.ts'

const defaults = {
  threshold: 8,
  spread: 100,
  growPx: 0,
  featherPx: 0,
  antialias: false,
}

test('wand treats fully transparent pixels as one region regardless of hidden RGB', () => {
  const pixels = new Uint8ClampedArray([
    255, 0, 0, 0,
    0, 0, 255, 0,
    0, 255, 0, 255,
  ])

  assert.deepEqual(
    createWandMaskAlpha(pixels, 3, 1, 0, 0, defaults),
    new Uint8ClampedArray([255, 255, 0]),
  )
})

test('sRGB is compared in CIELAB distance', () => {
  const white = srgbToLab(255, 255, 255)
  const red = srgbToLab(255, 0, 0)
  assert.ok(Math.abs(white[0] - 100) < 0.01)
  assert.ok(Math.abs(red[0] - 54.29) < 0.02)
  assert.ok(Math.abs(red[1] - 80.81) < 0.02)
  assert.ok(Math.abs(red[2] - 69.89) < 0.02)

  const pixels = new Uint8ClampedArray([
    120, 120, 120, 255,
    100, 120, 100, 255,
  ])
  const target = [100, 100, 100, 255] as const
  assert.equal(rgbaDifference(pixels, 0, target), 8)
  assert.equal(rgbaDifference(pixels, 4, target), 14)
})

test('threshold 1 follows exact-match behavior', () => {
  const pixels = new Uint8ClampedArray([
    100, 100, 100, 255,
    101, 100, 100, 255,
  ])
  assert.deepEqual(
    createWandMaskAlpha(pixels, 2, 1, 0, 0, {
      ...defaults,
      threshold: 1,
    }),
    new Uint8ClampedArray([255, 0]),
  )
})

test('spread turns color similarity into partial mask opacity', () => {
  const pixels = new Uint8ClampedArray([
    0, 0, 0, 255,
    25, 25, 25, 255,
  ])

  const hard = createWandMaskAlpha(pixels, 2, 1, 0, 0, {
    ...defaults,
    threshold: 20,
  })
  const soft = createWandMaskAlpha(pixels, 2, 1, 0, 0, {
    ...defaults,
    threshold: 20,
    spread: 0,
  })

  assert.deepEqual(hard, new Uint8ClampedArray([255, 255]))
  assert.equal(soft[0], 255)
  assert.ok(soft[1] > 0 && soft[1] < 255)
})

test('grow and shrink resize a hard selection before edge treatment', () => {
  const center = new Uint8ClampedArray([
    0, 0, 0,
    0, 255, 0,
    0, 0, 0,
  ])
  assert.deepEqual(
    resizeMaskAlpha(center, 3, 3, 1),
    new Uint8ClampedArray(9).fill(255),
  )

  const solid = new Uint8ClampedArray(25).fill(255)
  assert.deepEqual(
    resizeMaskAlpha(solid, 5, 5, -1),
    new Uint8ClampedArray([
      0, 0, 0, 0, 0,
      0, 255, 255, 255, 0,
      0, 255, 255, 255, 0,
      0, 255, 255, 255, 0,
      0, 0, 0, 0, 0,
    ]),
  )
})

test('anti-alias smooths only mask boundaries', () => {
  const hard = new Uint8ClampedArray([
    0, 0, 0, 0, 0,
    0, 255, 255, 255, 0,
    0, 255, 255, 255, 0,
    0, 255, 255, 255, 0,
    0, 0, 0, 0, 0,
  ])
  const smoothed = antialiasMaskAlpha(hard, 5, 5)

  assert.equal(smoothed[12], 255, 'flat interior stays fully selected')
  assert.ok(smoothed[6] > 0 && smoothed[6] < 255, 'boundary becomes fractional')
  assert.ok(smoothed[1] > 0 && smoothed[1] < 255, 'coverage reaches outside the edge')
})
