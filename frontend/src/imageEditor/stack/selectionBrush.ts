import type { Point } from '../ported/geometry'

export type SelectionBrushMode = 'add' | 'subtract'

/**
 * Paint one soft brush segment into an RGBA selection-mask region.
 *
 * Selection coverage is a set operation, not paint opacity: add keeps the
 * greatest coverage and subtract keeps the least remaining coverage. Both
 * operations are therefore idempotent when the brush crosses the same pixels.
 */
export function applySelectionBrushSegment(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  from: Point | null,
  to: Point,
  radius: number,
  hardness: number,
  mode: SelectionBrushMode,
): void {
  if (radius <= 0 || width <= 0 || height <= 0) return

  const start = from ?? to
  const dx = to.x - start.x
  const dy = to.y - start.y
  const lengthSquared = dx * dx + dy * dy
  const innerRadius = radius * Math.min(1, Math.max(0, hardness))
  const featherWidth = Math.max(Number.EPSILON, radius - innerRadius)

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const pixelX = x + 0.5
      const pixelY = y + 0.5
      const projection = lengthSquared === 0
        ? 0
        : Math.min(1, Math.max(
          0,
          ((pixelX - start.x) * dx + (pixelY - start.y) * dy) / lengthSquared,
        ))
      const nearestX = start.x + dx * projection
      const nearestY = start.y + dy * projection
      const distance = Math.hypot(pixelX - nearestX, pixelY - nearestY)
      if (distance >= radius) continue

      const coverage = distance <= innerRadius
        ? 255
        : Math.round(255 * (radius - distance) / featherWidth)
      const alphaOffset = (y * width + x) * 4 + 3
      const previous = pixels[alphaOffset]
      const next = mode === 'subtract'
        ? Math.min(previous, 255 - coverage)
        : Math.max(previous, coverage)
      pixels[alphaOffset - 3] = 255
      pixels[alphaOffset - 2] = 255
      pixels[alphaOffset - 1] = 255
      pixels[alphaOffset] = next
    }
  }
}
