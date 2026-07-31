/**
 * Normalize persisted names from before Paint and Retouch became distinct.
 *
 * Historical raster layers used all three executor names `paint`, `retouch`
 * and `sketch`, even though the compositor treated them identically. They are
 * Paint layers now. Executor names are deliberately left intact on old ops:
 * executor identity participates in stack hashes, and rewriting it would make
 * every sampled operation above the layer appear stale.
 *
 * New writes use `paint`. Region-based Retouch uses the unambiguous
 * `retouch-regions` executor and is never touched here.
 */

const LEGACY_RASTER_PAINT_KINDS = new Set(['paint', 'retouch', 'sketch'])

export function normalizeOperationTerminology(op: any): any {
  if (
    op?.class === 'container'
    && typeof op.raster_ref === 'string'
    && LEGACY_RASTER_PAINT_KINDS.has(op.exec?.kind)
    && op.label === 'Retouch'
  ) {
    op.label = 'Paint'
  }
  if (op?.class === 'patch' && op.operation === 'erase') {
    op.operation = 'remove'
    if (op.label === 'Erase') op.label = 'Remove'
  }
  return op
}

export function normalizeDocumentTerminology(document: any): any {
  for (const op of document?.edits ?? []) normalizeOperationTerminology(op)
  return document
}

/**
 * Undo entries may carry a whole removed/added op. Normalize those copies too
 * so undo cannot resurrect the retired Retouch label after the open document
 * itself has already been normalized.
 */
export function normalizeJournalTerminology(entries: any[]): any[] {
  for (const entry of entries ?? []) {
    normalizeOperationTerminology(entry?.forward?.op)
    normalizeOperationTerminology(entry?.inverse?.op)
    normalizeDocumentTerminology(entry?.document)
  }
  return entries
}
