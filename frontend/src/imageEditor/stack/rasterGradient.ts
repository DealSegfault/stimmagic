import type { Color, Point } from '../ported/geometry'
import type { GradientPaint } from '../ported/shapeTypes'

export interface RasterGradientStop {
  offset: number
  color: Color
}

const FALLBACK_COLORS: Color[] = [
  { r: 0, g: 0, b: 0, a: 1 },
  { r: 255, g: 255, b: 255, a: 1 },
]

/** Evenly distributed stops in the order the next gradient gesture uses. */
export function rasterGradientStops(
  paint: GradientPaint | null | undefined,
  reverse = false,
): RasterGradientStop[] {
  const authored = paint?.colors?.length ? paint.colors : FALLBACK_COLORS
  const colors = (reverse ? [...authored].reverse() : authored).map(color => ({ ...color }))
  if (colors.length === 1) colors.push({ ...colors[0] })
  return colors.map((color, index) => ({
    offset: index / (colors.length - 1),
    color,
  }))
}

/** A Photoshop-style reflected ramp: end color at both edges, start at center. */
export function reflectedGradientStops(
  paint: GradientPaint | null | undefined,
  reverse = false,
): RasterGradientStop[] {
  const oneWay = rasterGradientStops(paint, reverse)
  return [
    ...[...oneWay].reverse().map(stop => ({
      offset: (1 - stop.offset) / 2,
      color: { ...stop.color },
    })),
    ...oneWay.slice(1).map(stop => ({
      offset: 0.5 + stop.offset / 2,
      color: { ...stop.color },
    })),
  ]
}

/** Shift constrains a gradient drag to the nearest 45° without changing length. */
export function constrainedGradientEnd(start: Point, end: Point, constrain: boolean): Point {
  if (!constrain) return { ...end }
  const dx = end.x - start.x
  const dy = end.y - start.y
  const length = Math.hypot(dx, dy)
  if (length === 0) return { ...end }
  const snapped = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4)
  return {
    x: start.x + Math.cos(snapped) * length,
    y: start.y + Math.sin(snapped) * length,
  }
}

/** Sample an evenly spaced multi-stop spectrum for the diamond renderer. */
export function sampleRasterGradient(stops: RasterGradientStop[], value: number): Color {
  const t = Math.min(1, Math.max(0, value))
  const rightIndex = stops.findIndex(stop => stop.offset >= t)
  if (rightIndex <= 0) return { ...(stops[Math.max(0, rightIndex)]?.color ?? FALLBACK_COLORS[0]) }
  const left = stops[rightIndex - 1]
  const right = stops[rightIndex]
  const span = Math.max(1e-6, right.offset - left.offset)
  const mix = (t - left.offset) / span
  const channel = (a: number, b: number) => Math.round(a + (b - a) * mix)
  return {
    r: channel(left.color.r, right.color.r),
    g: channel(left.color.g, right.color.g),
    b: channel(left.color.b, right.color.b),
    a: (left.color.a ?? 1) + ((right.color.a ?? 1) - (left.color.a ?? 1)) * mix,
  }
}
