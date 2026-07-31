import test from 'node:test'
import assert from 'node:assert/strict'
import {
  headCacheImageRef,
} from './headCache.ts'
import type { StackDocument } from './types.ts'

function documentWithBrightness(brightness: number): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: {
      asset_id: 1,
      revision_id: 2,
      media_id: 3,
      file_hash: 'base-hash',
      width: 100,
      height: 80,
    },
    canvas: { width: 100, height: 80 },
    edits: [{
      id: 'adjust-1',
      class: 'parametric',
      enabled: true,
      label: 'Adjust',
      exec: { kind: 'adjust' },
      params: { brightness },
    }],
  }
}

test('head cache is addressed by the exact rendered stack', () => {
  const document = documentWithBrightness(10)

  assert.match(headCacheImageRef(document), /^cache\/head-[0-9a-f]{8}\.png$/)
})

test('a pixel-affecting stack change invalidates the cached head', () => {
  const before = documentWithBrightness(10)
  const after = documentWithBrightness(11)

  assert.notEqual(headCacheImageRef(before), headCacheImageRef(after))
})
