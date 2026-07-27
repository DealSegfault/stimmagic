<script setup lang="ts">
/**
 * Brush a mask over the composite, in the composite's own pixel space.
 *
 * Standalone by construction: this owns a mask and nothing else, so the
 * inpaint flow, region scoping ("Limit to"), and any later selection tooling
 * can all use it without reaching into a domain-specific surface.
 *
 * The soft brush is a radial gradient rather than a canvas `filter:` blur —
 * WKWebView is unreliable on canvas filters and cannot be version-pinned, so
 * the gradient path is the one that renders the same everywhere.
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { drawMaskTint, tokenRgb } from '../../composables/imageStack/maskTint'

const props = withDefaults(defineProps<{
  /** The composite this mask applies to; sets the mask's dimensions. */
  source: HTMLCanvasElement | null
  /** Display width in CSS pixels; the mask itself stays at source resolution. */
  displayWidth: number
  displayHeight: number
  /** Brush controls live in the sub-toolbar, not on the canvas. */
  mode?: 'paint' | 'erase'
  brushSize?: number
  hardness?: number
}>(), {
  mode: 'paint',
  brushSize: 80,
  hardness: 0.6,
})

const emit = defineEmits<{ change: [HTMLCanvasElement | null] }>()

const overlay = ref<HTMLCanvasElement | null>(null)
/** The mask itself: white where the model may paint, black elsewhere. */
let mask: HTMLCanvasElement | null = null

const mode = computed(() => props.mode)
const brushSize = computed(() => props.brushSize)
const hardness = computed(() => props.hardness)
const hasStrokes = ref(false)
const cursor = ref<{ x: number; y: number } | null>(null)

let drawing = false
let lastPoint: { x: number; y: number } | null = null

const scale = computed(() => {
  if (!props.source) return 1
  return props.source.width / Math.max(1, props.displayWidth)
})

function ensureMask() {
  if (!props.source) return null
  if (!mask || mask.width !== props.source.width || mask.height !== props.source.height) {
    mask = document.createElement('canvas')
    mask.width = props.source.width
    mask.height = props.source.height
    const ctx = mask.getContext('2d')!
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, mask.width, mask.height)
    hasStrokes.value = false
  }
  return mask
}

function pointFromEvent(event: PointerEvent) {
  const rect = overlay.value!.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) * scale.value,
    y: (event.clientY - rect.top) * scale.value,
  }
}

function stampBrush(ctx: CanvasRenderingContext2D, x: number, y: number) {
  const radius = (brushSize.value * scale.value) / 2
  const gradient = ctx.createRadialGradient(x, y, radius * hardness.value, x, y, radius)
  const inner = mode.value === 'paint' ? 'rgba(255,255,255,1)' : 'rgba(0,0,0,1)'
  const outer = mode.value === 'paint' ? 'rgba(255,255,255,0)' : 'rgba(0,0,0,0)'
  gradient.addColorStop(0, inner)
  gradient.addColorStop(1, outer)
  ctx.fillStyle = gradient
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
}

function strokeTo(point: { x: number; y: number }) {
  const target = ensureMask()
  if (!target) return
  const ctx = target.getContext('2d')!
  // Erasing paints black rather than clearing: the mask is opaque
  // white-on-black throughout, which is the shape every consumer expects.
  ctx.globalCompositeOperation = 'source-over'

  if (lastPoint) {
    // Space stamps along the segment so a fast drag stays continuous.
    const dx = point.x - lastPoint.x
    const dy = point.y - lastPoint.y
    const distance = Math.hypot(dx, dy)
    const step = Math.max(1, (brushSize.value * scale.value) / 6)
    for (let travelled = 0; travelled < distance; travelled += step) {
      const t = travelled / distance
      stampBrush(ctx, lastPoint.x + dx * t, lastPoint.y + dy * t)
    }
  }
  stampBrush(ctx, point.x, point.y)
  lastPoint = point
  hasStrokes.value = true
  drawOverlay()
}

function drawOverlay() {
  const canvas = overlay.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!mask) return

  // Tint the masked area so it reads as a selection over the artwork rather
  // than as a white shape covering it.
  drawMaskTint(ctx, mask, canvas.width, canvas.height,
    tokenRgb('--color-selection-rgb', [129, 140, 248]), 0.45)
}

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  drawing = true
  lastPoint = null
  overlay.value?.setPointerCapture(event.pointerId)
  strokeTo(pointFromEvent(event))
}

function onPointerMove(event: PointerEvent) {
  const rect = overlay.value?.getBoundingClientRect()
  if (rect) cursor.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  if (!drawing) return
  strokeTo(pointFromEvent(event))
}

function onPointerUp(event: PointerEvent) {
  if (!drawing) return
  drawing = false
  lastPoint = null
  overlay.value?.releasePointerCapture(event.pointerId)
  emit('change', hasStrokes.value ? mask : null)
}

function clear() {
  if (!mask) return
  const ctx = mask.getContext('2d')!
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, mask.width, mask.height)
  hasStrokes.value = false
  drawOverlay()
  emit('change', null)
}

function invert() {
  const target = ensureMask()
  if (!target) return
  const ctx = target.getContext('2d', { willReadFrequently: true })!
  const data = ctx.getImageData(0, 0, target.width, target.height)
  for (let i = 0; i < data.data.length; i += 4) {
    data.data[i] = 255 - data.data[i]
    data.data[i + 1] = 255 - data.data[i + 1]
    data.data[i + 2] = 255 - data.data[i + 2]
  }
  ctx.putImageData(data, 0, 0)
  hasStrokes.value = true
  drawOverlay()
  emit('change', target)
}

function resizeOverlay() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  drawOverlay()
}

defineExpose({ clear, maskCanvas: () => (hasStrokes.value ? mask : null) })

watch(() => props.source, () => { ensureMask(); resizeOverlay() })
onMounted(() => { ensureMask(); resizeOverlay() })
onBeforeUnmount(() => { mask = null })
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
    <!-- Brush outline: the only reliable size feedback while painting. -->
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
