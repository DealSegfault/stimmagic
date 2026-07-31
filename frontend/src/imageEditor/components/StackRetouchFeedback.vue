<script setup lang="ts">
/**
 * Read-only Retouch feedback above the image.
 *
 * Hover is a quiet boundary; selection adds an indigo wash and, for
 * source-based repairs, source/destination pins. Patch also repeats the
 * destination mask over its donor area with a dotted boundary, so both region
 * shapes remain legible after the selection itself has been consumed.
 * It never owns pointer input.
 */
import { onMounted, ref, watch } from 'vue'

interface FeedbackRegion {
  mask: HTMLCanvasElement
  source?: { x: number; y: number } | null
  target?: { x: number; y: number } | null
  isPatch?: boolean
}

const props = defineProps<{
  allRegions?: FeedbackRegion[]
  selectedMask?: HTMLCanvasElement | null
  hoveredMask?: HTMLCanvasElement | null
  sourcePoint?: { x: number; y: number } | null
  targetPoint?: { x: number; y: number } | null
  hoveredSourcePoint?: { x: number; y: number } | null
  hoveredTargetPoint?: { x: number; y: number } | null
  selectedIsPatch?: boolean
  hoveredIsPatch?: boolean
  displayWidth: number
  displayHeight: number
}>()

const canvas = ref<HTMLCanvasElement | null>(null)

function selectionRgb(): [number, number, number] {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue('--color-selection-rgb')
    .trim()
    .split(/\s+/)
    .map(Number)
  return raw.length === 3 && raw.every(Number.isFinite)
    ? [raw[0], raw[1], raw[2]]
    : [99, 102, 241]
}

function paintMask(
  ctx: CanvasRenderingContext2D,
  mask: HTMLCanvasElement,
  fillAlpha: number,
  edgeAlpha: number,
  options: {
    offset?: { x: number; y: number }
    dotted?: boolean
  } = {},
) {
  const width = mask.width
  const height = mask.height
  const source = mask.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, width, height)
  const overlayCanvas = document.createElement('canvas')
  overlayCanvas.width = width
  overlayCanvas.height = height
  const overlayCtx = overlayCanvas.getContext('2d')!
  const overlay = overlayCtx.createImageData(width, height)
  const [r, g, b] = selectionRgb()
  // Soft repair masks often reach their crop boundary at alpha 1/255. Using
  // that feather alpha for the outline made hover feedback mathematically
  // present but visually absent. The boundary is UI, not compositing data:
  // threshold it and draw it at a stable opacity.
  const boundaryThreshold = 12
  // Keep the dotted donor boundary approximately stable in screen pixels,
  // even when a large authored image is fitted down into the viewport.
  const displayScale = width / Math.max(1, props.displayWidth)
  const dotPeriod = Math.max(6, Math.round(8 * displayScale))
  const dotLength = Math.max(2, Math.round(3 * displayScale))
  const maskAlpha = (x: number, y: number) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return 0
    return source.data[(y * width + x) * 4 + 3]
  }

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const pixel = y * width + x
      const alpha = source.data[pixel * 4 + 3]
      if (alpha < boundaryThreshold) continue
      // Two native pixels survive normal image-to-viewport downscaling much
      // better than a one-pixel contour, without turning into a heavy halo.
      const edge =
        maskAlpha(x - 2, y) < boundaryThreshold
        || maskAlpha(x + 2, y) < boundaryThreshold
        || maskAlpha(x, y - 2) < boundaryThreshold
        || maskAlpha(x, y + 2) < boundaryThreshold
      overlay.data[pixel * 4] = r
      overlay.data[pixel * 4 + 1] = g
      overlay.data[pixel * 4 + 2] = b
      const showEdge = !options.dotted || ((x + y) % dotPeriod) < dotLength
      overlay.data[pixel * 4 + 3] = edge
        ? (showEdge ? Math.round(edgeAlpha * 255) : 0)
        : Math.round(fillAlpha * alpha)
    }
  }
  overlayCtx.putImageData(overlay, 0, 0)
  ctx.drawImage(overlayCanvas, options.offset?.x ?? 0, options.offset?.y ?? 0)
}

function drawPatchSource(
  ctx: CanvasRenderingContext2D,
  mask: HTMLCanvasElement | null | undefined,
  source: { x: number; y: number } | null | undefined,
  target: { x: number; y: number } | null | undefined,
  edgeAlpha: number,
) {
  if (!mask || !source || !target) return
  paintMask(ctx, mask, 0, edgeAlpha, {
    offset: {
      x: source.x - target.x,
      y: source.y - target.y,
    },
    dotted: true,
  })
}

function drawPins(
  ctx: CanvasRenderingContext2D,
  source: { x: number; y: number } | null | undefined,
  target: { x: number; y: number } | null | undefined,
  opacity: number,
) {
  if (!source || !target) return
  const [r, g, b] = selectionRgb()
  ctx.save()
  ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${opacity})`
  ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${opacity})`
  ctx.lineWidth = 1.5
  ctx.setLineDash([5, 4])
  ctx.beginPath()
  ctx.moveTo(source.x, source.y)
  ctx.lineTo(target.x, target.y)
  ctx.stroke()
  ctx.setLineDash([])
  for (const point of [source, target]) {
    ctx.beginPath()
    ctx.arc(point.x, point.y, 5, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = `rgba(255,255,255,${opacity})`
    ctx.lineWidth = 1.5
    ctx.stroke()
  }
  ctx.restore()
}

function draw() {
  const target = canvas.value
  const basis = props.selectedMask ?? props.hoveredMask ?? props.allRegions?.[0]?.mask
  if (!target || !basis) {
    if (target) target.getContext('2d')!.clearRect(0, 0, target.width, target.height)
    return
  }
  if (target.width !== basis.width) target.width = basis.width
  if (target.height !== basis.height) target.height = basis.height
  const ctx = target.getContext('2d')!
  ctx.clearRect(0, 0, target.width, target.height)
  for (const region of props.allRegions ?? []) {
    if (region.isPatch) {
      drawPatchSource(ctx, region.mask, region.source, region.target, 0.62)
    }
    paintMask(ctx, region.mask, 0.025, 0.62)
    drawPins(ctx, region.source, region.target, 0.62)
  }
  if (props.hoveredIsPatch) {
    drawPatchSource(
      ctx,
      props.hoveredMask,
      props.hoveredSourcePoint,
      props.hoveredTargetPoint,
      0.7,
    )
  }
  if (props.hoveredMask) paintMask(ctx, props.hoveredMask, 0.03, 0.7)
  if (props.hoveredMask) {
    drawPins(ctx, props.hoveredSourcePoint, props.hoveredTargetPoint, 0.72)
  }
  if (props.selectedIsPatch) {
    drawPatchSource(ctx, props.selectedMask, props.sourcePoint, props.targetPoint, 0.95)
  }
  if (props.selectedMask) paintMask(ctx, props.selectedMask, 0.16, 0.95)
  if (props.selectedMask) drawPins(ctx, props.sourcePoint, props.targetPoint, 0.95)
}

watch(
  () => [
    props.allRegions,
    props.selectedMask,
    props.hoveredMask,
    props.sourcePoint,
    props.targetPoint,
    props.hoveredSourcePoint,
    props.hoveredTargetPoint,
    props.selectedIsPatch,
    props.hoveredIsPatch,
    props.displayWidth,
    props.displayHeight,
  ],
  draw,
)
onMounted(draw)
</script>

<template>
  <canvas
    ref="canvas"
    class="absolute inset-0 pointer-events-none"
    :style="{ width: displayWidth + 'px', height: displayHeight + 'px' }"
  />
</template>
