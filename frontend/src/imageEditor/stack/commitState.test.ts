import test from 'node:test'
import assert from 'node:assert/strict'
import { hasUncommittedChanges } from './commitState.ts'
import type { StackDocument } from './types.ts'

function document(overrides: Partial<StackDocument> = {}): StackDocument {
  return {
    format: 'stimma-image-stack',
    version: 1,
    base: {
      asset_id: 1,
      revision_id: 2,
      media_id: 3,
      file_hash: 'base',
      width: 100,
      height: 100,
    },
    canvas: { width: 100, height: 100 },
    edits: [],
    ...overrides,
  }
}

test('a persisted uncommitted state stays dirty after reload', () => {
  assert.equal(hasUncommittedChanges(document({
    has_uncommitted_changes: true,
  })), true)
})

test('a committed working state stays clean after reload even when it has edits', () => {
  assert.equal(hasUncommittedChanges(document({
    edits: [{ enabled: true } as any],
    has_uncommitted_changes: false,
    last_commit: { asset_id: 1, revision_id: 4 },
  })), false)
})

test('legacy authored documents conservatively require a commit', () => {
  assert.equal(hasUncommittedChanges(document({
    edits: [{ enabled: true } as any],
  })), true)
  assert.equal(hasUncommittedChanges(document()), false)
})
