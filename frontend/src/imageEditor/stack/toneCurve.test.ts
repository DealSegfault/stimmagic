import assert from 'node:assert/strict'
import test from 'node:test'

import {
  defaultToneCurve,
  isIdentityToneCurve,
  toneCurveChannelValue,
  toneCurvePointValue,
  toneCurveValueOf,
} from './toneCurve.ts'

test('the point curve has one current document shape with four channels', () => {
  assert.deepEqual(toneCurveValueOf(undefined), defaultToneCurve())
  assert.deepEqual(toneCurveValueOf([0, 0.5, 1]), defaultToneCurve())
  assert.equal(isIdentityToneCurve(defaultToneCurve()), true)
})

test('smooth interpolation passes through authored points without overshoot', () => {
  const points: [number, number][] = [[0, 0], [0.25, 0.15], [0.5, 0.5], [0.75, 0.85], [1, 1]]
  assert.ok(Math.abs(toneCurvePointValue(0.25, points) - 0.15) < 1e-6)
  assert.ok(Math.abs(toneCurvePointValue(0.75, points) - 0.85) < 1e-6)
  for (let index = 0; index <= 100; index++) {
    const value = toneCurvePointValue(index / 100, points)
    assert.ok(value >= 0 && value <= 1)
  }
})

test('master and channel curves compose independently', () => {
  const curve = defaultToneCurve()
  curve.rgb = [[0, 0], [0.5, 0.6], [1, 1]]
  curve.red = [[0, 0], [0.6, 0.75], [1, 1]]
  const red = toneCurveChannelValue(0.5, curve, 'red')
  const green = toneCurveChannelValue(0.5, curve, 'green')
  assert.ok(red > green)
  assert.ok(green > 0.5)
})
