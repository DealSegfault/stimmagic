import assert from 'node:assert/strict'
import test from 'node:test'
import {
  FEATHER_SLIDER_MAX,
  MAX_FEATHER_PX,
  featherPxFromSlider,
  featherSliderFromPx,
} from './featherScale.ts'

test('feather scale preserves both endpoints', () => {
  assert.equal(featherPxFromSlider(0), 0)
  assert.equal(featherPxFromSlider(FEATHER_SLIDER_MAX), MAX_FEATHER_PX)
})

test('feather scale gives small radii useful slider travel', () => {
  assert.ok(featherSliderFromPx(48) > FEATHER_SLIDER_MAX * 0.25)
  assert.ok(featherSliderFromPx(48) < FEATHER_SLIDER_MAX * 0.5)
})

test('feather scale round-trips representative source-pixel values', () => {
  for (const pixels of [0, 4, 12, 48, 100, 250, 500, 1000]) {
    assert.ok(Math.abs(featherPxFromSlider(featherSliderFromPx(pixels)) - pixels) <= 1)
  }
})
