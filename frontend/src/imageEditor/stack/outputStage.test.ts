import assert from 'node:assert/strict'
import test from 'node:test'

import {
  contributions, finalResolutionFor, outputDimensions, outputLabel, outputOf,
} from './outputStage.ts'
import type { OutputStage } from './types.ts'

const stage = (patch: Partial<OutputStage> = {}): OutputStage =>
  ({ enabled: true, method: 'photo', tool_id: null, params: {}, ...patch })

// -- the stage's arithmetic -------------------------------------------------

test('an absent output stage is off', () => {
  assert.equal(outputOf(undefined).enabled, false)
  assert.equal(outputOf(null).enabled, false)
  assert.deepEqual(outputOf(null).params, {})
})

test('off writes the working size unchanged', () => {
  const off = stage({ enabled: false, params: { scaleFactor: 4 } })
  assert.deepEqual(outputDimensions(off, 999, 501), { width: 999, height: 501 })
  assert.equal(outputLabel(off), '')
})

test('a scale factor multiplies the composite, it does not name a target', () => {
  // Expand changes the composite's size mid-stack, which is exactly why this
  // has to be a multiplier: the frame at save time is not the frame at open.
  const two = stage({ params: { scaleFactor: 2 } })
  assert.deepEqual(outputDimensions(two, 1664, 2432), { width: 3328, height: 4864 })
  assert.deepEqual(outputDimensions(two, 2080, 3040), { width: 4160, height: 6080 })
  assert.equal(outputLabel(two), '2×')
})

test('short-edge mode preserves the aspect ratio', () => {
  const pixels = stage({ params: { resolutionMode: 'pixels', targetResolution: 2160 } })
  // 1000×1500 → short edge 1000 becomes 2160, so the long edge follows.
  assert.deepEqual(outputDimensions(pixels, 1000, 1500), { width: 2160, height: 3240 })
  assert.equal(outputLabel(pixels), '2160px')
})

test('the short edge asked for matches what ToolView would ask for', () => {
  // The payload builder always sends `resolution`; a second rule here would
  // mean the editor and ToolView asking the same tool for different things.
  const relative = stage({ params: { scaleFactor: 2 } })
  assert.equal(finalResolutionFor(relative, 1664, 2432), 3328)
  assert.equal(finalResolutionFor(relative, 2432, 1664), 3328)

  const pixels = stage({ params: { resolutionMode: 'pixels', targetResolution: 1440 } })
  assert.equal(finalResolutionFor(pixels, 1664, 2432), 1440)
})

test('a stage with no params falls back to the same defaults ToolView uses', () => {
  assert.equal(finalResolutionFor(stage(), 1000, 2000), 2000)
  assert.deepEqual(outputDimensions(stage(), 1000, 2000), { width: 2000, height: 4000 })
})

// -- the resampling kernel --------------------------------------------------

function sum(weights: Float32Array) {
  let total = 0
  for (const w of weights) total += w
  return total
}

test('every destination pixel draws a full unit of source', () => {
  // Weights that did not sum to 1 would darken or brighten the image by the
  // amount they were off, uniformly — the kind of bug that reads as "the
  // upscaler washed it out".
  for (const [from, to] of [[100, 200], [200, 100], [100, 400], [37, 111], [111, 37]]) {
    for (const row of contributions(from, to)) {
      assert.ok(
        Math.abs(sum(row.weights) - 1) < 1e-5,
        `weights for ${from}→${to} summed to ${sum(row.weights)}`
      )
    }
  }
})

test('contributions stay inside the source', () => {
  const srcSize = 64
  for (const row of contributions(srcSize, 256)) {
    assert.ok(row.start >= 0, `start ${row.start} is before the source`)
    assert.ok(
      row.start + row.weights.length <= srcSize,
      `run ends at ${row.start + row.weights.length}, past ${srcSize}`
    )
  }
})

test('downsampling widens the kernel so no source pixel is skipped', () => {
  // A fixed-width kernel at 4:1 would sample every fourth pixel and alias.
  // The support scales with the ratio, so each destination pixel sees them all.
  const wide = contributions(400, 100)
  const middle = wide[50]
  assert.ok(
    middle.weights.length >= 20,
    `expected a wide window when downsampling 4:1, got ${middle.weights.length}`
  )
})

test('upsampling keeps the kernel at its natural width', () => {
  const up = contributions(100, 400)
  // Lanczos-3 reaches three source pixels either side, so seven at most.
  assert.ok(
    up[200].weights.length <= 7,
    `expected a narrow window when upsampling, got ${up[200].weights.length}`
  )
})

test('an identity resize is a pass-through', () => {
  const rows = contributions(50, 50)
  rows.forEach((row, index) => {
    assert.ok(Math.abs(sum(row.weights) - 1) < 1e-5)
    // The peak sits on the pixel itself, not beside it.
    const peak = [...row.weights].indexOf(Math.max(...row.weights))
    assert.equal(row.start + peak, index, `row ${index} peaks at ${row.start + peak}`)
  })
})

test('a degenerate window still produces a pixel', () => {
  // One source pixel stretched wide: rather than a black row, the nearest
  // source pixel carries it.
  for (const row of contributions(1, 8)) {
    assert.equal(row.weights.length >= 1, true)
    assert.ok(Math.abs(sum(row.weights) - 1) < 1e-5)
  }
})
