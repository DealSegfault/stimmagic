import type { Point, Size } from './geometry.ts'
import type { Shape } from './shapeTypes.ts'

export interface AnnotationBounds {
  x: number
  y: number
  width: number
  height: number
}

export function boundsBetween(start: Point, end: Point): AnnotationBounds {
  return {
    x: Math.min(start.x, end.x),
    y: Math.min(start.y, end.y),
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  }
}

/**
 * Axis-aligned image-space bounds after applying the shape's rotation.
 *
 * Rotation has to happen in pixels: normalized x/y coordinates have different
 * scales on a non-square image, so rotating directly in 0-1 space skews the
 * marquee hit area away from the shape the person sees.
 */
export function rotatedBounds(
  bounds: AnnotationBounds,
  center: Point,
  rotation: number,
  imageSize: Size
): AnnotationBounds {
  if (!rotation) return bounds

  const centerX = center.x * imageSize.width
  const centerY = center.y * imageSize.height
  const cos = Math.cos(rotation)
  const sin = Math.sin(rotation)
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  const corners: Point[] = [
    { x: bounds.x, y: bounds.y },
    { x: bounds.x + bounds.width, y: bounds.y },
    { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
    { x: bounds.x, y: bounds.y + bounds.height },
  ]
  for (const corner of corners) {
    const dx = corner.x * imageSize.width - centerX
    const dy = corner.y * imageSize.height - centerY
    const x = centerX + dx * cos - dy * sin
    const y = centerY + dx * sin + dy * cos
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
  }

  return {
    x: minX / imageSize.width,
    y: minY / imageSize.height,
    width: (maxX - minX) / imageSize.width,
    height: (maxY - minY) / imageSize.height,
  }
}

export function boundsIntersect(a: AnnotationBounds, b: AnnotationBounds): boolean {
  return (
    a.x <= b.x + b.width &&
    a.x + a.width >= b.x &&
    a.y <= b.y + b.height &&
    a.y + a.height >= b.y
  )
}

/** IDs in drawing order, so the last ID is the natural primary selection. */
export function shapeIdsInMarquee(
  shapes: Shape[],
  start: Point,
  end: Point,
  imageSize: Size,
  getBounds: (shape: Shape) => AnnotationBounds,
  getCenter: (shape: Shape) => Point
): string[] {
  const marquee = boundsBetween(start, end)
  return shapes
    .filter(shape =>
      !shape.disableSelect &&
      boundsIntersect(
        marquee,
        rotatedBounds(getBounds(shape), getCenter(shape), shape.rotation || 0, imageSize)
      )
    )
    .map(shape => shape.id)
}

/**
 * Move any number of active shapes from immutable gesture-start snapshots.
 *
 * The keys are the live IDs being moved. During Option-drag those are copy
 * IDs, while the snapshot values still describe the original group.
 */
export function moveShapesFromSnapshots(
  shapes: Shape[],
  snapshotsByActiveId: Record<string, Shape>,
  dx: number,
  dy: number,
  move: (shape: Shape, dx: number, dy: number) => Partial<Shape>
): Shape[] {
  return shapes.map(shape => {
    const original = snapshotsByActiveId[shape.id]
    return original
      ? { ...shape, ...move(original, dx, dy) } as Shape
      : shape
  })
}
