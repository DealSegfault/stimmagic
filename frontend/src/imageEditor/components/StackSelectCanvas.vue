<script setup lang="ts">
/**
 * The selection overlay: marching ants whenever a selection exists, and the
 * gesture surface while a selection tool is armed.
 *
 * Mounted for the whole life of the display box, not per mode — the selection
 * is workspace state that cuts across every family, so its rendering cannot
 * belong to any one of them. The model itself (`useSelection`) is owned by the
 * HOST and passed in: this component draws and gestures, nothing more, so the
 * selection survives anything that unmounts the overlay (the crop viewport
 * replaces the display box entirely).
 *
 * When no tool is armed the overlay is pointer-transparent: the open family's
 * canvas underneath keeps the pointer, and the ants simply march above it.
 * Arming a tool takes the pointer without touching the family's session.
 *
 * A selection is not a step. It is a value the next gesture consumes: an
 * inpaint mask, a paint clip, an adjustment's region. Always by copy, never
 * live-linked, so an op ends up referencing only its own payload.
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import type { useSelection } from '../ported/useSelection'
import { useMagneticLasso } from '../ported/useMagneticLasso'
import type { Point, SelectionMode } from '../ported/geometry'
import type { SelectToolId } from '../stack/toolFamilies'

const props = withDefaults(defineProps<{
  source: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  /** The host-owned selection model; this component never creates its own. */
  model: ReturnType<typeof useSelection>
  /** The armed tool, or null when the overlay is display-only. */
  armed?: SelectToolId | null
  combine?: SelectionMode
  featherPx?: number
  /** Magic wand color-and-opacity threshold, 0-100. */
  tolerance?: number
  /** Fully opaque extent within the wand threshold, 0-100. */
  wandSpread?: number
  /** Wand mask growth (positive) or shrinkage (negative), in source pixels. */
  wandGrowPx?: number
  /** Smooth hard wand boundaries when feathering is zero. */
  wandAntialias?: boolean
  /** Selection brush diameter in display pixels, like the paint brush. */
  brushSize?: number
  /** Visual chrome only; the selection model remains intact while hidden. */
  visible?: boolean
}>(), {
  armed: null,
  combine: 'new',
  featherPx: 0,
  tolerance: 8,
  wandSpread: 100,
  wandGrowPx: 0,
  wandAntialias: true,
  brushSize: 80,
  visible: true,
})

const emit = defineEmits<{ change: [HTMLCanvasElement | null] }>()

const overlay = ref<HTMLCanvasElement | null>(null)
const selection = props.model
const magnetic = useMagneticLasso()

let drawing = false
let lastBrushPoint: Point | null = null
/** This gesture's brush path, for live feedback until the ants take over. */
let brushGesture: Point[] = []
/** Opaque intermediate prevents translucent feedback from accumulating where a path overlaps itself. */
let brushFeedback: HTMLCanvasElement | null = null
const cursor = ref<{ x: number; y: number } | null>(null)
let antsTimer: ReturnType<typeof setInterval> | null = null

const scale = computed(() =>
  props.source ? props.source.width / Math.max(1, props.displayWidth) : 1
)

function pointFrom(event: PointerEvent): Point {
  const rect = overlay.value!.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * scale.value,
    y: (event.clientY - rect.top) * scale.value,
  }
}

/**
 * Feather is skipped for brush gestures: the brush tip carries its own soft
 * edge, and a brush stroke publishes per gesture — re-feathering the whole
 * mask on each one would accumulate blur.
 */
function publish(applyFeather = true) {
  if (applyFeather && props.featherPx > 0) selection.feather(props.featherPx)
  selection.updateMarchingAnts()
  draw()
  emit('change', selection.hasSelection() ? selection.getSelectionMask() : null)
}

// -- gestures ---------------------------------------------------------------

function onPointerDown(event: PointerEvent) {
  if (!props.source || !props.armed) return
  const point = pointFrom(event)
  drawing = true
  overlay.value?.setPointerCapture(event.pointerId)

  if (props.armed === 'wand') {
    const ctx = props.source.getContext('2d', { willReadFrequently: true })
    if (ctx) {
      selection.magicWandSelect(ctx, point, {
        threshold: props.tolerance,
        spread: props.wandSpread,
        growPx: props.wandGrowPx,
        featherPx: props.featherPx,
        antialias: props.wandAntialias,
      }, props.combine)
    }
    drawing = false
    // The wand refines its temporary mask before combining it. Publishing
    // must not feather the accumulated selection a second time.
    publish(false)
    return
  }
  if (props.armed === 'brush') {
    // `New` replaces per GESTURE, so the first stroke starts over and further
    // strokes of the same drag extend it — matching how every brush works.
    if (props.combine === 'new') selection.clearSelection()
    lastBrushPoint = null
    brushGesture = []
    brushTo(point)
    return
  }
  if (props.armed === 'magnetic') {
    // The live-wire traces edges from a gradient map of the image, so it has to
    // be initialised against whatever the step is being drawn over.
    if (!magnetic.isReady()) magnetic.initialize(props.source)
    // placeAnchor returns true when the click closed the loop on the first
    // anchor, which is the gesture that finishes a magnetic lasso.
    if (magnetic.placeAnchor(point)) closeMagnetic()
    draw()
    startAnts()
    return
  }
  if (props.armed === 'rect') selection.startRectSelection(point)
  else if (props.armed === 'ellipse') selection.startEllipseSelection(point)
  else selection.startLassoSelection(point)
  startAnts()
}

