import assert from 'node:assert/strict'
import test from 'node:test'

import {
  boundsBetween,
  moveShapesFromSnapshots,
  shapeIdsInMarquee,
} from '../ported/annotationSelection.ts'
import type { PathShape, RectangleShape, Shape } from '../ported/shapeTypes.ts'

const imageSize = { width: 1000, height: 500 }

function shapeBounds(shape: Shape) {
  if (shape.type === 'rectangle') {
    return { x: shape.x, y: shape.y, width: shape.width, height: shape.height }
  }
  if (shape.type === 'path') {
    const xs = shape.points.map(point => point.x)
    const ys = shape.points.map(point => point.y)
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
    }
  }
  throw new Error(`Unsupported test shape: ${shape.type}`)
}

function shapeCenter(shape: Shape) {
  if (shape.type === 'rectangle') {
    return { x: shape.x + shape.width / 2, y: shape.y + shape.height / 2 }
  }
  return { x: shape.x, y: shape.y }
}

function moveShape(shape: Shape, dx: number, dy: number): Partial<Shape> {
  if (shape.type === 'path') {
    return {
      x: shape.x + dx,
      y: shape.y + dy,
      points: shape.points.map(point => ({ x: point.x + dx, y: point.y + dy })),
    }
  }
  return { x: shape.x + dx, y: shape.y + dy }
}

function rectangle(
  id: string,
  x: number,
  y: number,
  width: number,
  height: number,
  rotation = 0
): RectangleShape {
  return {
    id,
    type: 'rectangle',
    x,
    y,
    width,
    height,
    rotation,
    opacity: 1,
  }
}

test('marquee bounds normalize a drag in any direction', () => {
  const bounds = boundsBetween({ x: 0.8, y: 0.7 }, { x: 0.2, y: 0.1 })
  assert.equal(bounds.x, 0.2)
  assert.equal(bounds.y, 0.1)
  assert.ok(Math.abs(bounds.width - 0.6) < 1e-9)
  assert.ok(Math.abs(bounds.height - 0.6) < 1e-9)
})

test('a marquee selects every intersecting selectable annotation in draw order', () => {
  const shapes: Shape[] = [
    rectangle('inside-a', 0.1, 0.1, 0.1, 0.1),
    rectangle('outside', 0.75, 0.75, 0.1, 0.1),
    rectangle('inside-b', 0.3, 0.2, 0.2, 0.15),
    { ...rectangle('locked', 0.2, 0.2, 0.1, 0.1), disableSelect: true },
  ]

  assert.deepEqual(
    shapeIdsInMarquee(
      shapes,
      { x: 0.05, y: 0.05 },
      { x: 0.55, y: 0.5 },
      imageSize,
      shapeBounds,
      shapeCenter
    ),
    ['inside-a', 'inside-b']
  )
})

test('a marquee may start on the matte and enter the image', () => {
  const shapes = [
    rectangle('left', 0.05, 0.2, 0.15, 0.2),
    rectangle('right', 0.75, 0.2, 0.15, 0.2),
  ]

  assert.deepEqual(
    shapeIdsInMarquee(
      shapes,
      { x: -0.4, y: 0.1 },
      { x: 0.4, y: 0.6 },
      imageSize,
      shapeBounds,
      shapeCenter,
    ),
    ['left'],
  )
})

test('marquee hit testing follows rotated bounds on a non-square image', () => {
  const rotated = rectangle('rotated', 0.45, 0.4, 0.2, 0.1, Math.PI / 2)

  assert.deepEqual(
    shapeIdsInMarquee(
      [rotated],
      { x: 0.53, y: 0.3 },
      { x: 0.54, y: 0.35 },
      imageSize,
      shapeBounds,
      shapeCenter
    ),
    ['rotated']
  )
})

test('group movement updates anchor and point-based shapes from their snapshots', () => {
  const rect = rectangle('rect', 0.1, 0.2, 0.2, 0.1)
  const path: PathShape = {
    id: 'path',
    type: 'path',
    x: 0.3,
    y: 0.4,
    rotation: 0,
    opacity: 1,
    points: [{ x: 0.3, y: 0.4 }, { x: 0.35, y: 0.45 }],
    strokeColor: { r: 255, g: 255, b: 255, a: 1 },
    strokeWidth: 4,
  }

  const moved = moveShapesFromSnapshots(
    [rect, path],
    { rect, path },
    0.1,
    -0.05,
    moveShape
  )

  assert.deepEqual(
    moved.map(shape => [shape.id, shape.x, shape.y]),
    [['rect', 0.2, 0.15000000000000002], ['path', 0.4, 0.35000000000000003]]
  )
  assert.deepEqual((moved[1] as PathShape).points, [
    { x: 0.4, y: 0.35000000000000003 },
    { x: 0.44999999999999996, y: 0.4 },
  ])
})
