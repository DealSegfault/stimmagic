/**
 * Everything the Edits list needs to derive from a document.
 *
 * **No staleness is ever stored.** It is computed at render time by comparing
 * each generative op's `sampled_input_hash` against the hash of its current
 * input composite. Storing it would mean migrating a heuristic every time it
 * changes, and would let the document disagree with the pixels.
 *
 * **One severity, and no second one.** A patch or pixel-reading container whose
 * input changed is *advisory*: its composite is still deterministic and still
 * correct pixels, only the context it was sampled against has moved. It never
 * blocks and never auto-regenerates.
 *
 * There used to be a second severity — a checkpoint whose input changed, which
 * froze everything above it behind a wall. It is gone with the whole-image op
 * class it described. An advisory is comprehensible because it is a claim about
 * one row; a wall was a claim about the world, and no wording made it read.
 * Every row in this list is now a live parameter, so order is free everywhere
 * and nothing pins it.
 */

import type { Op, StackDocument } from './types.ts'
import { pickedCandidate } from './types.ts'
import { stackHashes } from './stackHashes.ts'

export type Staleness = 'clean' | 'advisory'

export interface OpState {
  op: Op
  index: number
  inputHash: string
  staleness: Staleness
}

export interface StackState {
  ops: OpState[]
}

/**
 * Resolve a drag's landing GAP into the index moveOp wants, or null when the
 * drop would be a no-op.
 *
 * A gap `g` is the boundary before edits[g] — dropping there means "end up at
 * position g". moveOp splices the row OUT and then back in, so its target is
 * an index in the list WITHOUT the row: one lower for any gap above where the
 * row started. The two gaps touching the row itself (`from` and `from + 1`)
 * put it back where it was, and promising a move that will not happen is
 * worse than showing nothing.
 *
 * Every other gap is legal: with no checkpoints there are no segments to stay
 * inside.
 */
export function moveTargetForGap(
  doc: StackDocument,
  opId: string,
  gap: number
): number | null {
  const from = doc.edits.findIndex(op => op.id === opId)
  if (from < 0) return null
  if (gap < 0 || gap > doc.edits.length) return null
  if (gap === from || gap === from + 1) return null
  return gap > from ? gap - 1 : gap
}

export function deriveStackState(doc: StackDocument | null): StackState {
  if (!doc) return { ops: [] }

  const { inputs } = stackHashes(doc)
  const ops: OpState[] = []

  for (let index = 0; index < doc.edits.length; index++) {
    const op = doc.edits[index]
    const inputHash = inputs[index]

    let staleness: Staleness = 'clean'
    if (op.enabled) {
      const sampled = sampledHash(op)
      if (sampled && sampled !== inputHash) staleness = 'advisory'
    }

    ops.push({ op, index, inputHash, staleness })
  }

  return { ops }
}

function sampledHash(op: Op): string | null {
  if (op.class === 'patch') {
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
 * op changes the input of everything above it, so every generative op above it
 * would go advisory. Nothing goes further than advisory, because no row can
 * stop being derivable from its input any more.
 */
export function blastRadius(doc: StackDocument | null, opId: string): {
  advisory: Set<string>
} {
  const advisory = new Set<string>()
  if (!doc) return { advisory }

  const from = doc.edits.findIndex(op => op.id === opId)
  if (from < 0) return { advisory }

  for (let index = from + 1; index < doc.edits.length; index++) {
    const op = doc.edits[index]
    if (op.class === 'patch' || sampledHash(op)) advisory.add(op.id)
  }
  return { advisory }
}
