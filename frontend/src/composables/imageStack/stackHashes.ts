/**
 * Content hashing for the op stack.
 *
 * `hash(i+1) = H(hash(i), canonical(op(i)))`, so any edit invalidates exactly
 * the ops at and above it and everything below is a cache hit. Disabled ops
 * hash as identity, which is why toggling one off is instant, and reordering
 * swaps hash inputs the same way — there is no special dirty logic anywhere.
 *
 * Kept free of rendering imports so the parts that only need to REASON about a
 * stack (staleness, blast radius) do not drag in a canvas.
 */

import type { Op, StackDocument } from './types.ts'
import { pickedCandidate } from './types.ts'

/** FNV-1a over a string. Fast, stable, and only ever compared for equality. */
function hashString(input: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(16).padStart(8, '0')
}

/**
 * The part of an op that changes its output. Anything not in here must not
 * affect pixels — labels and selection state deliberately do not.
 */
export function canonicalOp(op: Op): string {
  if (!op.enabled) return 'identity'
  const anyOp = op as any
  const picked = pickedCandidate(op)
  return JSON.stringify([
    op.class,
    anyOp.exec,
    anyOp.params ?? null,
    op.region ? [op.region.mask_ref, op.region.feather_px, op.region.invert] : null,
    anyOp.mask_ref ?? null,
    anyOp.raster_ref ?? null,
    anyOp.blend ?? null,
    picked ? [picked.file_hash, picked.patch_ref ?? null, picked.patch_origin ?? null] : null,
  ])
}

/** Input hashes for every op, plus the hash of the finished composite. */
export function stackHashes(doc: StackDocument): { inputs: string[]; head: string } {
  let hash = doc.base.file_hash
  const inputs: string[] = []
  for (const op of doc.edits) {
    inputs.push(hash)
    hash = hashString(hash + '|' + canonicalOp(op))
  }
  return { inputs, head: hash }
}
