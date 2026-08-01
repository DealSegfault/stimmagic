import assert from 'node:assert/strict'
import test from 'node:test'

import { morphSelectionPixels } from './selectionMorphology.ts'

function alphaMask(rows: string[]): Uint8ClampedArray {
  const pixels = new Uint8ClampedArray(rows.length * rows[0].length * 4)
  rows.join('').split('').forEach((value, index) => {
    pixels[index * 4 + 3] = value === '#' ? 255 : 0
  })
  return pixels
}

function alphaRows(pixels: Uint8ClampedArray, width: number): string[] {
  const rows: string[] = []
  for (let y = 0; y < pixels.length / 4 / width; y++) {
    let row = ''
    for (let x = 0; x < width; x++) {
      row += pixels[(y * width + x) * 4 + 3] > 127 ? '#' : '.'
    }
    rows.push(row)
  }
  return rows
}

test('positive pixels expand a selection on every edge', () => {
  const pixels = alphaMask([
    '.....',
    '.....',
    '..#..',
    '.....',
    '.....',
  ])
  morphSelectionPixels(pixels, 5, 5, 1)
  assert.deepEqual(alphaRows(pixels, 5), [
    '.....',
    '.###.',
    '.###.',
    '.###.',
    '.....',
  ])
})

test('negative pixels contract a selection and treat the frame edge as empty', () => {
  const pixels = alphaMask([
    '#####',
    '#####',
    '#####',
    '#####',
    '#####',
  ])
  morphSelectionPixels(pixels, 5, 5, -1)
  assert.deepEqual(alphaRows(pixels, 5), [
    '.....',
    '.###.',
    '.###.',
    '.###.',
    '.....',
  ])
})

test('a contraction can empty a small selection', () => {
  const pixels = alphaMask([
    '.....',
    '.###.',
    '.###.',
    '.###.',
    '.....',
  ])
  morphSelectionPixels(pixels, 5, 5, -2)
  assert.deepEqual(alphaRows(pixels, 5), [
    '.....',
    '.....',
    '.....',
    '.....',
    '.....',
  ])
})
