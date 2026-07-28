/**
 * Copied from packages/image-editor/src/composables/useInteraction.ts, keeping
 * the crop half and dropping pan, zoom and touch.
 *
 * The new editor fits the image to the viewport and does not pan or zoom, so
 * those paths had nowhere to go — worse, the old code moves the crop to stay
 * visually stationary while the view pans, which without a real pan would drag
 * the crop the wrong way on any click that missed a handle. Everything that
 * remains is verbatim: the canvas-space crop rect, the rotation-aware hit test,
 * the aspect-locked corner and edge resize maths, and the ±45° rotation clamp.
 */
import { ref } from 'vue'
import type { Point, Size, ViewTransform } from './geometry'

export interface CropRect {
  /** Centre of the crop in image space, 0-1. */
  x: number
  y: number
  /** Size relative to the image. */
  width: number
  height: number
  /** Locked aspect ratio in PIXEL space, or null for free. */
  aspectRatio: number | null
  /** Crop rotation in radians. */
  rotation?: number
}

export type CropHandle =
  | 'n' | 's' | 'e' | 'w'
  | 'ne' | 'nw' | 'se' | 'sw'
  | 'center' | 'rotation'

export const HIT_TEST = {
  handleRadius: 12,
  rotationRadius: 24,
} as const

/** Distance from the bottom edge to the rotation lollipop, in canvas pixels. */
export const ROTATE_HANDLE_DISTANCE = 30

export const DEFAULT_ASPECT_RATIOS: { label: string; value: number | null }[] = [
  { label: 'Free', value: null },
  { label: 'Original', value: -1 },
  { label: '16:9', value: 16 / 9 },
  { label: '3:2', value: 3 / 2 },
  { label: '4:3', value: 4 / 3 },
  { label: '1:1', value: 1 },
  { label: '3:4', value: 3 / 4 },
  { label: '2:3', value: 2 / 3 },
  { label: '9:16', value: 9 / 16 },
]

function distance(p1: Point, p2: Point): number {
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  return Math.sqrt(dx * dx + dy * dy)
}

export function rotatePoint(px: number, py: number, cx: number, cy: number, angle: number): Point {
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  const dx = px - cx
  const dy = py - cy
  return {
    x: cx + dx * cos - dy * sin,
    y: cy + dx * sin + dy * cos,
  }
}

/** The crop rect in canvas coordinates, centre-based. */
export function cropCanvasRect(
  crop: CropRect,
  transform: ViewTransform,
  imageSize: Size,
  canvasSize: Size
) {
  const { zoom, panX, panY } = transform
  const imgCenterX = canvasSize.width / 2 + panX
  const imgCenterY = canvasSize.height / 2 + panY

  const cx = imgCenterX + (crop.x - 0.5) * imageSize.width * zoom
  const cy = imgCenterY + (crop.y - 0.5) * imageSize.height * zoom
  const w = crop.width * imageSize.width * zoom
  const h = crop.height * imageSize.height * zoom

  return { x: cx - w / 2, y: cy - h / 2, w, h, cx, cy, rotation: crop.rotation ?? 0 }
}

type Interaction =
  | { type: 'idle' }
  | { type: 'dragging'; handle: CropHandle; startRect: CropRect; startMouse: Point }
  | { type: 'rotating'; startAngle: number; startRotation: number }

