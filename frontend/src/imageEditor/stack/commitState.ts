import type { StackDocument } from './types.ts'

/**
 * Restore the commit boundary independently of the browser session.
 *
 * Older documents predate the persisted flag. Treat any authored state as
 * uncommitted in that case; a subsequent commit records the exact boundary.
 */
export function hasUncommittedChanges(document: StackDocument | null): boolean {
  if (!document) return false
  if (typeof document.has_uncommitted_changes === 'boolean') {
    return document.has_uncommitted_changes
  }
  return document.edits.length > 0
    || Boolean(document.output?.enabled)
    || Boolean(document.base.payload_ref)
}
