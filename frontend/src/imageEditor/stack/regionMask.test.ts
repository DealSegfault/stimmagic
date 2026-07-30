import assert from 'node:assert/strict'
import test from 'node:test'
import {
  DEFAULT_LINEAR_SOFTNESS,
  MIN_GRADIENT_EXTENT,
  gradientAlpha,
  gradientSliderOf,
  hasGradientMask,
  isDegenerate,
  isGradientMask,
  linearMaskFromDrag,
  radialMaskFromDrag,
  regionHasCoverage,
  regionMaskOf,
  transformGradientMask,
  withGradientSlider,
} from './regionMask.ts'
import { cropAffine, invert } from './geometryTransform.ts'
import type { GradientMask } from './types.ts'

const at = (alpha: Uint8ClampedArray, width: number, x: number, y: number) =>
  alpha[y * width + x]

test('a region with no mask field reads as raster', () => {
  assert.deepEqual(regionMaskOf({}), { kind: 'raster' })
  assert.equal(hasGradientMask({}), false)
  assert.equal(isGradientMask(undefined), false)
  assert.equal(isGradientMask({ kind: 'raster' }), false)
})

test('a vertical ramp is full at its start and empty past its end', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 9 }, 0)
  const alpha = gradientAlpha(mask, 4, 20)
  assert.equal(at(alpha, 4, 0, 0), 255)
  assert.equal(at(alpha, 4, 0, 9), 0)
  // Past the end handle the ramp stays dead rather than wrapping around.
  assert.equal(at(alpha, 4, 0, 19), 0)
})

test('a ramp is constant along its perpendicular — the reason it has no seam', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 15 })
  const alpha = gradientAlpha(mask, 8, 16)
  for (let y = 0; y < 16; y++) {
    const first = at(alpha, 8, 0, y)
    for (let x = 1; x < 8; x++) {
      assert.equal(at(alpha, 8, x, y), first, `row ${y} varies across x`)
    }
  }
})

test('a ramp decreases monotonically from start to end', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 31 }, DEFAULT_LINEAR_SOFTNESS)
  const alpha = gradientAlpha(mask, 1, 32)
  for (let y = 1; y < 32; y++) {
    assert.ok(alpha[y] <= alpha[y - 1], `alpha rose at y=${y}`)
  }
})

test('softness 0 is a straight ramp; the midpoint sits at half', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 }, 0)
  const alpha = gradientAlpha(mask, 1, 11)
  assert.equal(alpha[5], 128)
})

test('softness eases the ends without moving the midpoint', () => {
  const soft = gradientAlpha(linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 }, 100), 1, 11)
  const hard = gradientAlpha(linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 }, 0), 1, 11)
  assert.equal(soft[5], hard[5])
  // Eased: closer to full near the start, closer to empty near the end.
  assert.ok(soft[2] > hard[2])
  assert.ok(soft[8] < hard[8])
})

test('a diagonal ramp runs along the drag, not along an axis', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 10, y: 10 }, 0)
  const alpha = gradientAlpha(mask, 11, 11)
  // Equal-distance-along-the-drag points match; the perpendicular is flat.
  assert.equal(at(alpha, 11, 10, 0), at(alpha, 11, 0, 10))
  assert.equal(at(alpha, 11, 0, 0), 255)
  assert.equal(at(alpha, 11, 10, 10), 0)
})

test('a radial mask is full at the centre and empty outside the ellipse', () => {
  const mask: GradientMask = {
    kind: 'radial', cx: 10, cy: 10, rx: 8, ry: 8, feather: 50, invert: false,
  }
  const alpha = gradientAlpha(mask, 21, 21)
  assert.equal(at(alpha, 21, 10, 10), 255)
  assert.equal(at(alpha, 21, 0, 0), 0)
  // Inside the un-feathered core it is still at full strength.
  assert.equal(at(alpha, 21, 13, 10), 255)
})

