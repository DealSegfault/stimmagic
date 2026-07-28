<script setup lang="ts">
/**
 * Select maintains ONE active selection, drawn as marching ants.
 *
 * The selection model itself is the snapshot editor's, copied into
 * `imageEditor/ported/` — rect, ellipse, lasso, magnetic lasso, magic wand,
 * combine modes, feather, invert, and the marching-ants path generation were
 * all already solved and debugged there. This component is only the gesture
 * surface and the bridge to the op stack.
 *
 * A selection is not a step. It is a value the next gesture consumes: entering
 * Generate → Inpaint pre-fills the mask from it, and an adjustment scopes to it
 * with "Limit to". Always by copy, never live-linked, so an op ends up
 * referencing only its own payload.
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useSelection } from '../../imageEditor/ported/useSelection'
import { useMagneticLasso } from '../../imageEditor/ported/useMagneticLasso'
import type { Point, SelectionMode } from '../../imageEditor/ported/geometry'

const props = withDefaults(defineProps<{
  source: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  tool?: 'rect' | 'ellipse' | 'lasso' | 'magnetic' | 'wand' | 'brush'
  combine?: SelectionMode
  featherPx?: number
  /** Magic wand colour tolerance, 0-255. */
  tolerance?: number
}>(), {
  tool: 'rect',
  combine: 'new',
  featherPx: 0,
  tolerance: 32,
})

const emit = defineEmits<{ change: [HTMLCanvasElement | null] }>()

const overlay = ref<HTMLCanvasElement | null>(null)
const selection = useSelection()
const magnetic = useMagneticLasso()

let drawing = false
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

function publish() {
  if (props.featherPx > 0) selection.feather(props.featherPx)
  selection.updateMarchingAnts()
  draw()
  emit('change', selection.hasSelection() ? selection.getSelectionMask() : null)
}

// -- gestures ---------------------------------------------------------------

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  const point = pointFrom(event)
  drawing = true
  overlay.value?.setPointerCapture(event.pointerId)

  if (props.tool === 'wand') {
    const ctx = props.source.getContext('2d', { willReadFrequently: true })
    if (ctx) selection.magicWandSelect(ctx, point, props.tolerance, props.combine)
    drawing = false
    publish()
    return
  }
  if (props.tool === 'magnetic') {
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
  if (props.tool === 'rect' || props.tool === 'brush') selection.startRectSelection(point)
  else if (props.tool === 'ellipse') selection.startEllipseSelection(point)
  else selection.startLassoSelection(point)
  startAnts()
}

function onPointerMove(event: PointerEvent) {
  if (!drawing || !props.source) return
  const point = pointFrom(event)
  if (props.tool === 'magnetic') magnetic.updatePreview(point)
  else if (props.tool === 'rect' || props.tool === 'brush') selection.updateRectSelection(point, props.combine, event.shiftKey)
  else if (props.tool === 'ellipse') selection.updateEllipseSelection(point, props.combine, event.shiftKey)
  else selection.continueLassoSelection(point)
  draw()
}

function onPointerUp(event: PointerEvent) {
  if (!drawing) return
  const point = pointFrom(event)
  overlay.value?.releasePointerCapture(event.pointerId)

  // A magnetic lasso closes on its own anchors, not on pointer-up.
  if (props.tool === 'magnetic') { draw(); return }
  drawing = false
  if (props.tool === 'rect' || props.tool === 'brush') selection.finishRectSelection(point, props.combine, event.shiftKey)
  else if (props.tool === 'ellipse') selection.finishEllipseSelection(point, props.combine, event.shiftKey)
  else selection.finishLassoSelection(props.combine)
  stopAnts()
  publish()
}

/** Double-click, or clicking the first anchor, closes a magnetic lasso. */
function onDoubleClick() {
  if (props.tool === 'magnetic') closeMagnetic()
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

  ctx.save()
  ctx.lineWidth = Math.max(1, scale.value)

  // The committed selection: the ported model's own marching-ants paths.
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
  if (props.tool === 'magnetic') {
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
    if ((props.tool === 'rect' || props.tool === 'brush') && start && current) {
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

/** Invert and feather are selection-wide verbs the sub-bar offers. */
function invert() {
  selection.invert()
  publish()
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
  selectionCanvas: () => (selection.hasSelection() ? selection.getSelectionMask() : null),
})

watch(() => props.source, resize)
// Marching ants animate whenever there IS a selection, not only while drawing.
watch(() => selection.marchingAntsPaths.value.length, length => {
  if (length) startAnts()
  else stopAnts()
})
onMounted(resize)
onBeforeUnmount(stopAnts)
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
      @dblclick="onDoubleClick"
    />
  </div>
</template>
