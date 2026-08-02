import assert from 'node:assert/strict'
import test from 'node:test'

import {
  assetHeadSignature,
  normalizeAssetHead,
  replaceAssetHeadInCache,
} from './assetHeadProjection.ts'

test('head identity includes the changing revision payload, not only the stable Asset', () => {
  const oldHead = { id: 12, asset_id: 12, revision_id: 4, media_id: 40, file_hash: 'old' }
  const newHead = { id: 12, asset_id: 12, revision_id: 5, media_id: 41, file_hash: 'new' }

  assert.notEqual(assetHeadSignature(oldHead), assetHeadSignature(newHead))
})

test('normalizing a fresh head preserves stable browser identity', () => {
  assert.deepEqual(
    normalizeAssetHead(12, { id: 41, media_id: 41, revision_id: 5, file_hash: 'new' }),
    { id: 12, asset_id: 12, media_id: 41, revision_id: 5, file_hash: 'new' },
  )
})

test('replaces the payload for the matching Asset without disturbing slideshow order', () => {
  const first = { id: 12, asset_id: 12, revision_id: 4, media_id: 40, file_hash: 'old' }
  const second = { id: 13, asset_id: 13, revision_id: 1, media_id: 50, file_hash: 'other' }
  const cache = new Map([[7, first], [8, second]])

  const next = replaceAssetHeadInCache(cache, 12, {
    asset_id: 12,
    revision_id: 5,
    media_id: 41,
    file_hash: 'new',
  })

  assert.notEqual(next, cache)
  assert.deepEqual(next.get(7), {
    id: 12,
    asset_id: 12,
    revision_id: 5,
    media_id: 41,
    file_hash: 'new',
  })
  assert.equal(next.get(8), second)
})

test('returns the same cache when the Asset is absent', () => {
  const cache = new Map([[0, { id: 13, asset_id: 13, file_hash: 'other' }]])
  assert.equal(replaceAssetHeadInCache(cache, 12, { file_hash: 'new' }), cache)
})
