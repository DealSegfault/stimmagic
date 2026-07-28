/**
 * Everything the Edits list needs to derive from a document.
 *
 * **No staleness is ever stored.** It is computed at render time by comparing
 * each generative op's `sampled_input_hash` against the hash of its current
 * input composite. Storing it would mean migrating a heuristic every time it
 * changes, and would let the document disagree with the pixels.
 *
 * Two severities, with different physics, and no third:
 *
 * - **advisory** — a patch or pixel-reading container whose input changed. Its
 *   composite is still deterministic and still correct pixels; only the context
 *   it was *sampled* against has moved. Never blocks, never auto-regenerates.
 * - **hard** — a checkpoint (whole-image op) whose input changed, and
 *   everything above it. The checkpoint's content was sampled from the whole
 *   image below, so it cannot be re-derived without re-running the model. The
 *   canvas keeps showing the cached result rather than silently degrading.
 */

import type { Op, StackDocument } from './types.ts'
import { pickedCandidate } from './types.ts'
import { stackHashes } from './stackHashes.ts'

export type Staleness = 'clean' | 'advisory' | 'hard'

export interface OpState {
  op: Op
  index: number
  inputHash: string
  staleness: Staleness
  /** Index of the checkpoint that folds this op, if any. */
  checkpointIndex: number | null
}

export interface StackState {
  ops: OpState[]
  /** Indices of whole-image ops, bottom to top. */
  checkpoints: number[]
  /** How many rows are stale, for the checkpoint band's status line. */
  staleCount: number
}

/**
 * A segment is the run of rows between checkpoints. Order within a segment is
 * free — replay is deterministic and cheap — while a checkpoint pins order,
 * because its content was sampled from everything below it and re-sampling
 * costs money.
 */
export function segmentBounds(doc: StackDocument, index: number): { start: number; end: number } {
  let start = 0
  let end = doc.edits.length
  for (let i = 0; i < doc.edits.length; i++) {
    if (doc.edits[i].class !== 'whole') continue
    if (i < index) start = i + 1
    if (i >= index) { end = i; break }
  }
  return { start, end }
}

/** Whether an op may move to `toIndex` without crossing a checkpoint. */
export function canMoveWithinSegment(
  doc: StackDocument,
  opId: string,
  toIndex: number
): boolean {
  const from = doc.edits.findIndex(op => op.id === opId)
  if (from < 0) return false
  // A checkpoint itself never moves: its position IS what it was computed from.
  if (doc.edits[from].class === 'whole') return false
  const { start, end } = segmentBounds(doc, from)
  return toIndex >= start && toIndex <= end
}

export function deriveStackState(doc: StackDocument | null): StackState {
  if (!doc) return { ops: [], checkpoints: [], staleCount: 0 }

  const { inputs } = stackHashes(doc)
  const ops: OpState[] = []
  const checkpoints: number[] = []

  // Once a checkpoint is hard-stale, everything above it is too: it sits on a
  // composite that no longer exists.
  let aboveHardStale = false

  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index]
    const inputHash = inputs[index]
    if (op.class === 'whole') checkpoints.push(index)

    let staleness: Staleness = 'clean'
    if (aboveHardStale) {
      staleness = 'hard'
    } else if (op.enabled) {
      const sampled = sampledHash(op)
      if (sampled && sampled !== inputHash) {
        if (op.class === 'whole') {
          staleness = 'hard'
          aboveHardStale = true
        } else {
          staleness = 'advisory'
        }
      }
    }

    ops.push({ op, index, inputHash, staleness, checkpointIndex: null })
  }

  // Attribute each row to the checkpoint that folds it — the one above it.
  for (const opState of ops) {
    const fold = checkpoints.find(index => index > opState.index)
    opState.checkpointIndex = fold ?? null
  }

  return {
    ops,
    checkpoints,
    staleCount: ops.filter(o => o.staleness !== 'clean').length,
  }
}

function sampledHash(op: Op): string | null {
  if (op.class === 'patch' || op.class === 'whole') {
    return pickedCandidate(op)?.sampled_input_hash ?? null
  }
  if (op.class === 'container') {
    // Retouch engines that READ pixels (heal, clone) bake against their input
    // and carry an advisory hash like patches do. Pure paint does not.
    return (op as any).sampled_input_hash ?? null
  }
  return null
}

/**
 * Which rows a gesture on `opId` would disturb — the blast radius.
 *
 * Shown on hover/focus of a drag grip or eye toggle only, never at rest:
 * decoration that is always on stops being information. Moving or disabling an
 * op changes the input of everything above it, so every generative op above
 * would go stale, and a checkpoint above takes everything with it.
 */
export function blastRadius(doc: StackDocument | null, opId: string): {
  advisory: Set<string>
  hard: Set<string>
} {
  const advisory = new Set<string>()
  const hard = new Set<string>()
  if (!doc) return { advisory, hard }

  const from = doc.edits.findIndex(op => op.id === opId)
  if (from < 0) return { advisory, hard }

  let reachedCheckpoint = false
  for (let index = from + 1; index < doc.edits.length; index++) {
    const op = doc.edits[index]
    if (reachedCheckpoint) {
      hard.add(op.id)
      continue
    }
    if (op.class === 'whole') {
      hard.add(op.id)
      reachedCheckpoint = true
    } else if (op.class === 'patch' || sampledHash(op)) {
      advisory.add(op.id)
    }
  }
  return { advisory, hard }
}

/** Facts-only status line for a stale checkpoint band. */
export function checkpointStatus(state: StackState, index: number): string | null {
  const checkpoint = state.ops[index]
  if (!checkpoint || checkpoint.staleness !== 'hard') return null
  const below = state.ops.slice(0, index).filter(o => o.staleness !== 'clean').length
  const count = Math.max(1, below)
  return `Showing previous result — ${count} ${count === 1 ? 'edit' : 'edits'} stale`
}

/** How many steps a checkpoint folds, for its "Built from N steps" affordance. */
export function foldedCount(doc: StackDocument | null, checkpointIndex: number): number {
  if (!doc) return 0
  const { start } = segmentBounds(doc, checkpointIndex)
  return checkpointIndex - start
}
