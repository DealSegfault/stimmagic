<script setup lang="ts">
/**
 * Paint strokes into a raster layer.
 *
 * A layer IS a step: several Paint rows are several layers, each at its own
 * stack position with its own opacity, re-enterable by double-clicking the row.
 * Individual strokes are never rows.
 *
 * Engines that lay down colour (round, ink, airbrush) draw into the layer.
 * Engines that READ pixels (blur, dodge, burn) sample the composite below and
 * bake the result into the layer — which is why their layers carry an advisory
 * hash like a generative patch: what they baked depends on what was underneath.
 *
 * The soft brush is a radial gradient, not a canvas `filter:` blur: WKWebView
 * is unreliable on canvas filters and cannot be version-pinned.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { PAINT_ENGINES } from '../../composables/imageStack/toolFamilies'

const props = withDefaults(defineProps<{
  /** The composite below — what pixel-reading engines sample. */
  source: HTMLCanvasElement | null
  /** Existing layer content when re-entering a Paint step. */
  initialLayer?: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  engineId?: string
  brushSize?: number
  opacity?: number
  color?: string
}>(), {
  engineId: 'round-soft',
  brushSize: 26,
  opacity: 1,
  color: '#c9a276',
})

const emit = defineEmits<{
  /** A stroke finished: the layer, and whether pixels below were read. */
  stroke: [HTMLCanvasElement, boolean]
}>()

const overlay = ref<HTMLCanvasElement | null>(null)
let layer: HTMLCanvasElement | null = null

const cursor = ref<{ x: number; y: number } | null>(null)
let drawing = false
let lastPoint: { x: number; y: number } | null = null

const engine = computed(
  () => PAINT_ENGINES.find(e => e.id === props.engineId) || PAINT_ENGINES[0]
)
const scale = computed(() =>
  props.source ? props.source.width / Math.max(1, props.displayWidth) : 1
)

function ensureLayer() {
  if (!props.source) return null
  if (!layer || layer.width !== props.source.width || layer.height !== props.source.height) {
    layer = document.createElement('canvas')
    layer.width = props.source.width
    layer.height = props.source.height
    if (props.initialLayer) {
      layer.getContext('2d')!.drawImage(props.initialLayer, 0, 0)
    }
  }
  return layer
}

function pointFrom(event: PointerEvent) {
  const rect = overlay.value!.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * scale.value,
    y: (event.clientY - rect.top) * scale.value,
  }
}

function stamp(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const radius = Math.max(1, (props.brushSize * scale.value) / 2)
  const current = engine.value

  if (current.readsPixels && props.source) {
    // Sample the composite below, transform it, and lay THAT down. The layer
    // keeps holding pixels, so the compositor needs no special case.
    stampFromSource(ctx, x, y, radius, current.id)
    return
  }

  const gradient = ctx.createRadialGradient(x, y, radius * current.hardness, x, y, radius)
  gradient.addColorStop(0, props.color)
  gradient.addColorStop(1, 'transparent')
  ctx.globalAlpha = props.opacity * current.flow
  ctx.fillStyle = gradient
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalAlpha = 1
}

function stampFromSource(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  engineId: string
) {
  const size = Math.ceil(radius * 2)
  const left = Math.round(x - radius)
  const top = Math.round(y - radius)
  if (size < 1) return

  const patch = document.createElement('canvas')
  patch.width = size
  patch.height = size
  const patchCtx = patch.getContext('2d', { willReadFrequently: true })!
  patchCtx.drawImage(props.source!, left, top, size, size, 0, 0, size, size)

  const data = patchCtx.getImageData(0, 0, size, size)
  if (engineId === 'blur') {
    boxBlur(data, size)
  } else {
    // Dodge lifts, burn deepens — the snapshot editor's own reading of both.
    const factor = engineId === 'dodge' ? 1.35 : 0.7
    for (let i = 0; i < data.data.length; i += 4) {
      data.data[i] = data.data[i] * factor
      data.data[i + 1] = data.data[i + 1] * factor
      data.data[i + 2] = data.data[i + 2] * factor
    }
  }
  patchCtx.putImageData(data, 0, 0)

  // Feather the sampled patch into a round dab.
  const mask = document.createElement('canvas')
  mask.width = size
  mask.height = size
  const maskCtx = mask.getContext('2d')!
  const gradient = maskCtx.createRadialGradient(
    radius, radius, radius * engine.value.hardness, radius, radius, radius
  )
  gradient.addColorStop(0, 'rgba(0,0,0,1)')
  gradient.addColorStop(1, 'rgba(0,0,0,0)')
  maskCtx.fillStyle = gradient
  maskCtx.fillRect(0, 0, size, size)
  maskCtx.globalCompositeOperation = 'source-in'
  maskCtx.drawImage(patch, 0, 0)

  ctx.globalAlpha = props.opacity * engine.value.flow
  ctx.drawImage(mask, left, top)
  ctx.globalAlpha = 1
}

function boxBlur(data: ImageData, size: number) {
  const source = new Uint8ClampedArray(data.data)
  const radius = 2
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0, n = 0
      for (let dy = -radius; dy <= radius; dy++) {
        for (let dx = -radius; dx <= radius; dx++) {
          const sx = Math.min(size - 1, Math.max(0, x + dx))
          const sy = Math.min(size - 1, Math.max(0, y + dy))
          const i = (sy * size + sx) * 4
          r += source[i]; g += source[i + 1]; b += source[i + 2]; n++
        }
      }
      const i = (y * size + x) * 4
      data.data[i] = r / n
      data.data[i + 1] = g / n
      data.data[i + 2] = b / n
    }
  }
}

function strokeTo(point: { x: number; y: number }) {
  const target = ensureLayer()
  if (!target) return
  const ctx = target.getContext('2d')!
  ctx.globalCompositeOperation = 'source-over'

  if (lastPoint) {
    const dx = point.x - lastPoint.x
    const dy = point.y - lastPoint.y
    const distance = Math.hypot(dx, dy)
    const step = Math.max(1, (props.brushSize * scale.value) / 5)
    for (let travelled = 0; travelled < distance; travelled += step) {
      const t = travelled / distance
      stamp(ctx, lastPoint.x + dx * t, lastPoint.y + dy * t)
    }
  }
  stamp(ctx, point.x, point.y)
  lastPoint = point
  drawOverlay()
}

function drawOverlay() {
  const canvas = overlay.value
  if (!canvas || !layer) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(layer, 0, 0)
}

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  drawing = true
  lastPoint = null
  overlay.value?.setPointerCapture(event.pointerId)
  strokeTo(pointFrom(event))
}

function onPointerMove(event: PointerEvent) {
  const rect = overlay.value?.getBoundingClientRect()
  if (rect) cursor.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  if (drawing) strokeTo(pointFrom(event))
}

function onPointerUp(event: PointerEvent) {
  if (!drawing) return
  drawing = false
  lastPoint = null
  overlay.value?.releasePointerCapture(event.pointerId)
  if (layer) emit('stroke', layer, !!engine.value.readsPixels)
}

function resize() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  drawOverlay()
}

/** Start a new layer: the next stroke creates the next Paint step. */
function reset() {
  layer = null
  ensureLayer()
  drawOverlay()
}

defineExpose({ reset })

watch(() => props.source, () => { ensureLayer(); resize() })
watch(() => props.initialLayer, () => { layer = null; ensureLayer(); resize() })
onMounted(() => { ensureLayer(); resize() })
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
      v-if="cursor"
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
