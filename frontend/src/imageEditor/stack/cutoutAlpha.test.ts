import test from 'node:test'
import assert from 'node:assert/strict'

import { cutoutAlpha } from './cutoutAlpha.ts'

test('the matte multiplies the input alpha rather than replacing it', () => {
  const input = new Uint8ClampedArray([255, 128, 0, 255])
  const matte = new Uint8ClampedArray([255, 255, 255, 0])
  assert.deepEqual(
    cutoutAlpha(input, matte, 4, 1, 0, 1),
    new Uint8ClampedArray([255, 128, 0, 0]),
  )
})

test('a soft model matte keeps its softness', () => {
  const input = new Uint8ClampedArray([255, 255])
  const matte = new Uint8ClampedArray([64, 192])
  const output = cutoutAlpha(input, matte, 2, 1, 0, 1)
  assert.equal(output[0], 64)
  assert.equal(output[1], 192)
})

test('opacity backs the cut off toward the original image', () => {
  const input = new Uint8ClampedArray([255])
  const matte = new Uint8ClampedArray([0])
  assert.equal(cutoutAlpha(input, matte, 1, 1, 0, 0)[0], 255)
  assert.equal(cutoutAlpha(input, matte, 1, 1, 0, 0.5)[0], 128)
  assert.equal(cutoutAlpha(input, matte, 1, 1, 0, 1)[0], 0)
})

test('feather softens the matte edge without inventing coverage', () => {
  const input = new Uint8ClampedArray([255, 255, 255, 255, 255, 255, 255])
  const matte = new Uint8ClampedArray([0, 0, 255, 255, 255, 0, 0])
  const output = cutoutAlpha(input, matte, 7, 1, 1, 1)
  assert.ok(output[2] > 0 && output[2] < 255)
  assert.ok(output[3] > output[2])
})
