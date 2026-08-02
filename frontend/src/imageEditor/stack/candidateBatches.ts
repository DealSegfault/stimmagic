export interface PendingCandidateBatch {
  batchId: string
  count: number
}

export interface CandidateBatch<T> {
  id: string
  candidates: T[]
  pendingCount: number
}

const LEGACY_BATCH_ID = 'legacy-candidates'

/**
 * Keep every paid generation invocation visually distinct.
 *
 * Older documents have no batch id, so all of their candidates remain in one
 * compatibility row. New candidates carry the invocation id that created
 * them, and pending slots join that same row while results arrive.
 */
export function groupCandidateBatches<T extends { batchId?: string | null }>(
  candidates: T[],
  pending: PendingCandidateBatch[] = [],
): CandidateBatch<T>[] {
  const batches: CandidateBatch<T>[] = []
  const byId = new Map<string, CandidateBatch<T>>()

  function batch(id: string): CandidateBatch<T> {
    const existing = byId.get(id)
    if (existing) return existing
    const created = { id, candidates: [], pendingCount: 0 }
    byId.set(id, created)
    batches.push(created)
    return created
  }

  for (const candidate of candidates) {
    batch(candidate.batchId || LEGACY_BATCH_ID).candidates.push(candidate)
  }
  for (const item of pending) {
    if (item.count <= 0) continue
    batch(item.batchId).pendingCount += item.count
  }

  return batches
}
