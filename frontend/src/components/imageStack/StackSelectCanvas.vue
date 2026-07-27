<script setup lang="ts">
/**
 * Select maintains ONE active selection, drawn as marching ants.
 *
 * A selection is not a step — it is a value the next gesture consumes. While it
 * exists, entering Generate → Inpaint pre-fills the mask from it, and an
 * adjustment can be scoped with "Limit to → Selection". Selections are consumed
 * by COPY, like every region: nothing stays live-linked, which is what keeps an
 * op referencing only its own payloads.
 *
 * Combine modes compose onto the existing selection rather than replacing it,
 * which is what makes rectangle-plus-lasso a usable way to build a shape.
 */
import { ref, computed, onMounted, watch } from 'vue'
import type { SelectionMode } from '../../composables/imageStack/toolFamilies'
import { drawMaskTint, tokenRgb } from '../../composables/imageStack/maskTint'

const props = withDefaults(defineProps<{
  source: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  tool?: 'rect' | 'ellipse' | 'lasso' | 'brush'
  combine?: SelectionMode
  featherPx?: number
  brushSize?: number
}>(), {
  tool: 'rect',
  combine: 'new',
  featherPx: 8,
  brushSize: 60,
})

const emit = defineEmits<{ change: [HTMLCanvasElement | null] }>()

const overlay = ref<HTMLCanvasElement | null>(null)
/** The selection itself: white inside, black outside. */
let selection: HTMLCanvasElement | null = null
let hasSelection = false

let dragging = false
let start: { x: number; y: number } | null = null
let current: { x: number; y: number } | null = null
let lassoPoints: Array<{ x: number; y: number }> = []
/** Marching-ants phase; animated only while a selection exists. */
const antsOffset = ref(0)
let antsTimer: ReturnType<typeof setInterval> | null = null

const scale = computed(() =>
  props.source ? props.source.width / Math.max(1, props.displayWidth) : 1
)

function ensureSelection() {
  if (!props.source) return null
  if (!selection || selection.width !== props.source.width || selection.height !== props.source.height) {
    selection = document.createElement('canvas')
    selection.width = props.source.width
    selection.height = props.source.height
    const ctx = selection.getContext('2d')!
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, selection.width, selection.height)
    hasSelection = false
  }
  return selection
}

function pointFrom(event: PointerEvent) {
  const rect = overlay.value!.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * scale.value,
    y: (event.clientY - rect.top) * scale.value,
  }
}