function onPointerMove(event: PointerEvent) {
  const rect = overlay.value?.getBoundingClientRect()
  if (rect && props.armed === 'brush') {
    cursor.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }
  if (!drawing || !props.source || !props.armed) return
  const point = pointFrom(event)
  if (props.armed === 'brush') brushTo(point)
  else if (props.armed === 'magnetic') magnetic.updatePreview(point)
  else if (props.armed === 'rect') selection.updateRectSelection(point, props.combine, event.shiftKey)
  else if (props.armed === 'ellipse') selection.updateEllipseSelection(point, props.combine, event.shiftKey)
  else selection.continueLassoSelection(point)
  if (props.armed !== 'brush') draw()
}

function onPointerUp(event: PointerEvent) {
  if (!drawing || !props.armed) return
  const point = pointFrom(event)
  overlay.value?.releasePointerCapture(event.pointerId)

  // A magnetic lasso closes on its own anchors, not on pointer-up.
  if (props.armed === 'magnetic') { draw(); return }
  drawing = false
  if (props.armed === 'brush') {
    lastBrushPoint = null
    brushGesture = []
    publish(false)
    return
  }
  if (props.armed === 'rect') selection.finishRectSelection(point, props.combine, event.shiftKey)
  else if (props.armed === 'ellipse') selection.finishEllipseSelection(point, props.combine, event.shiftKey)
  else selection.finishLassoSelection(props.combine)
  stopAnts()
  publish()
}

function brushTo(point: Point) {
  const radius = (props.brushSize * scale.value) / 2
  selection.brushStroke(lastBrushPoint, point, radius, props.combine)
  lastBrushPoint = point
  brushGesture.push(point)
  draw()
}

/** Double-click, or clicking the first anchor, closes a magnetic lasso. */
function onDoubleClick() {
  if (props.armed === 'magnetic') closeMagnetic()
}

function closeMagnetic() {
  const path = magnetic.closeSelection()
  if (path.length > 2) selection.createMagneticLassoSelection(path, props.combine)
  magnetic.cancel()
  drawing = false
  stopAnts()
  publish()
}

// -- painting ---------------------------------------------------------------