export function useCropInteraction(
  canvasRef: { value: HTMLCanvasElement | null },
  viewTransform: { value: ViewTransform },
  imageSize: { value: Size | null },
  canvasSize: { value: Size },
  getCrop: () => CropRect,
  onCropChange: (crop: CropRect) => void,
  /** A gesture finished — one undo step. */
  onCommit: () => void
) {
  const interaction = ref<Interaction>({ type: 'idle' })
  const cursorStyle = ref('default')

  function toCanvasPoint(event: MouseEvent): Point | null {
    const canvas = canvasRef.value
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    return { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }

  function canvasRect() {
    if (!imageSize.value) return null
    return cropCanvasRect(getCrop(), viewTransform.value, imageSize.value, canvasSize.value)
  }

  function hitTestCropHandle(canvasPoint: Point): CropHandle | null {
    const cropRect = canvasRect()
    if (!cropRect) return null

    const { w, h, cx, cy, rotation } = cropRect
    const radius = HIT_TEST.handleRadius
    const rotationRadius = HIT_TEST.rotationRadius

    const halfW = w / 2
    const halfH = h / 2

    const corners = {
      nw: rotatePoint(cx - halfW, cy - halfH, cx, cy, rotation),
      ne: rotatePoint(cx + halfW, cy - halfH, cx, cy, rotation),
      se: rotatePoint(cx + halfW, cy + halfH, cx, cy, rotation),
      sw: rotatePoint(cx - halfW, cy + halfH, cx, cy, rotation),
    }

    // The lollipop hangs perpendicular to the bottom edge, so it follows the
    // crop around as it rotates rather than staying below the image.
    const bottomCenterX = (corners.sw.x + corners.se.x) / 2
    const bottomCenterY = (corners.sw.y + corners.se.y) / 2
    const edgeX = corners.se.x - corners.sw.x
    const edgeY = corners.se.y - corners.sw.y
    const edgeLen = Math.sqrt(edgeX * edgeX + edgeY * edgeY)
    const perpX = -edgeY / edgeLen
    const perpY = edgeX / edgeLen
    const rotateHandleX = bottomCenterX + perpX * ROTATE_HANDLE_DISTANCE
    const rotateHandleY = bottomCenterY + perpY * ROTATE_HANDLE_DISTANCE

    if (distance(canvasPoint, { x: rotateHandleX, y: rotateHandleY }) < rotationRadius) {
      return 'rotation'
    }

    if (distance(canvasPoint, corners.nw) < radius) return 'nw'
    if (distance(canvasPoint, corners.ne) < radius) return 'ne'
    if (distance(canvasPoint, corners.sw) < radius) return 'sw'
    if (distance(canvasPoint, corners.se) < radius) return 'se'

    const localPoint = rotatePoint(canvasPoint.x, canvasPoint.y, cx, cy, -rotation)
    if (localPoint.x >= cx - halfW && localPoint.x <= cx + halfW &&
        localPoint.y >= cy - halfH && localPoint.y <= cy + halfH) {
      return 'center'
    }

    return null
  }

  function getCropCursor(handle: CropHandle | null): string {
    if (!handle) return 'default'
    switch (handle) {
      case 'n': case 's': return 'ns-resize'
      case 'e': case 'w': return 'ew-resize'
      case 'ne': case 'sw': return 'nesw-resize'
      case 'nw': case 'se': return 'nwse-resize'
      case 'center': return 'move'
      case 'rotation': return 'grab'
      default: return 'default'
    }
  }

  function handleCropDrag(
    canvasPoint: Point,
    state: { handle: CropHandle; startRect: CropRect; startMouse: Point },
    shiftKey: boolean
  ) {
    if (!imageSize.value) return

    const { zoom } = viewTransform.value
    const imgSize = imageSize.value

    const dx = (canvasPoint.x - state.startMouse.x) / (imgSize.width * zoom)
    const dy = (canvasPoint.y - state.startMouse.y) / (imgSize.height * zoom)

    const newCrop = { ...state.startRect }
    const { handle } = state

    if (handle === 'center') {
      newCrop.x = state.startRect.x + dx
      newCrop.y = state.startRect.y + dy
    } else {
      // aspectRatio is in pixel space but the maths runs in normalized coords,
      // so it is divided through by the image's own aspect ratio.
      const imageAR = imgSize.width / imgSize.height
      const pixelAR = newCrop.aspectRatio ?? (shiftKey
        ? (state.startRect.width * imgSize.width) / (state.startRect.height * imgSize.height)
        : null)
      const aspectRatio = pixelAR ? pixelAR / imageAR : null

      const isCorner = handle.length === 2
      const hasNorth = handle.includes('n')
      const hasSouth = handle.includes('s')
      const hasWest = handle.includes('w')
      const hasEast = handle.includes('e')

      const startLeft = state.startRect.x - state.startRect.width / 2
      const startRight = state.startRect.x + state.startRect.width / 2
      const startTop = state.startRect.y - state.startRect.height / 2
      const startBottom = state.startRect.y + state.startRect.height / 2

      const draggedX = hasWest ? startLeft + dx : hasEast ? startRight + dx : null
      const draggedY = hasNorth ? startTop + dy : hasSouth ? startBottom + dy : null

      let newLeft = startLeft
      let newRight = startRight
      let newTop = startTop
      let newBottom = startBottom

      if (aspectRatio && isCorner) {
        // Project the mouse onto the aspect diagonal from the fixed corner,
        // which is what makes a locked corner drag track the pointer instead
        // of snapping between the two axes.
        const fixedX = hasWest ? startRight : startLeft
        const fixedY = hasNorth ? startBottom : startTop

        const relX = draggedX! - fixedX
        const relY = draggedY! - fixedY

        const signX = hasEast ? 1 : -1
        const signY = hasSouth ? 1 : -1

        const ar = aspectRatio
        const t = (signX * ar * relX + signY * relY) / (ar * ar + 1)

        const clampedT = Math.max(0.05, Math.abs(t)) * Math.sign(t || 1)
        const newWidth = Math.abs(ar * clampedT)
        const newHeight = Math.abs(clampedT)

        if (hasEast) {
          newLeft = fixedX
          newRight = fixedX + newWidth
        } else {
          newRight = fixedX
          newLeft = fixedX - newWidth
        }
        if (hasSouth) {
          newTop = fixedY
          newBottom = fixedY + newHeight
        } else {
          newBottom = fixedY
          newTop = fixedY - newHeight
        }
      } else if (aspectRatio && !isCorner) {
        // Edge drag with a locked ratio: the dragged edge moves and the
        // perpendicular pair expands symmetrically about the centre.
        if (hasNorth) {
          newTop = startTop + dy
          const newHeight = newBottom - newTop
          const newWidth = newHeight * aspectRatio
          const centerX = (newLeft + newRight) / 2
          newLeft = centerX - newWidth / 2
          newRight = centerX + newWidth / 2
        } else if (hasSouth) {
          newBottom = startBottom + dy
          const newHeight = newBottom - newTop
          const newWidth = newHeight * aspectRatio
          const centerX = (newLeft + newRight) / 2
          newLeft = centerX - newWidth / 2
          newRight = centerX + newWidth / 2
        } else if (hasWest) {
          newLeft = startLeft + dx
          const newWidth = newRight - newLeft
          const newHeight = newWidth / aspectRatio
          const centerY = (newTop + newBottom) / 2
          newTop = centerY - newHeight / 2
          newBottom = centerY + newHeight / 2
        } else if (hasEast) {
          newRight = startRight + dx
          const newWidth = newRight - newLeft
          const newHeight = newWidth / aspectRatio
          const centerY = (newTop + newBottom) / 2
          newTop = centerY - newHeight / 2
          newBottom = centerY + newHeight / 2
        }
      } else {
        if (hasNorth) newTop = startTop + dy
        if (hasSouth) newBottom = startBottom + dy
        if (hasWest) newLeft = startLeft + dx
        if (hasEast) newRight = startRight + dx
      }

      const newWidth = newRight - newLeft
      const newHeight = newBottom - newTop

      if (newWidth > 0.05 && newHeight > 0.05) {
        newCrop.width = newWidth
        newCrop.height = newHeight
        newCrop.x = (newLeft + newRight) / 2
        newCrop.y = (newTop + newBottom) / 2
      }
    }

    onCropChange(newCrop)
  }

  function handleCropRotate(
    canvasPoint: Point,
    state: { startAngle: number; startRotation: number }
  ) {
    const cropRect = canvasRect()
    if (!cropRect) return

    const { cx, cy } = cropRect
    const currentAngle = Math.atan2(canvasPoint.y - cy, canvasPoint.x - cx)
    const deltaAngle = currentAngle - state.startAngle

    // Straightening, not free rotation: past 45° the crop would be better
    // described by a quarter turn, which is a separate control.
    let newRotation = state.startRotation + deltaAngle
    const maxRotation = Math.PI / 4
    newRotation = Math.max(-maxRotation, Math.min(maxRotation, newRotation))

    onCropChange({ ...getCrop(), rotation: newRotation })
  }

  function handleMouseDown(event: MouseEvent) {
    if (event.button !== 0) return
    const canvasPoint = toCanvasPoint(event)
    if (!canvasPoint) return

    const handle = hitTestCropHandle(canvasPoint)
    if (!handle) return
    event.preventDefault()

    if (handle === 'rotation') {
      const cropRect = canvasRect()
      if (!cropRect) return
      const { cx, cy } = cropRect
      interaction.value = {
        type: 'rotating',
        startAngle: Math.atan2(canvasPoint.y - cy, canvasPoint.x - cx),
        startRotation: getCrop().rotation ?? 0,
      }
      cursorStyle.value = 'grabbing'
      return
    }

    interaction.value = {
      type: 'dragging',
      handle,
      startRect: { ...getCrop() },
      startMouse: canvasPoint,
    }
    cursorStyle.value = getCropCursor(handle)
  }

  function handleMouseMove(event: MouseEvent) {
    const canvasPoint = toCanvasPoint(event)
    if (!canvasPoint) return
    const state = interaction.value

    if (state.type === 'dragging') handleCropDrag(canvasPoint, state, event.shiftKey)
    else if (state.type === 'rotating') handleCropRotate(canvasPoint, state)
    else cursorStyle.value = getCropCursor(hitTestCropHandle(canvasPoint))
  }

  function handleMouseUp() {
    if (interaction.value.type === 'idle') return
    interaction.value = { type: 'idle' }
    cursorStyle.value = 'default'
    onCommit()
  }

  function setupListeners() {
    const canvas = canvasRef.value
    if (!canvas) return
    canvas.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  function cleanupListeners() {
    const canvas = canvasRef.value
    if (canvas) canvas.removeEventListener('mousedown', handleMouseDown)
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', handleMouseUp)
  }

  return { interaction, cursorStyle, setupListeners, cleanupListeners, hitTestCropHandle }
}
