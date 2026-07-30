/** Clamp keyboard movement to the available candidate strip. */
export function adjacentCandidateIndex(
  count: number,
  current: number,
  delta: -1 | 1,
): number {
  if (count <= 0) return -1
  return Math.max(0, Math.min(count - 1, current + delta))
}

/** The two familiar key pairs used to scrub horizontally through results. */
export function candidateNavigationDelta(key: string): -1 | 1 | null {
  const normalized = key.toLowerCase()
  if (normalized === 'arrowleft' || normalized === 'a') return -1
  if (normalized === 'arrowright' || normalized === 'd') return 1
  return null
}
