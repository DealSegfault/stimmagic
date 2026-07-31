import type { Point } from './geometry'

/**
 * Get brush dabs along a stroke path at a fixed spatial interval.
 *
 * The endpoint is intentionally omitted when it does not complete another
 * interval. The caller retains the last returned dab so short pointer movements
 * accumulate instead of changing effect strength with event frequency.
 */
export function getStrokePoints(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  spacing: number,
): Point[] {
  const points: Point[] = []
  const dx = endX - startX
  const dy = endY - startY
  const distance = Math.sqrt(dx * dx + dy * dy)
  const interval = Math.max(0.01, spacing)

  if (distance < interval) return points

  const steps = Math.floor(distance / interval)
  for (let i = 1; i <= steps; i++) {
    const t = (i * interval) / distance
    points.push({
      x: startX + dx * t,
      y: startY + dy * t,
    })
  }

  return points
}

export function advanceStroke(
  lastDab: Point | null,
  point: Point,
  spacing: number,
): { points: Point[]; lastDab: Point } {
  if (!lastDab) return { points: [point], lastDab: { ...point } }

  const points = getStrokePoints(
    lastDab.x,
    lastDab.y,
    point.x,
    point.y,
    spacing,
  )
  return {
    points,
    lastDab: points.length ? { ...points[points.length - 1] } : lastDab,
  }
}