/** Draw the in-progress shape into a scratch canvas, white on transparent. */
function renderShapeTo(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = '#fff'
  if (props.tool === 'rect' && start && current) {
    ctx.fillRect(
      Math.min(start.x, current.x), Math.min(start.y, current.y),
      Math.abs(current.x - start.x), Math.abs(current.y - start.y)
    )
  } else if (props.tool === 'ellipse' && start && current) {
    const cx = (start.x + current.x) / 2
    const cy = (start.y + current.y) / 2
    ctx.beginPath()
    ctx.ellipse(cx, cy, Math.abs(current.x - start.x) / 2, Math.abs(current.y - start.y) / 2, 0, 0, Math.PI * 2)
    ctx.fill()
  } else if (props.tool === 'lasso' && lassoPoints.length > 1) {
    ctx.beginPath()
    ctx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
    for (const point of lassoPoints.slice(1)) ctx.lineTo(point.x, point.y)
    ctx.closePath()
    ctx.fill()
  } else if (props.tool === 'brush' && lassoPoints.length) {
    const radius = (props.brushSize * scale.value) / 2
    for (const point of lassoPoints) {
      ctx.beginPath()
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

/** Compose the finished shape onto the selection with the combine mode. */
function commitShape() {
  const target = ensureSelection()
  if (!target) return

  const shape = document.createElement('canvas')
  shape.width = target.width
  shape.height = target.height
  renderShapeTo(shape.getContext('2d')!)

  const ctx = target.getContext('2d')!
  ctx.globalCompositeOperation = 'source-over'
  if (props.combine === 'new') {
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, target.width, target.height)
    ctx.drawImage(shape, 0, 0)
  } else if (props.combine === 'add') {
    ctx.drawImage(shape, 0, 0)
  } else if (props.combine === 'subtract') {
    // Paint black where the new shape is.
    const cut = document.createElement('canvas')
    cut.width = target.width
    cut.height = target.height
    const cutCtx = cut.getContext('2d')!
    cutCtx.drawImage(shape, 0, 0)
    cutCtx.globalCompositeOperation = 'source-in'
    cutCtx.fillStyle = '#000'
    cutCtx.fillRect(0, 0, target.width, target.height)
    ctx.drawImage(cut, 0, 0)
  } else if (props.combine === 'intersect') {
    ctx.globalCompositeOperation = 'destination-in'
    ctx.drawImage(shape, 0, 0)
    ctx.globalCompositeOperation = 'source-over'
    // destination-in leaves transparency where it clipped; refill as black so
    // the mask stays opaque white-on-black for every consumer.
    const flat = document.createElement('canvas')
    flat.width = target.width
    flat.height = target.height
    const flatCtx = flat.getContext('2d')!
    flatCtx.fillStyle = '#000'
    flatCtx.fillRect(0, 0, flat.width, flat.height)
    flatCtx.drawImage(target, 0, 0)
    ctx.clearRect(0, 0, target.width, target.height)
    ctx.drawImage(flat, 0, 0)
  }

  hasSelection = true
  emit('change', target)
}

function drawOverlay() {
  const canvas = overlay.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  if (selection && hasSelection) {
    drawMaskTint(ctx, selection, canvas.width, canvas.height,
      tokenRgb('--color-selection-rgb', [129, 140, 248]), 0.35)
  }

  // Marching ants around the in-progress shape.
  if (dragging) {
    ctx.save()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = Math.max(1, scale.value)
    ctx.setLineDash([6 * scale.value, 4 * scale.value])
    ctx.lineDashOffset = -antsOffset.value
    if (props.tool === 'rect' && start && current) {
      ctx.strokeRect(
        Math.min(start.x, current.x), Math.min(start.y, current.y),
        Math.abs(current.x - start.x), Math.abs(current.y - start.y)
      )
    } else if (props.tool === 'ellipse' && start && current) {
      ctx.beginPath()
      ctx.ellipse(
        (start.x + current.x) / 2, (start.y + current.y) / 2,
        Math.abs(current.x - start.x) / 2, Math.abs(current.y - start.y) / 2,
        0, 0, Math.PI * 2
      )
      ctx.stroke()
    } else if (lassoPoints.length > 1) {
      ctx.beginPath()
      ctx.moveTo(lassoPoints[0].x, lassoPoints[0].y)
      for (const point of lassoPoints.slice(1)) ctx.lineTo(point.x, point.y)
      ctx.stroke()
    }
    ctx.restore()
  }
}

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  dragging = true
  const point = pointFrom(event)
  start = point
  current = point
  lassoPoints = [point]
  overlay.value?.setPointerCapture(event.pointerId)
  startAnts()
}

function onPointerMove(event: PointerEvent) {
  if (!dragging) return
  const point = pointFrom(event)
  current = point
  if (props.tool === 'lasso' || props.tool === 'brush') lassoPoints.push(point)
  drawOverlay()
}

function onPointerUp(event: PointerEvent) {
  if (!dragging) return
  dragging = false
  overlay.value?.releasePointerCapture(event.pointerId)
  commitShape()
  stopAnts()
  drawOverlay()
}

function startAnts() {
  if (antsTimer) return
  antsTimer = setInterval(() => {
    antsOffset.value = (antsOffset.value + 1) % 20
    drawOverlay()
  }, 80)
}
function stopAnts() {
  if (antsTimer) { clearInterval(antsTimer); antsTimer = null }
}

function clear() {
  if (!selection) return
  const ctx = selection.getContext('2d')!
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, selection.width, selection.height)
  hasSelection = false
  drawOverlay()
  emit('change', null)
}

function resize() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  drawOverlay()
}

defineExpose({ clear, selectionCanvas: () => (hasSelection ? selection : null) })

watch(() => props.source, () => { ensureSelection(); resize() })
onMounted(() => { ensureSelection(); resize() })
</script>

<template>
  <div class="absolute inset-0">
    <canvas
      ref="overlay"
      class="w-full h-full cursor-crosshair touch-none"
      :style="{ width: displayWidth + 'px', height: displayHeight + 'px' }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
    />
  </div>
</template>
