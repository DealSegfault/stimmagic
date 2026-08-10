import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { seamlessPatch } from './seamlessPatch.ts'
import initSeamlessPatchWasm, {
  seamless_patch as seamlessPatchWasm,
} from './seamlessPatchWasm/seamlessPatchWasm.js'

test('the production WASM solver matches the multiscale reference', async () => {
  const width = 65
  const height = 61
  const pixels = width * height
  const source = new Uint8ClampedArray(pixels * 4)
  const destination = new Uint8ClampedArray(pixels * 4)
  const mask = new Uint8ClampedArray(pixels)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const pixel = y * width + x
      const rgba = pixel * 4
      source.set([(x * 7 + y * 3) & 255, (x * 2 + y * 5) & 255, (x + y * 11) & 255, 255], rgba)
      destination.set([70 + ((x + y) & 15), 105 + ((x * 3) & 15), 145 + ((y * 3) & 15), 255], rgba)
      if (x >= 7 && x < 58 && y >= 6 && y < 55) mask[pixel] = 255
    }
  }

  const wasmBytes = await readFile(new URL(
    './seamlessPatchWasm/seamlessPatchWasm_bg.wasm',
    import.meta.url,
  ))
  await initSeamlessPatchWasm({ module_or_path: wasmBytes })
  const expected = seamlessPatch(source, destination, mask, width, height)
  const actual = seamlessPatchWasm(source, destination, mask, width, height)

  assert.equal(actual.length, expected.length)
  let maxDifference = 0
  for (let index = 0; index < actual.length; index++) {
    maxDifference = Math.max(maxDifference, Math.abs(actual[index] - expected[index]))
  }
  assert.ok(maxDifference <= 1, `maximum channel difference was ${maxDifference}`)
})
