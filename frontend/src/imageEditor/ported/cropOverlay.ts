/**
 * Copied from `drawCropOverlay` in
 * packages/image-editor/src/components/EditorCanvas.vue.
 *
 * The look is the whole point: everything outside the crop dims via an
 * even-odd fill, the kept region stays bright, a dashed blue border and a
 * rule-of-thirds grid follow the rotation, and the rotation lollipop hangs
 * perpendicular to the bottom edge so it travels with the crop. Extracted from
 * the component only because it was a private function inside a renderer this
 * editor does not use.
 */
import type { Size, ViewTransform } from './geometry'
import type { CropRect } from './useCropInteraction'
import { ROTATE_HANDLE_DISTANCE } from './useCropInteraction'

const BORDER = '#3b82f6'
const GUIDE_LINE = 'rgba(255, 255, 255, 0.5)'
const MASK = 'rgba(0, 0, 0, 0.55)'

export function drawCropOverlay(
  ctx: CanvasRenderingContext2D,
  crop: CropRect,
  transform: ViewTransform,
  imageSize: Size,
  canvasSize: Size,
  /** Rectangle still, image moving — see cropCanvasRect. */
  pinned = false
) {
  const { zoom, panX, panY } = transform
  // Pinned, the rectangle never turns: the tilt is carried by the image drawn
  // behind it, which is what makes straightening legible.
  const cropRotation = pinned ? 0 : (crop.rotation ?? 0)

  const imgCenterX = canvasSize.width / 2 + panX
  const imgCenterY = canvasSize.height / 2 + panY

  const cropCenterX = pinned
    ? canvasSize.width / 2
    : imgCenterX + (crop.x - 0.5) * imageSize.width * zoom
  const cropCenterY = pinned
    ? canvasSize.height / 2
    : imgCenterY + (crop.y - 0.5) * imageSize.height * zoom
  const cropW = crop.width * imageSize.width * zoom
  const cropH = crop.height * imageSize.height * zoom

  const rotatePoint = (px: number, py: number) => {
    const cos = Math.cos(cropRotation)
    const sin = Math.sin(cropRotation)
    const dx = px - cropCenterX
    const dy = py - cropCenterY
    return {
      x: cropCenterX + dx * cos - dy * sin,
      y: cropCenterY + dx * sin + dy * cos,
    }
  }

  const halfW = cropW / 2
  const halfH = cropH / 2
  const corners = [
    rotatePoint(cropCenterX - halfW, cropCenterY - halfH), // NW
    rotatePoint(cropCenterX + halfW, cropCenterY - halfH), // NE
    rotatePoint(cropCenterX + halfW, cropCenterY + halfH), // SE
    rotatePoint(cropCenterX - halfW, cropCenterY + halfH), // SW
  ]

  // Dim everything outside the crop: one path, outer rect clockwise and the
  // crop counter-clockwise, filled even-odd.
  ctx.save()
  ctx.fillStyle = MASK
  ctx.beginPath()
  ctx.rect(0, 0, canvasSize.width, canvasSize.height)
  ctx.moveTo(corners[0].x, corners[0].y)
  ctx.lineTo(corners[3].x, corners[3].y)
  ctx.lineTo(corners[2].x, corners[2].y)
  ctx.lineTo(corners[1].x, corners[1].y)
  ctx.closePath()
  ctx.fill('evenodd')
  ctx.restore()

  ctx.strokeStyle = BORDER
  ctx.lineWidth = 2
  ctx.setLineDash([6, 4])
  ctx.beginPath()
  ctx.moveTo(corners[0].x, corners[0].y)
  ctx.lineTo(corners[1].x, corners[1].y)
  ctx.lineTo(corners[2].x, corners[2].y)
  ctx.lineTo(corners[3].x, corners[3].y)
  ctx.closePath()
  ctx.stroke()
  ctx.setLineDash([])

  ctx.strokeStyle = GUIDE_LINE
  ctx.lineWidth = 1

  const lerp = (p1: { x: number; y: number }, p2: { x: number; y: number }, t: number) => ({
    x: p1.x + (p2.x - p1.x) * t,
    y: p1.y + (p2.y - p1.y) * t,
  })

  ctx.beginPath()
  for (const t of [1 / 3, 2 / 3]) {
    const top = lerp(corners[0], corners[1], t)
    const bottom = lerp(corners[3], corners[2], t)
    ctx.moveTo(top.x, top.y)
    ctx.lineTo(bottom.x, bottom.y)
  }
  for (const t of [1 / 3, 2 / 3]) {
    const left = lerp(corners[0], corners[3], t)
    const right = lerp(corners[1], corners[2], t)
    ctx.moveTo(left.x, left.y)
    ctx.lineTo(right.x, right.y)
  }
  ctx.stroke()

  // Centre cross, rotated with the crop — the cue that tells you the crop is
  // off-axis even when the content has no straight lines in it.
  const centerSize = 8
  const cos = Math.cos(cropRotation)
  const sin = Math.sin(cropRotation)

  ctx.beginPath()
  ctx.moveTo(cropCenterX - centerSize * cos, cropCenterY - centerSize * sin)
  ctx.lineTo(cropCenterX + centerSize * cos, cropCenterY + centerSize * sin)
  ctx.moveTo(cropCenterX + centerSize * sin, cropCenterY - centerSize * cos)
  ctx.lineTo(cropCenterX - centerSize * sin, cropCenterY + centerSize * cos)
  ctx.stroke()

  const handleRadius = 7
  const rotateHandleRadius = 7

  const bottomCenter = lerp(corners[3], corners[2], 0.5)
  const edgeX = corners[2].x - corners[3].x
  const edgeY = corners[2].y - corners[3].y
  const edgeLen = Math.sqrt(edgeX * edgeX + edgeY * edgeY)
  const perpX = -edgeY / edgeLen
  const perpY = edgeX / edgeLen

  const rotateHandleX = bottomCenter.x + perpX * ROTATE_HANDLE_DISTANCE
  const rotateHandleY = bottomCenter.y + perpY * ROTATE_HANDLE_DISTANCE

  ctx.strokeStyle = BORDER
  ctx.lineWidth = 2
  ctx.setLineDash([4, 3])
  ctx.beginPath()
  ctx.moveTo(bottomCenter.x, bottomCenter.y)
  ctx.lineTo(rotateHandleX, rotateHandleY)
  ctx.stroke()
  ctx.setLineDash([])

  ctx.fillStyle = '#ffffff'
  ctx.strokeStyle = BORDER
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.arc(rotateHandleX, rotateHandleY, rotateHandleRadius, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()

  for (const corner of corners) {
    ctx.beginPath()
    ctx.arc(corner.x, corner.y, handleRadius, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
  }
}
