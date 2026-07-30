/**
 * Session-only lifecycle for UI-created entries that have not affected pixels.
 *
 * The document does not persist "fragile": touching a substantive property
 * commits the entry, while choosing another sibling first cancels it. Keeping
 * cancellation separately lets an async payload upload finish harmlessly
 * without resurrecting an entry the person already replaced.
 */
export class FragileEntryTracker {
  private fragile = new Set<string>()
  private cancelled = new Set<string>()

  mark(id: string) {
    this.cancelled.delete(id)
    this.fragile.add(id)
  }

  commit(id: string) {
    this.fragile.delete(id)
    this.cancelled.delete(id)
  }

  cancel(id: string | null | undefined): boolean {
    if (!id || !this.fragile.delete(id)) return false
    this.cancelled.add(id)
    return true
  }

  isCancelled(id: string): boolean {
    return this.cancelled.has(id)
  }

  forget(id: string) {
    this.fragile.delete(id)
    this.cancelled.delete(id)
  }
}
