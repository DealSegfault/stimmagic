import { canonicalOp } from './stackHashes.ts'
import type { StackDocument } from './types.ts'

/**
 * The part of a document that changes the image a commit would materialize.
 *
 * Journal position is deliberately absent: adding a step and then removing it
 * must land on the same state. Labels, unpicked candidates and other editor UI
 * metadata are already excluded by canonicalOp for the same reason.
 */
function commitState(document: StackDocument): string {
  const output = document.output?.enabled
    ? {
        enabled: true,
        method: document.output.method,
        tool_id: document.output.tool_id,
        params: document.output.params,
      }
    : null
  return JSON.stringify({
    base: {
      file_hash: document.base.file_hash,
      payload_ref: document.base.payload_ref ?? null,
      width: document.base.width,
      height: document.base.height,
    },
    canvas: document.canvas,
    edits: document.edits.map(canonicalOp),
    output,
  })
}

/** Two independent 32-bit passes make accidental equality vanishingly rare. */
function stateHash(input: string): string {
  let first = 0x811c9dc5
  let second = 0x9e3779b9
  for (let index = 0; index < input.length; index++) {
    const code = input.charCodeAt(index)
    first = Math.imul(first ^ code, 0x01000193)
    second = Math.imul(second ^ code, 0x85ebca6b)
  }
  return `${input.length.toString(16)}:${(first >>> 0).toString(16)}:${(second >>> 0).toString(16)}`
}

export function documentCommitStateHash(document: StackDocument): string {
  return stateHash(commitState(document))
}

/** Record the exact working state represented by the new Asset Revision. */
export function captureCommittedState(document: StackDocument): void {
  document.committed_state_hash = documentCommitStateHash(document)
  document.has_uncommitted_changes = false
}

/**
 * Seed the comparison boundary for new and known-clean documents.
 *
 * A legacy dirty document has no trustworthy boundary, so it keeps the old
 * conservative behavior until it is committed. The one safe repair is an
 * untouched branch with no prior editor commit and no authored state: that is
 * the sticky add-then-remove bug, not an image change waiting to be saved.
 */
export function ensureCommittedState(document: StackDocument): void {
  if (document.committed_state_hash) return
  const pristine = document.edits.length === 0
    && !document.output?.enabled
    && !document.base.payload_ref
  const knownClean = document.has_uncommitted_changes === false
    || document.has_uncommitted_changes === undefined && pristine
    || pristine && !document.last_commit
  if (knownClean) captureCommittedState(document)
}

/**
 * Restore the commit boundary independently of the browser session.
 *
 * Older documents predate the persisted flag. Treat any authored state as
 * uncommitted in that case; a subsequent commit records the exact boundary.
 */
export function hasUncommittedChanges(document: StackDocument | null): boolean {
  if (!document) return false
  if (document.committed_state_hash) {
    return document.committed_state_hash !== documentCommitStateHash(document)
  }
  if (typeof document.has_uncommitted_changes === 'boolean') {
    return document.has_uncommitted_changes
  }
  return document.edits.length > 0
    || Boolean(document.output?.enabled)
    || Boolean(document.base.payload_ref)
}
