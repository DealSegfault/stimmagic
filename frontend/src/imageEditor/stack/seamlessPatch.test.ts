import assert from 'node:assert/strict'
import test from 'node:test'

import { seamlessPatch } from './seamlessPatch.ts'

function rgba(
  width: number,
  height: number,
  colorAt: (x: number, y: number) => [number, number, number, number?],
): Uint8ClampedArray {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const [r, g, b, a = 255] = colorAt(x, y)
      const offset = (y * width + x) * 4
      data.set([r, g, b, a], offset)
    }
  }
  return data
}

const channelAt = (
  data: Uint8ClampedArray,
  width: number,
  x: number,
  y: number,
  channel = 0,
) => data[(y * width + x) * 4 + channel]

test('a hard patch reconstructs to the destination boundary without alpha feathering', () => {
  const width = 11
  const height = 11
  const source = rgba(width, height, (x, y) => {
    const texture = (x + y) % 2 === 0 ? 24 : -24
    return [190 + texture, 190 + texture, 190 + texture]
  })
  const destination = rgba(width, height, () => [55, 55, 55])
  const mask = new Uint8ClampedArray(width * height)
  for (let y = 2; y <= 8; y++) {
    for (let x = 2; x <= 8; x++) mask[y * width + x] = 255
  }

  const result = seamlessPatch(source, destination, mask, width, height)

  // Pixels outside the selected solve domain are inviolable.
  assert.equal(channelAt(result, width, 1, 5), 55)
  // Donor texture survives, but its 190-level illumination does not get pasted
  // onto a 55-level destination.
  const a = channelAt(result, width, 5, 5)
  const b = channelAt(result, width, 6, 5)
  assert.ok(Math.abs(a - b) > 25, 'donor texture should survive reconstruction')
  assert.ok((a + b) / 2 < 100, 'destination illumination should anchor the patch')
  assert.equal(channelAt(result, width, 5, 5, 3), 255)
})

test('the solve removes a donor color cast across the patch, not just at its edge', () => {
  const width = 13
  const height = 9
  const source = rgba(width, height, (x) => [170 + (x % 3) * 8, 80, 60])
  const destination = rgba(width, height, (x) => [45 + x * 2, 100 + x, 145 + x])
  const mask = new Uint8ClampedArray(width * height)
  for (let y = 2; y <= 6; y++) {
    for (let x = 2; x <= 10; x++) mask[y * width + x] = 255
  }

  const result = seamlessPatch(source, destination, mask, width, height)
  const center = [0, 1, 2].map(channel => channelAt(result, width, 6, 4, channel))

  assert.ok(center[0] < 100, 'red cast should adapt to the destination')
  assert.ok(center[1] > 85, 'green should reconstruct from destination boundary conditions')
  assert.ok(center[2] > 120, 'blue should reconstruct from destination boundary conditions')
})

test('fractional selection alpha is honored only at final compositing', () => {
  const width = 5
  const height = 5
  const source = rgba(width, height, (x) => [180 + x * 5, 180, 180])
  const destination = rgba(width, height, () => [40, 40, 40])
  const hardMask = new Uint8ClampedArray(width * height)
  const softMask = new Uint8ClampedArray(width * height)
  hardMask[2 * width + 2] = 255
  softMask[2 * width + 2] = 128

  const hard = seamlessPatch(source, destination, hardMask, width, height)
  const soft = seamlessPatch(source, destination, softMask, width, height)
  const hardValue = channelAt(hard, width, 2, 2)
  const softValue = channelAt(soft, width, 2, 2)

  assert.ok(Math.abs(softValue - (hardValue + 40) / 2) <= 1)
})

test('the solver is deterministic', () => {
  const width = 9
  const height = 9
  const source = rgba(width, height, (x, y) => [x * 17, y * 19, (x + y) * 9])
  const destination = rgba(width, height, (x, y) => [80 + x, 90 + y, 100])
  const mask = new Uint8ClampedArray(width * height)
  for (let y = 2; y < 7; y++) {
    for (let x = 2; x < 7; x++) mask[y * width + x] = 255
  }

  assert.deepEqual(
    seamlessPatch(source, destination, mask, width, height),
    seamlessPatch(source, destination, mask, width, height),
  )
})
