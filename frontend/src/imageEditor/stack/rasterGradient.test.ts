import assert from 'node:assert/strict'
import test from 'node:test'

import {
  constrainedGradientEnd,
  rasterGradientStops,
  reflectedGradientStops,
  sampleRasterGradient,
} from './rasterGradient.ts'

const paint = {
  type: 'gradient' as const,
  direction: 'horizontal' as const,
  colors: [
    { r: 0, g: 0, b: 0, a: 1 },
    { r: 100, g: 50, b: 0, a: 0.5 },
    { r: 200, g: 100, b: 0, a: 0 },
  ],
}

test('raster gradient stops are evenly spaced and reversible', () => {
  assert.deepEqual(rasterGradientStops(paint).map(stop => stop.offset), [0, 0.5, 1])
  assert.deepEqual(rasterGradientStops(paint, true).map(stop => stop.color.r), [200, 100, 0])
})

test('reflected gradients mirror the ramp around its start point', () => {
  const stops = reflectedGradientStops(paint)
  assert.deepEqual(stops.map(stop => stop.offset), [0, 0.25, 0.5, 0.75, 1])
  assert.deepEqual(stops.map(stop => stop.color.r), [200, 100, 0, 100, 200])
})

test('shift snapping preserves length and chooses the nearest 45 degree angle', () => {
  const end = constrainedGradientEnd({ x: 4, y: 8 }, { x: 13, y: 11 }, true)
  assert.ok(Math.abs(Math.hypot(end.x - 4, end.y - 8) - Math.hypot(9, 3)) < 1e-9)
  assert.ok(Math.abs(end.y - 8) < 1e-9)
})

test('diamond spectrum sampling interpolates color and alpha', () => {
  assert.deepEqual(sampleRasterGradient(rasterGradientStops(paint), 0.25), {
    r: 50, g: 25, b: 0, a: 0.75,
  })
})