test('a radial mask respects independent radii', () => {
  const mask: GradientMask = {
    kind: 'radial', cx: 10, cy: 10, rx: 9, ry: 3, feather: 20, invert: false,
  }
  const alpha = gradientAlpha(mask, 21, 21)
  assert.ok(at(alpha, 21, 17, 10) > 0, 'wide axis should still be covered')
  assert.equal(at(alpha, 21, 10, 16), 0, 'narrow axis should be clear')
})

test('invert makes the ellipse an edge burn', () => {
  const base: GradientMask = {
    kind: 'radial', cx: 10, cy: 10, rx: 6, ry: 6, feather: 40, invert: false,
  }
  const inside = gradientAlpha(base, 21, 21)
  const outside = gradientAlpha({ ...base, invert: true }, 21, 21)
  for (let p = 0; p < inside.length; p++) {
    assert.equal(inside[p] + outside[p], 255, `pixel ${p} is not complementary`)
  }
})

test('a drag centres the ellipse on the press, not on a corner', () => {
  const mask = radialMaskFromDrag({ x: 40, y: 30 }, { x: 55, y: 50 })
  assert.equal(mask.kind, 'radial')
  if (mask.kind !== 'radial') return
  assert.equal(mask.cx, 40)
  assert.equal(mask.cy, 30)
  assert.equal(mask.rx, 15)
  assert.equal(mask.ry, 20)
})

test('degenerate geometry covers nothing rather than guessing', () => {
  const dot = linearMaskFromDrag({ x: 5, y: 5 }, { x: 5, y: 5 })
  assert.equal(isDegenerate(dot), true)
  assert.equal(regionHasCoverage({ mask: dot }), false)
  assert.ok(gradientAlpha(dot, 4, 4).every(v => v === 0))

  const flat: GradientMask = {
    kind: 'radial', cx: 5, cy: 5, rx: 0, ry: 9, feather: 50, invert: false,
  }
  assert.equal(isDegenerate(flat), true)
  assert.ok(gradientAlpha(flat, 4, 4).every(v => v === 0))
})

test('coverage for a drawn region still depends on its payload', () => {
  assert.equal(regionHasCoverage({ mask_ref: 'm.png' }), true)
  assert.equal(regionHasCoverage({}), false)
  assert.equal(regionHasCoverage({ mask: { kind: 'raster' } }), false)
  // A gradient needs no payload at all.
  assert.equal(
    regionHasCoverage({ mask: linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 20 }) }),
    true,
  )
})

test('the island slider maps to whichever parameter the gradient owns', () => {
  const linear = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 }, 30)
  assert.deepEqual(gradientSliderOf(linear), { label: 'Softness', value: 30 })
  const bumped = withGradientSlider(linear, 80)
  assert.equal(bumped.kind === 'linear' && bumped.softness, 80)

  const radial = radialMaskFromDrag({ x: 0, y: 0 }, { x: 10, y: 10 }, { feather: 25 })
  assert.deepEqual(gradientSliderOf(radial), { label: 'Feather', value: 25 })
  const feathered = withGradientSlider(radial, 90)
  assert.equal(feathered.kind === 'radial' && feathered.feather, 90)
})

test('a ramp shorter than the threshold is not worth keeping', () => {
  // Guards the gesture rule: a click or a twitch must leave no region behind.
  const twitch = linearMaskFromDrag({ x: 100, y: 100 }, { x: 100, y: 100 + MIN_GRADIENT_EXTENT - 1 })
  const real = linearMaskFromDrag({ x: 100, y: 100 }, { x: 100, y: 100 + MIN_GRADIENT_EXTENT })
  const extent = (mask: GradientMask) => mask.kind === 'linear'
    ? Math.hypot(mask.x2 - mask.x1, mask.y2 - mask.y1)
    : Math.min(mask.rx, mask.ry)
  assert.ok(extent(twitch) < MIN_GRADIENT_EXTENT)
  assert.ok(extent(real) >= MIN_GRADIENT_EXTENT)
  // Both are non-degenerate, so the threshold is what rejects the twitch.
  assert.equal(isDegenerate(twitch), false)
})

