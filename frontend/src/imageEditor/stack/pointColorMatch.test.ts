import assert from 'node:assert/strict'
import test from 'node:test'

import { hexToHsl, hslToHex, matchShifts } from './pointColorMatch.ts'
import { applyPhotographicAdjustments } from './photoAdjustments.ts'

test('hex parsing round-trips through HSL', () => {
  assert.equal(hexToHsl('nonsense'), null)
  assert.equal(hexToHsl('#12345'), null)
  for (const hex of ['#c1442e', '#0d9488', '#ffffff', '#000000', '#808080']) {
    const hsl = hexToHsl(hex)
    assert.ok(hsl)
    assert.equal(hslToHex(hsl), hex)
  }
})

test('match computes shifts that land the picked color on the target', () => {
  const picked = hexToHsl('#c1442e')!
  const target = hexToHsl('#e03a2a')!
  const shifts = matchShifts(picked, target)

  // Apply through the real renderer at the reference color itself: a pixel of
  // exactly the picked color must come out as (approximately) the target.
  const pixel = {
    data: new Uint8ClampedArray([0xc1, 0x44, 0x2e, 255]),
  } as ImageData
  applyPhotographicAdjustments(pixel, {
    pointHue: picked.hue,
    pointSat: picked.sat,
    pointLum: picked.lum,
    ...shifts,
    pointRange: 50,
  })
  assert.ok(Math.abs(pixel.data[0] - 0xe0) <= 6, `red ${pixel.data[0]}`)
  assert.ok(Math.abs(pixel.data[1] - 0x3a) <= 6, `green ${pixel.data[1]}`)
  assert.ok(Math.abs(pixel.data[2] - 0x2a) <= 6, `blue ${pixel.data[2]}`)
})

test('match takes the short way around the hue wheel', () => {
  const shifts = matchShifts(
    { hue: 350, sat: 60, lum: 50 },
    { hue: 10, sat: 60, lum: 50 },
  )
  assert.equal(shifts.pointHueShift, 20)
})
