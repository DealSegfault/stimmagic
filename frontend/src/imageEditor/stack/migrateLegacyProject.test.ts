import assert from 'node:assert/strict'
import test from 'node:test'

import { migrateLegacyProject } from './migrateLegacyProject.ts'

/** A snapshot-editor state with every field at its default. */
function untouched(overrides: Record<string, any> = {}) {
  return {
    state: {
      crop: { x: 0.5, y: 0.5, width: 1, height: 1 },
      rotation: 0, rotation90: 0, flipX: false, flipY: false,
      brightness: 0, contrast: 0, saturation: 0, exposure: 0, temperature: 0, gamma: 1,
      filter: null, colorMatrix: null,
      splitToningEnabled: false, gradientMapEnabled: false, colorIsolationEnabled: false,
      blur: 0, sharpen: 0, noise: 0, glow: 0, pixelate: 0, chromaticAberration: 0,
      motionBlur: 0, motionBlurAngle: 0, vignette: 0, clarity: 0,
      halftone: 0, halftoneAngle: 0, vhs: 0, glitch: 0, glitchBlockSize: 16,
      ditherEnabled: false, ditherPalette: 'none',
      annotations: [], decorations: [], redactions: [], stickers: [],
      retouchLayerData: null,
      ...overrides,
    },
  }
}

test('an untouched project migrates to an empty stack', () => {
  const { ops, dropped } = migrateLegacyProject(untouched())
  assert.equal(ops.length, 0, 'nothing was edited, so there is nothing to import')
  assert.deepEqual(dropped, [])
})

test('a default crop rect is not imported as a Crop step', () => {
  const { ops } = migrateLegacyProject(untouched({ brightness: 20 }))
  assert.deepEqual(ops.map(o => (o as any).exec.kind), ['adjust'])
})

test('crop, legacy retouch pixels, adjust and annotate land bottom-to-top in render order', () => {
  const { ops, rasters } = migrateLegacyProject(untouched({
    crop: { x: 0.5, y: 0.5, width: 0.8, height: 0.8 },
    retouchLayerData: 'data:image/png;base64,iVBORw0KGgo=',
    brightness: 15,
    vignette: 40,
    annotations: [{ id: 'a', type: 'rect' }],
  }))

  assert.deepEqual(ops.map(o => (o as any).exec.kind), ['crop', 'paint', 'adjust', 'annotate'])
  assert.equal(rasters.length, 1)
  assert.equal(rasters[0].opId, ops[1].id)
  assert.equal(ops[1].label, 'Paint')
  assert.equal((ops[1] as any).raster_ref, `payloads/${ops[1].id}-layer.png`)
})

test('every touched adjustment lands in ONE Adjust step', () => {
  const { ops } = migrateLegacyProject(untouched({
    brightness: 15, saturation: -20, vignette: 40, splitToningEnabled: true,
  }))
  const adjust = ops.filter(o => (o as any).exec.kind === 'adjust')
  assert.equal(adjust.length, 1, 'a adjust session is one step, not one per slider')
  assert.deepEqual((adjust[0] as any).params, {
    brightness: 15, saturation: -20, vignette: 40, splitToningEnabled: true,
  })
})

test('the Adjust label names the sections it touched', () => {
  const { ops } = migrateLegacyProject(untouched({ brightness: 15, vignette: 40 }))
  assert.equal(ops[0].label, 'Adjust — Light · Effects')
})

test('untouched fields are not carried into params', () => {
  const { ops } = migrateLegacyProject(untouched({ contrast: 10 }))
  assert.deepEqual(Object.keys((ops[0] as any).params), ['contrast'])
})

test('shape families merge into one Annotate step in draw order', () => {
  const { ops } = migrateLegacyProject(untouched({
    annotations: [{ id: 'a' }],
    decorations: [{ id: 'd' }],
    redactions: [{ id: 'r' }],
    stickers: [{ id: 's' }],
  }))
  const annotate = ops.find(o => (o as any).exec.kind === 'annotate') as any
  assert.deepEqual(annotate.params.shapes.map((s: any) => s.id), ['a', 'd', 'r', 's'])
})

test('geometry carries straighten and flips, not just the rectangle', () => {
  const { ops } = migrateLegacyProject(untouched({
    rotation: 0.05, rotation90: 1, flipX: true,
  }))
  assert.deepEqual((ops[0] as any).params, {
    rect: { x: 0.5, y: 0.5, width: 1, height: 1 },
    rotation: 0.05, cropRotation: 0, rotation90: 1, flipX: true, flipY: false,
  })
})

test('a tilted crop window survives, and is not confused with image rotation', () => {
  // The two turn opposite ways, so carrying one across as the other does not
  // merely lose the straightening — it applies it backwards.
  const { ops } = migrateLegacyProject(untouched({
    crop: { x: 0.5, y: 0.5, width: 1, height: 1, rotation: 0.12 },
  }))
  assert.equal(ops.length, 1, 'a straightened crop is not an identity crop')
  assert.equal((ops[0] as any).params.cropRotation, 0.12)
  assert.equal((ops[0] as any).params.rotation, 0)
})

test('what the stack cannot represent is named, not silently lost', () => {
  const { dropped } = migrateLegacyProject(untouched({
    frame: { type: 'polaroid' },
    backgroundColor: { r: 0, g: 0, b: 0, a: 1 },
    targetSize: { width: 800, height: 600 },
  }))
  assert.equal(dropped.length, 3)
  assert.ok(dropped.some(d => d.includes('frame')))
  assert.ok(dropped.some(d => d.includes('background')))
  assert.ok(dropped.some(d => d.includes('export size')))
})

test('an unreadable retouch layer is reported rather than dropped in silence', () => {
  const { ops, dropped } = migrateLegacyProject(untouched({ retouchLayerData: {} }))
  assert.equal(ops.length, 0)
  assert.ok(dropped[0].includes('retouch layer'))
})

test('a project with no state at all reports rather than throws', () => {
  const { ops, dropped } = migrateLegacyProject(null)
  assert.equal(ops.length, 0)
  assert.equal(dropped.length, 1)
})

test('ops get distinct stable ids', () => {
  const { ops } = migrateLegacyProject(untouched({
    crop: { x: 0.5, y: 0.5, width: 0.9, height: 1 },
    brightness: 5,
    annotations: [{ id: 'a' }],
  }))
  const ids = ops.map(o => o.id)
  assert.equal(new Set(ids).size, ids.length)
  assert.ok(ids.every(id => id.length === 26), 'ULID-shaped')
})
