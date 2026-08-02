export type EditRowKeyboardCommand =
  | { type: 'move-row'; indexDelta: -1 | 1 }
  | { type: 'move-candidate'; candidateDelta: -1 | 1 }
  | { type: 'toggle' }
  | { type: 'remove' }

/**
 * Only the row itself owns list shortcuts.
 *
 * Looking up an ancestor here would make a textarea, candidate, or row button
 * borrow the row's destructive shortcuts when its own key event bubbles.
 */
export function directEditRowId(target: EventTarget | null): string | null {
  if (!target || typeof target !== 'object') return null
  const element = target as EventTarget & {
    dataset?: { opId?: string }
    matches?: (selector: string) => boolean
  }
  if (typeof element.matches !== 'function' || !element.matches('[data-op-id]')) return null
  return element.dataset?.opId || null
}

/** Map row-owned keys to stack commands; document indices run opposite the UI. */
export function editRowKeyboardCommand(key: string): EditRowKeyboardCommand | null {
  if (key === 'ArrowDown') return { type: 'move-row', indexDelta: -1 }
  if (key === 'ArrowUp') return { type: 'move-row', indexDelta: 1 }
  if (key === 'ArrowRight') return { type: 'move-candidate', candidateDelta: 1 }
  if (key === 'ArrowLeft') return { type: 'move-candidate', candidateDelta: -1 }
  if (key === ' ' || key === 'Spacebar') return { type: 'toggle' }
  if (key === 'Delete' || key === 'Backspace') return { type: 'remove' }
  return null
}

/**
 * Pick the adjacent candidate while focus stays on the row. An unpicked strip
 * enters from the edge matching the arrow direction.
 */
export function rowCandidateIndex(
  count: number,
  current: number,
  delta: -1 | 1,
): number {
  if (count <= 0) return -1
  if (current < 0) return delta > 0 ? 0 : count - 1
  return Math.max(0, Math.min(count - 1, current + delta))
}
