import assert from 'node:assert/strict'
import test from 'node:test'

import {
  applyPhotographicAdjustments,
  hasPhotographicAdjustments,
} from './photoAdjustments.ts'

function pixel(r: number, g: number, b: number) {
  return { data: new Uint8ClampedArray([r, g, b, 255]) } as ImageData
}

test('new tonal and color controls participate in adjustment identity', () => {
  assert.equal(hasPhotographicAdjustments({}), false)
  assert.equal(hasPhotographicAdjustments({ highlights: 1 }), true)
  assert.equal(hasPhotographicAdjustments({ hue: 1 }), true)
  assert.equal(hasPhotographicAdjustments({ vibrance: 1 }), true)
  assert.equal(
    hasPhotographicAdjustments({
      curve: {
        rgb: [[0, 0], [0.5, 0.4], [1, 1]],
        red: [[0, 0], [1, 1]],
        green: [[0, 0], [1, 1]],
        blue: [[0, 0], [1, 1]],
      },
    }),
    true,
  )
  assert.equal(hasPhotographicAdjustments({ dehaze: 1 }), true)
})

test('highlight adjustment is weighted toward bright pixels', () => {
  const dark = pixel(40, 40, 40)
  const bright = pixel(220, 220, 220)
  applyPhotographicAdjustments(dark, { highlights: 100 })
  applyPhotographicAdjustments(bright, { highlights: 100 })
  assert.ok(bright.data[0] - 220 > dark.data[0] - 40)
})

test('hue adjustment rotates color while retaining saturation', () => {
  const red = pixel(255, 0, 0)
  applyPhotographicAdjustments(red, { hue: 120 })
  assert.ok(red.data[1] > 240)
  assert.ok(red.data[0] < 15)
  assert.ok(red.data[2] < 15)
})

test('vibrance favours muted colors and a master curve remaps channels', () => {
  const muted = pixel(150, 120, 110)
  const originalSpread = muted.data[0] - muted.data[2]
  applyPhotographicAdjustments(muted, {
    vibrance: 100,
    curve: {
      rgb: [[0, 0], [0.25, 0.18], [0.5, 0.48], [0.75, 0.82], [1, 1]],
      red: [[0, 0], [1, 1]],
      green: [[0, 0], [1, 1]],
      blue: [[0, 0], [1, 1]],
    },
  })
  assert.ok(muted.data[0] - muted.data[2] > originalSpread)
  assert.notEqual(muted.data[0], 150)
})
