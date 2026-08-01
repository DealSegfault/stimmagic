import assert from 'node:assert/strict'
import test from 'node:test'

import {
  expandEdgesFromParams,
  expandParamsFromEdges,
  expandedFrame,
} from './expandGeometry.ts'
import { geometryBelow, applyToPoint } from './geometryTransform.ts'
import type { StackDocument } from './types.ts'

test('expandedFrame uses the tri-repo floor rule, per axis', () => {
  // 1344×768 at 25% everywhere: floor(1344·25/100)=336, floor(768·25/100)=192.
  const frame = expandedFrame({ top: 25, bottom: 25, left: 25, right: 25 }, 1344, 768)
  assert.deepEqual(frame, { width: 2016, height: 1152, left: 336, top: 192 })

  // Truncation, not rounding: floor(101·33/100) = 33, not 33.33 → 33.
  const odd = expandedFrame({ top: 0, bottom: 0, left: 33, right: 0 }, 101, 50)
  assert.deepEqual(odd, { width: 134, height: 50, left: 33, top: 0 })
})

test('edges round-trip through the wire params and clamp garbage', () => {
  const params = expandParamsFromEdges({ top: 10, bottom: 0, left: 150, right: -5 })
  assert.deepEqual(params, {
    expand_top_pct: 10,
    expand_bottom_pct: 0,
    expand_left_pct: 100,
    expand_right_pct: 0,
  })
  assert.deepEqual(expandEdgesFromParams(params), {
    top: 10, bottom: 0, left: 100, right: 0,
  })
  assert.deepEqual(expandEdgesFromParams(undefined), {
    top: 0, bottom: 0, left: 0, right: 0,
  })
})

function doc(edits: any[]): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: { asset_id: 1, revision_id: 1, media_id: 1, file_hash: 'base', width: 200, height: 100 },
    canvas: { width: 200, height: 100 },
    edits,
  } as StackDocument
}

function expandOp(params: any, { picked = true, enabled = true } = {}) {
  return {
    id: 'x', class: 'patch', enabled, label: 'Expand',
    exec: { kind: 'tool', tool_id: 't', task_type: 'outpaint-image' },
    operation: 'expand',
    params, mask_ref: 'payloads/x-mask.png',
    picked: picked ? 'c1' : null,
    candidates: picked
      ? [{ id: 'c1', patch_ref: 'p', media_id: 1, file_hash: 'h', sampled_input_hash: 's' }]
      : [],
  }
}

test('geometryBelow grows the frame and translates by the new margins', () => {
  const d = doc([expandOp({ expand_top_pct: 10, expand_left_pct: 50 })])
  const geometry = geometryBelow(d, 1)
  // left: floor(200·50/100)=100; top: floor(100·10/100)=10.
  assert.equal(geometry.width, 300)
  assert.equal(geometry.height, 110)
  assert.deepEqual(applyToPoint(geometry.matrix, 0, 0), [100, 10])
})

test('a staged or disabled expand contributes no geometry — the mirror law', () => {
  const staged = doc([expandOp({ expand_left_pct: 50 }, { picked: false })])
  assert.equal(geometryBelow(staged, 1).width, 200)

  const hidden = doc([expandOp({ expand_left_pct: 50 }, { enabled: false })])
  assert.equal(geometryBelow(hidden, 1).width, 200)
})

test('crop above an expand works in the grown frame', () => {
  const crop = {
    id: 'c', class: 'parametric', enabled: true, label: 'Crop',
    exec: { kind: 'crop' },
    params: { rect: { x: 0.5, y: 0.5, width: 0.5, height: 0.5 } },
  }
  const d = doc([expandOp({ expand_left_pct: 50, expand_right_pct: 50 }), crop])
  // Expanded to 400×100, then cropped to half: 200×50.
  const geometry = geometryBelow(d, 2)
  assert.equal(geometry.width, 200)
  assert.equal(geometry.height, 50)
})