function draw() {
  const canvas = overlay.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!props.visible) return

  // Live feedback for a brush gesture: rasterize the path opaquely first, then
  // apply one translucent wash. Stroking with the translucent color directly
  // makes self-overlaps visibly darker even though they are one selection.
  if (drawing && props.armed === 'brush' && brushGesture.length) {
    if (!brushFeedback) brushFeedback = document.createElement('canvas')
    if (brushFeedback.width !== canvas.width) brushFeedback.width = canvas.width
    if (brushFeedback.height !== canvas.height) brushFeedback.height = canvas.height
    const feedbackCtx = brushFeedback.getContext('2d')!
    feedbackCtx.clearRect(0, 0, brushFeedback.width, brushFeedback.height)
    feedbackCtx.save()
    feedbackCtx.strokeStyle = '#fff'
    feedbackCtx.lineWidth = props.brushSize * scale.value
    feedbackCtx.lineCap = 'round'
    feedbackCtx.lineJoin = 'round'
    feedbackCtx.beginPath()
    feedbackCtx.moveTo(brushGesture[0].x, brushGesture[0].y)
    // A tap has one point; the lineTo-self plus round caps makes it a dot.
    if (brushGesture.length === 1) {
      feedbackCtx.lineTo(brushGesture[0].x, brushGesture[0].y)
    }
    for (const point of brushGesture.slice(1)) feedbackCtx.lineTo(point.x, point.y)
    feedbackCtx.stroke()
    feedbackCtx.globalCompositeOperation = 'source-in'
    feedbackCtx.fillStyle = props.combine === 'subtract'
      ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)'
    feedbackCtx.fillRect(0, 0, brushFeedback.width, brushFeedback.height)
    feedbackCtx.restore()
    ctx.drawImage(brushFeedback, 0, 0)
  }

  ctx.save()
  ctx.lineWidth = Math.max(1, scale.value)

  // The committed selection: the model's own marching-ants paths.
  for (const path of selection.marchingAntsPaths.value) {
    if (path.length < 2) continue
    ctx.beginPath()
    ctx.moveTo(path[0].x, path[0].y)
    for (const point of path.slice(1)) ctx.lineTo(point.x, point.y)
    ctx.closePath()
    ctx.strokeStyle = '#000'
    ctx.setLineDash([])
    ctx.stroke()
    ctx.strokeStyle = '#fff'
    ctx.setLineDash([5 * scale.value, 5 * scale.value])
    ctx.lineDashOffset = -selection.antsOffset.value
    ctx.stroke()
  }

  // The gesture in progress.
  ctx.setLineDash([4 * scale.value, 3 * scale.value])
  ctx.strokeStyle = '#fff'
  if (props.armed === 'magnetic') {
    const preview = magnetic.getAllPoints()
    if (preview.length > 1) {
      ctx.beginPath()
      ctx.moveTo(preview[0].x, preview[0].y)
      for (const point of preview.slice(1)) ctx.lineTo(point.x, point.y)
      ctx.stroke()
    }
  } else if (drawing) {
    const points = selection.drawingPoints.value
    const start = selection.drawingStartPoint.value
    const current = selection.drawingCurrentPoint.value
    if ((props.armed === 'rect') && start && current) {
      ctx.strokeRect(
        Math.min(start.x, current.x), Math.min(start.y, current.y),
        Math.abs(current.x - start.x), Math.abs(current.y - start.y)
      )
    } else if (props.armed === 'ellipse' && start && current) {
      ctx.beginPath()
      ctx.ellipse(
        (start.x + current.x) / 2, (start.y + current.y) / 2,
        Math.abs(current.x - start.x) / 2, Math.abs(current.y - start.y) / 2,
        0, 0, Math.PI * 2
      )
      ctx.stroke()
    } else if (points.length > 1) {
      ctx.beginPath()
      ctx.moveTo(points[0].x, points[0].y)
      for (const point of points.slice(1)) ctx.lineTo(point.x, point.y)
      ctx.stroke()
    }
  }
  ctx.restore()
}

function startAnts() {
  if (antsTimer) return
  antsTimer = setInterval(() => {
    selection.antsOffset.value = (selection.antsOffset.value + 1) % 10
    draw()
  }, 90)
}
function stopAnts() {
  if (antsTimer) { clearInterval(antsTimer); antsTimer = null }
}

function clear() {
  selection.clearSelection()
  magnetic.cancel()
  publish()
}

/** Invert and feather are selection-wide verbs the options bar offers. */
function invert() {
  selection.invert()
  publish(false)
}

function resize() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  selection.initSelection({ width: props.source.width, height: props.source.height })
  // The gradient map is per-image; drop it when the composite underneath moves.
  magnetic.invalidate()
  draw()
}

defineExpose({
  clear,
  invert,
  redraw: draw,
  selectionCanvas: () => (selection.hasSelection() ? selection.getSelectionMask() : null),
})

watch(() => props.source, resize)
watch(() => props.armed, armed => {
  if (!armed) {
    magnetic.cancel()
    drawing = false
    cursor.value = null
  }
  draw()
})
watch(() => props.visible, draw)
// Marching ants animate whenever there IS a selection, not only while drawing.
watch([() => selection.marchingAntsPaths.value.length, () => props.visible], ([length, visible]) => {
  if (length && visible) startAnts()
  else stopAnts()
}, { immediate: true })
onMounted(resize)
onBeforeUnmount(stopAnts)
</script>

<template>
  <div
    class="absolute inset-0"
    :class="armed && visible ? '' : 'pointer-events-none'"
  >
    <canvas
      ref="overlay"
      class="w-full h-full touch-none"
      :class="armed && visible ? 'cursor-crosshair' : ''"
      :style="{ width: displayWidth + 'px', height: displayHeight + 'px' }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="cursor = null"
      @dblclick="onDoubleClick"
    />
    <!-- Brush outline: the only reliable size feedback while painting. -->
    <div
      v-if="visible && cursor && armed === 'brush'"
      class="pointer-events-none absolute rounded-full border border-white/70 mix-blend-difference"
      :style="{
        left: cursor.x - brushSize / 2 + 'px',
        top: cursor.y - brushSize / 2 + 'px',
        width: brushSize + 'px',
        height: brushSize + 'px',
      }"
    />
  </div>
</template>
