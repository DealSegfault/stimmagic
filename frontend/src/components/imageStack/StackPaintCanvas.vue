<script setup lang="ts">
/**
 * Paint strokes into a raster layer.
 *
 * The pixel work is the snapshot editor's, copied into `imageEditor/ported/`:
 * paint, clone stamp, spot heal, patch, dodge and burn with proper shadow /
 * midtone / highlight targeting, sponge, blur and sharpen. Reimplementing it
 * produced a radial-gradient stamp and a brightness multiply pretending to be
 * dodge — this component is now only the gesture surface and the bridge to the
 * op stack.
 *
 * A layer IS a step: several Paint rows are several layers, each at its own
 * stack position, re-enterable by double-clicking the row. Strokes are never
 * rows.
 *
 * Engines that READ the composite below (heal, clone, dodge, burn, sponge,
 * blur, sharpen) bake what was underneath, which is why their layers carry an
 * advisory hash like a generative patch.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRetouchLayer } from '../../imageEditor/ported/useRetouchLayer'
import type { BrushSettings, Point } from '../../imageEditor/ported/geometry'

/** Engines whose output depends on the pixels below them. */
const PIXEL_READING = new Set([
  'clone', 'heal', 'patch', 'dodge', 'burn', 'sponge', 'blur', 'sharpen',
])

const props = withDefaults(defineProps<{
  /** The composite below — what pixel-reading engines sample. */
  source: HTMLCanvasElement | null
  /** Existing layer content when re-entering a Paint step. */
  initialLayer?: HTMLCanvasElement | null
  /** Restrict strokes to the active selection. */
  selectionMask?: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  engineId?: string
  brush?: BrushSettings
  color?: { r: number; g: number; b: number; a?: number }
  /** Dodge/burn strength and range. */
  exposure?: number
  range?: 'shadows' | 'midtones' | 'highlights'
  /** Sponge / blur / sharpen strength. */
  flow?: number
}>(), {
  engineId: 'paint',
  exposure: 50,
  range: 'midtones',
  flow: 50,
})

const emit = defineEmits<{
  /** A stroke finished: the layer, and whether pixels below were read. */
  stroke: [HTMLCanvasElement, boolean]
}>()

const overlay = ref<HTMLCanvasElement | null>(null)
const layer = useRetouchLayer()

const cursor = ref<{ x: number; y: number } | null>(null)
let drawing = false

const brushSettings = computed<BrushSettings>(() => props.brush ?? {
  size: 26, hardness: 60, opacity: 100, flow: 100, spacing: 10,
})
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

/** Brush size is a display measurement; the layer works in image pixels. */
function scaledBrush(): BrushSettings {
  return { ...brushSettings.value, size: brushSettings.value.size * scale.value }
}

function stamp(point: Point) {
  const source = props.source
  if (!source) return
  const brush = scaledBrush()

  switch (props.engineId) {
    case 'clone':
      layer.applyCloneStamp(source, point, brush)
      break
    case 'heal':
      layer.applySpotHeal(source, point, brush.size)
      break
    case 'dodge':
      layer.applyDodgeBurn(source, point, brush, props.exposure, props.range, true)
      break
    case 'burn':
      layer.applyDodgeBurn(source, point, brush, props.exposure, props.range, false)
      break
    case 'sponge':
      layer.applySaturationBrush(source, point, brush, props.flow, true)
      break
    case 'blur':
      layer.applyBlurBrush(source, point, brush, props.flow)
      break
    case 'sharpen':
      layer.applySharpenBrush(source, point, brush, props.flow)
      break
    case 'fill':
      layer.applyFloodFill(source, point, props.color ?? { r: 0, g: 0, b: 0, a: 1 }, 32)
      break
    default:
      layer.applyPaintBrush(point, brush, props.color ?? { r: 0, g: 0, b: 0, a: 1 })
  }
  drawOverlay()
}

function drawOverlay() {
  const canvas = overlay.value
  const source = layer.retouchCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (source) ctx.drawImage(source, 0, 0)
}

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  overlay.value?.setPointerCapture(event.pointerId)
  const point = pointFrom(event)

  // Alt-click sets the clone source, the way it works everywhere else.
  if (props.engineId === 'clone' && event.altKey) {
    layer.setCloneSource(point, { x: 0, y: 0 })
    return
  }

  drawing = true
  // The layer batches a stroke, so a drag is one operation rather than N.
  layer.startStroke()
  stamp(point)
}

function onPointerMove(event: PointerEvent) {
  const rect = overlay.value?.getBoundingClientRect()
  if (rect) cursor.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  if (drawing) stamp(pointFrom(event))
}

function onPointerUp(event: PointerEvent) {
  if (!drawing) return
  drawing = false
  overlay.value?.releasePointerCapture(event.pointerId)
  layer.endStroke()
  const canvas = layer.retouchCanvas.value
  if (canvas) emit('stroke', canvas, PIXEL_READING.has(props.engineId))
}

/** Start a new layer: the next stroke creates the next Paint step. */
function reset() {
  layer.clearLayer()
  drawOverlay()
}

function resize() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  layer.initLayer({ width: props.source.width, height: props.source.height })
  if (props.initialLayer) layer.loadFromSnapshot(props.initialLayer)
  drawOverlay()
}

defineExpose({ reset })

// Strokes respect the active selection, which is what makes Select → Paint work
// without either side knowing about the other.
watch(() => props.selectionMask, mask => {
  layer.setSelectionMask(mask ? mask.getContext('2d') : null)
}, { immediate: true })

watch(() => props.source, resize)
watch(() => props.initialLayer, resize)
onMounted(resize)
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
      @pointerleave="cursor = null"
    />
    <div
      v-if="cursor && brush"
      class="pointer-events-none absolute rounded-full border border-white/70 mix-blend-difference"
      :style="{
        left: cursor.x - brush.size / 2 + 'px',
        top: cursor.y - brush.size / 2 + 'px',
        width: brush.size + 'px',
        height: brush.size + 'px',
      }"
    />
  </div>
</template>