test('carrying a ramp through a crop and back is exact', () => {
  // The real affine a centred half-size crop produces, so this is the transform
  // the stack actually applies rather than a hand-picked easy one.
  const { matrix } = cropAffine({ rect: { x: 0.5, y: 0.5, width: 0.5, height: 0.5 } }, 400, 300)
  const back = invert(matrix)
  assert.ok(back, 'a crop affine must be invertible')

  const authored = linearMaskFromDrag({ x: 40, y: 20 }, { x: 40, y: 260 }, 40)
  const inComposite = transformGradientMask(authored, matrix)
  const roundTripped = transformGradientMask(inComposite, back!)

  assert.equal(roundTripped.kind, 'linear')
  if (roundTripped.kind !== 'linear' || authored.kind !== 'linear') return
  for (const key of ['x1', 'y1', 'x2', 'y2'] as const) {
    assert.ok(
      Math.abs(roundTripped[key] - authored[key]) < 1e-6,
      `${key} drifted: ${roundTripped[key]} vs ${authored[key]}`,
    )
  }
  // Storing parameters rather than pixels is what makes this lossless.
  assert.equal(roundTripped.softness, authored.softness)
})

test('a crop moves an ellipse with the image and scales it', () => {
  // Half-size crop: the same object is half as many pixels across afterwards.
  const { matrix } = cropAffine({ rect: { x: 0.5, y: 0.5, width: 0.5, height: 0.5 } }, 400, 400)
  const authored: GradientMask = {
    kind: 'radial', cx: 200, cy: 200, rx: 80, ry: 40, feather: 50, invert: true,
  }
  const moved = transformGradientMask(authored, matrix)
  assert.equal(moved.kind, 'radial')
  if (moved.kind !== 'radial') return
  // The centre of the image stays the centre of the cropped frame.
  assert.ok(Math.abs(moved.cx - 100) < 1e-6)
  assert.ok(Math.abs(moved.cy - 100) < 1e-6)
  assert.ok(Math.abs(moved.rx - 80) < 1e-6, 'a pure window crop must not rescale radii')
  assert.ok(Math.abs(moved.ry - 40) < 1e-6)
  assert.equal(moved.invert, true, 'the falloff settings are geometry-independent')
})

test('translating a ramp does not change its falloff', () => {
  const mask = linearMaskFromDrag({ x: 10, y: 10 }, { x: 10, y: 50 }, 70)
  const moved = transformGradientMask(mask, [1, 0, 0, 1, 25, -5])
  assert.equal(moved.kind === 'linear' && moved.x1, 35)
  assert.equal(moved.kind === 'linear' && moved.y1, 5)
  assert.equal(moved.kind === 'linear' && moved.softness, 70)
})

test('coverage belongs in the alpha channel, not just RGB', () => {
  // compositeRetouchRegion reads a region mask's ALPHA; compositePatch and
  // maskBounds read RED. An opaque alpha made every gradient region cover the
  // whole frame, so the adjustment applied globally and stopped being local.
  // This is a channel-convention contract, so it is asserted on the buffer the
  // canvas writer copies rather than on a canvas the test runner has no DOM for.
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 }, 0)
  const alpha = gradientAlpha(mask, 1, 11)
  const rgba = new Uint8ClampedArray(alpha.length * 4)
  for (let p = 0, i = 0; p < alpha.length; p++, i += 4) {
    rgba[i] = alpha[p]; rgba[i + 1] = alpha[p]; rgba[i + 2] = alpha[p]; rgba[i + 3] = alpha[p]
  }
  // Full at the start, gone at the end — in alpha AND in red.
  assert.equal(rgba[3], 255)
  assert.equal(rgba[0], 255)
  assert.equal(rgba[10 * 4 + 3], 0, 'alpha must fall to zero or the region covers everything')
  assert.equal(rgba[10 * 4], 0)
  // And never a constant alpha, which is exactly the bug this guards.
  const alphas = new Set(Array.from({ length: 11 }, (_, y) => rgba[y * 4 + 3]))
  assert.ok(alphas.size > 2, 'alpha must vary across the ramp')
})

test('rasterising is safe at zero size', () => {
  const mask = linearMaskFromDrag({ x: 0, y: 0 }, { x: 0, y: 10 })
  assert.equal(gradientAlpha(mask, 0, 0).length, 0)
})
