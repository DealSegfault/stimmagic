/**
 * The journal reducer: how one journal entry moves a document forward or back.
 *
 * Extracted from the document store so undo/redo semantics are testable as
 * plain data transforms. `replaceDocument` conversions are the one shape the
 * store still owns, because their inverse swaps the whole document ref.
 */
import type { JournalEntry, StackDocument } from './types.ts'

/**
 * Apply an entry's inverse. Returns the document to use afterwards — the same
 * object mutated in place, except for conversions whose inverse carries an
 * entire replacement document.
 */
export function applyJournalInverse(
  d: StackDocument,
  entry: JournalEntry,
): StackDocument {
  const inv = entry.inverse || {}
  switch (entry.action) {
    case 'add_op':
      d.edits = d.edits.filter(o => o.id !== inv.op_id)
      break
    case 'remove_op':
      d.edits.splice(Math.min(inv.index, d.edits.length), 0, inv.op)
      break
    case 'move_op': {
      const from = d.edits.findIndex(o => o.id === inv.op_id)
      if (from >= 0) {
        const [op] = d.edits.splice(from, 1)
        d.edits.splice(inv.to, 0, op)
      }
      break
    }
    case 'reorder_ops': {
      const byId = new Map(d.edits.map(op => [op.id, op]))
      d.edits = (inv.order ?? []).flatMap((id: string) => byId.get(id) ?? [])
      break
    }
    case 'replace_edits':
      d.edits = inv.edits ?? []
      break
    case 'toggle_op': {
      const op = d.edits.find(o => o.id === inv.op_id)
      if (op) op.enabled = inv.enabled
      break
    }
    case 'set_params': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      if (op) op.params = inv.params
      break
    }
    case 'set_reference_images': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      if (op) op.reference_images = inv.images
      break
    }
    case 'replace_params': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      if (op) op.params = inv.params
      break
    }
    case 'set_regions': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      if (op) op.regions = inv.regions
      break
    }
    case 'set_label': {
      const op = d.edits.find(o => o.id === inv.op_id)
      if (op) op.label = inv.label
      break
    }
    case 'pick_candidate': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      // Un-picking only; the candidates themselves are never touched.
      if (op) op.picked = inv.candidate_id
      break
    }
    case 'set_blend': {
      const op = d.edits.find(o => o.id === inv.op_id) as any
      if (op) op.blend = inv.blend
      break
    }
    case 'set_output':
      d.output = inv.output
      break
    // A conversion's inverse is the entire document it replaced.
    case 'flatten_whole_ops':
      if (inv.document) return inv.document
      break
  }
  return d
}

/** Apply an entry's forward direction; mirror of applyJournalInverse. */
export function applyJournalForward(d: StackDocument, entry: JournalEntry): void {
  const fwd = entry.forward || {}
  switch (entry.action) {
    case 'add_op':
      d.edits.splice(Math.min(fwd.index, d.edits.length), 0, fwd.op)
      break
    case 'remove_op':
      d.edits = d.edits.filter(o => o.id !== fwd.op_id)
      break
    case 'move_op': {
      const from = d.edits.findIndex(o => o.id === fwd.op_id)
      if (from >= 0) {
        const [op] = d.edits.splice(from, 1)
        d.edits.splice(fwd.to, 0, op)
      }
      break
    }
    case 'reorder_ops': {
      const byId = new Map(d.edits.map(op => [op.id, op]))
      d.edits = (fwd.order ?? []).flatMap((id: string) => byId.get(id) ?? [])
      break
    }
    case 'replace_edits':
      d.edits = fwd.edits ?? []
      break
    case 'toggle_op': {
      const op = d.edits.find(o => o.id === fwd.op_id)
      if (op) op.enabled = fwd.enabled
      break
    }
    case 'set_params': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.params = { ...(op.params || {}), ...fwd.params }
      break
    }
    case 'set_reference_images': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.reference_images = fwd.images
      break
    }
    case 'replace_params': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.params = fwd.params
      break
    }
    case 'set_regions': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.regions = fwd.regions
      break
    }
    case 'set_label': {
      const op = d.edits.find(o => o.id === fwd.op_id)
      if (op) op.label = fwd.label
      break
    }
    case 'pick_candidate': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.picked = fwd.candidate_id
      break
    }
    case 'set_blend': {
      const op = d.edits.find(o => o.id === fwd.op_id) as any
      if (op) op.blend = fwd.blend
      break
    }
    case 'set_output':
      d.output = fwd.output
      break
  }
}
