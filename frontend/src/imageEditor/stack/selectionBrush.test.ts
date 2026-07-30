import assert from 'node:assert/strict'
import test from 'node:test'
import { applySelectionBrushSegment } from './selectionBrush.ts'

function blankMask(width: number, height: number, alpha = 0) {
  const pixels = new Uint8ClampedArray(width * height * 4)
  for (let index = 3; index < pixels.length; index += 4) pixels[index] = alpha
  return pixels
}

test('painting the same selection-brush segment twice does not build opacity', () => {
  const pixels = blankMask(20, 12)
  const args = [
    pixels,
    20,
    12,
    { x: 3, y: 6 },
    { x: 17, y: 6 },
    5,
    0.6,
    'add',
  ] as const

  applySelectionBrushSegment(...args)
  const firstPass = pixels.slice()
  applySelectionBrushSegment(...args)

  assert.deepEqual(pixels, firstPass)
  assert.equal(pixels[(6 * 20 + 10) * 4 + 3], 255)
  assert.ok(pixels[(2 * 20 + 10) * 4 + 3] > 0)
  assert.ok(pixels[(2 * 20 + 10) * 4 + 3] < 255)
})

test('erasing the same selection-brush segment twice does not build removal', () => {
  const pixels = blankMask(20, 12, 255)
  const args = [
    pixels,
    20,
    12,
    { x: 3, y: 6 },
    { x: 17, y: 6 },
    5,
    0.6,
    'subtract',
  ] as const

  applySelectionBrushSegment(...args)
  const firstPass = pixels.slice()
  applySelectionBrushSegment(...args)

  assert.deepEqual(pixels, firstPass)
  assert.equal(pixels[(6 * 20 + 10) * 4 + 3], 0)
  assert.ok(pixels[(2 * 20 + 10) * 4 + 3] > 0)
  assert.ok(pixels[(2 * 20 + 10) * 4 + 3] < 255)
})
