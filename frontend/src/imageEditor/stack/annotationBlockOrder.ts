export interface AnnotationOrderItem {
  id: string
  annotate: boolean
}

/**
 * Move selected annotation rows as one block to an annotation edge.
 *
 * The selected rows retain their document order. Non-annotation rows retain
 * their order too; they move only as a consequence of the block crossing the
 * first or last unselected annotation peer.
 */
export function annotationBlockOrder(
  items: AnnotationOrderItem[],
  selectedIds: Iterable<string>,
  edge: 'front' | 'back'
): string[] | null {
  const requested = new Set(selectedIds)
  const selected = items.filter(item => item.annotate && requested.has(item.id))
  if (!selected.length) return null

  const selectedSet = new Set(selected.map(item => item.id))
  const annotationIds = items.filter(item => item.annotate).map(item => item.id)
  const selectedIdsInOrder = selected.map(item => item.id)
  const edgeIds = edge === 'back'
    ? annotationIds.slice(0, selected.length)
    : annotationIds.slice(-selected.length)
  if (edgeIds.every((id, index) => id === selectedIdsInOrder[index])) return null

  const stationary = items.filter(item => !selectedSet.has(item.id))
  const annotationIndexes = stationary.flatMap((item, index) =>
    item.annotate ? [index] : []
  )
  if (!annotationIndexes.length) return null

  const insertAt = edge === 'back'
    ? annotationIndexes[0]
    : annotationIndexes[annotationIndexes.length - 1] + 1
  const next = [
    ...stationary.slice(0, insertAt),
    ...selected,
    ...stationary.slice(insertAt),
  ].map(item => item.id)
  const current = items.map(item => item.id)
  return current.every((id, index) => id === next[index]) ? null : next
}
