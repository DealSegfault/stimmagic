import assert from 'node:assert/strict'
import test from 'node:test'
import {
  applyToPoint,
  cropAffine,
  multiply,
  payloadToDocument,
  stageFromPayload,
  translate,
} from './geometryTransform.ts'
import type { StackDocument } from './types.ts'

function documentWithCrop(): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: {
      asset_id: 1,
      revision_id: 1,
      media_id: 1,
      file_hash: 'base',
      width: 2048,
      height: 2048,
    },
    canvas: { width: 2048, height: 2048 },
    edits: [{
      id: 'crop',
      class: 'parametric',
      enabled: true,
      label: 'Crop',
      exec: { kind: 'crop' },
      params: { rect: { x: 0.5, y: 0.5, width: 1, height: 9 / 16 } },
    }],
    output: { enabled: false, mode: 'photo', tool_id: null, params: {} },
  }
}

test('a compact patch origin is folded into its document-space anchor', () => {
  const authored = { matrix: [1, 0, 0, 1, 0, 0] }
  const anchor = payloadToDocument(authored, [700, 900])
  assert.ok(anchor)
  assert.deepEqual(applyToPoint(anchor, 0, 0), [700, 900])
})

test('a crop projects compact patch pixels from document space without clipping their origin', () => {
  const doc = documentWithCrop()
  const anchor = payloadToDocument({ matrix: [1, 0, 0, 1, 0, 0] }, [700, 900])
  assert.ok(anchor)
  const projected = stageFromPayload(doc, 1, anchor)
  // A centered 2048-square -> 16:9 crop removes 448 px from the top.
  assert.deepEqual(applyToPoint(projected.matrix, 0, 0), [700, 452])
  assert.equal(projected.width, 2048)
  assert.equal(projected.height, 1152)
})

test('authored crop geometry round-trips through permanent document space', () => {
  const first = cropAffine(
    { rect: { x: 0.5, y: 0.5, width: 1, height: 9 / 16 } },
    2048,
    2048,
  )
  const anchor = payloadToDocument(first, [100, 200])
  assert.ok(anchor)
  assert.deepEqual(
    applyToPoint(multiply(first.matrix, anchor), 0, 0),
    applyToPoint(translate(100, 200), 0, 0),
  )
})
