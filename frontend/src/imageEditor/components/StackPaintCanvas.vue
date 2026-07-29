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
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRetouchLayer } from '../ported/useRetouchLayer'
import { getSelectionBounds } from '../ported/selection'
import type { BrushSettings, Point } from '../ported/geometry'

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
  strength?: number
  /** Sponge direction: saturate, or pull color out. */
  saturate?: boolean
}>(), {
  engineId: 'paint',
  exposure: 10,
  range: 'midtones',
  strength: 20,
  saturate: true,
})

const emit = defineEmits<{
  /**
   * A stroke finished: an immutable layer snapshot, whether pixels below were
   * read, and the local revision that snapshot represents.
   */
  stroke: [HTMLCanvasElement, boolean, number]
  /** A patch landed: the selection it consumed should clear. */
  patchApplied: []
}>()

const overlay = ref<HTMLCanvasElement | null>(null)
/** The complete layer that is snapshotted and persisted after each stroke. */
const layer = useRetouchLayer()
/** Only the stroke currently under the pointer; never contains older strokes. */
const liveStroke = useRetouchLayer()

const cursor = ref<{ x: number; y: number } | null>(null)
/**
 * Completed strokes that persistence has not handed to the composite yet.
 *
 * The overlay draws these deltas plus `liveStroke`, never the cumulative layer:
 * once a revision lands in the stack, removing its delta cannot reveal or
 * double-composite older strokes.
 */
let pendingPreviews: Array<{ revision: number; canvas: HTMLCanvasElement }> = []
/** Frozen visual input for the current stroke, including any pending previews. */
let strokeSource: HTMLCanvasElement | null = null
/** Where clone samples from, set by alt-click and kept across strokes. */
const cloneAnchor = ref<Point | null>(null)
let drawing = false
let activePointerId: number | null = null
/**
 * Monotonic ownership token for the overlay.
 *
 * Stroke persistence is asynchronous. A completed older render must not clear
 * a newer stroke that has already taken the overlay back.
 */
let layerRevision = 0
/** The entry snapshot is seed data, not something to restore after each render. */
let loadedInitialLayer: HTMLCanvasElement | null = null

/**
 * The patch drag in flight: grab inside the selection, drag to the donor
 * area. While it lasts, the overlay previews the donor pixels flowing into
 * the selection — the pixels that will actually land, not an outline.
 */
let patchDrag: {
  start: Point
  current: Point
  bounds: { x: number; y: number; width: number; height: number }
  /** Scratch canvas for the masked donor preview, allocated once per drag. */
  preview: HTMLCanvasElement
} | null = null

function pointInMask(point: Point): boolean {
  const mask = props.selectionMask
  if (!mask) return false
  const x = Math.floor(point.x)
  const y = Math.floor(point.y)
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return false
  const ctx = mask.getContext('2d', { willReadFrequently: true })!
  return ctx.getImageData(x, y, 1, 1).data[3] > 0
}

const brushSettings = computed<BrushSettings>(() => props.brush ?? {
  size: 26, hardness: 60, opacity: 100, flow: 100, spacing: 25,
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

/**
 * Brush size is a display measurement; the layer works in image pixels.
 *
 * Rounded, not just scaled: heal allocates an ImageData of exactly this many
 * pixels and then indexes it as `(y * size + x) * 4`. A fractional size makes
 * every one of those indices miss, and the engine silently writes nothing.
 */
function scaledBrush(): BrushSettings {
  return {
    ...brushSettings.value,
    size: Math.max(1, Math.round(brushSettings.value.size * scale.value)),
  }
}

function prepareStroke() {
  const source = props.source
  if (!source) return

  liveStroke.clearLayer()
  liveStroke.startStroke()

  const working = document.createElement('canvas')
  working.width = source.width
  working.height = source.height
  const ctx = working.getContext('2d')!
  ctx.drawImage(source, 0, 0)
  for (const pending of pendingPreviews) ctx.drawImage(pending.canvas, 0, 0)
  strokeSource = working
}

function stamp(point: Point) {
  const source = strokeSource ?? props.source
  if (!source) return
  const brush = scaledBrush()

  switch (props.engineId) {
    case 'clone':
      liveStroke.applyCloneStamp(source, point, brush)
      break
    case 'heal':
      liveStroke.applySpotHeal(source, point, brush)
      break
    case 'dodge':
      liveStroke.applyDodgeBurn(source, point, brush, props.exposure, props.range, true)
      break
    case 'burn':
      liveStroke.applyDodgeBurn(source, point, brush, props.exposure, props.range, false)
      break
    case 'sponge':
      liveStroke.applySaturationBrush(source, point, brush, props.strength, props.saturate)
      break
    case 'blur':
      liveStroke.applyBlurBrush(source, point, brush, props.strength)
      break
    case 'sharpen':
      liveStroke.applySharpenBrush(source, point, brush, props.strength)
      break
    case 'fill':
      liveStroke.applyFloodFill(
        source,
        point,
        props.color ?? { r: 0, g: 0, b: 0, a: 1 },
        32,
      )
      break
    default:
      liveStroke.applyPaintBrush(point, brush, props.color ?? { r: 0, g: 0, b: 0, a: 1 })
  }
  drawOverlay()
}

function finishStroke(readsPixels: boolean): boolean {
  liveStroke.endStroke()
  const preview = liveStroke.toSnapshot()
  if (!preview) return false

  // Canvas source-over is associative: merging the delta into the persisted
  // layer produces the same pixels the user just saw over the stage.
  layer.retouchCtx.value?.drawImage(preview, 0, 0)
  pendingPreviews.push({ revision: layerRevision, canvas: preview })

  const snapshot = layer.toSnapshot()
  liveStroke.clearLayer()
  strokeSource = null
  drawOverlay()
  if (snapshot) emit('stroke', snapshot, readsPixels, layerRevision)
  return !!snapshot
}

function drawOverlay() {
  const canvas = overlay.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  for (const pending of pendingPreviews) ctx.drawImage(pending.canvas, 0, 0)
  if (drawing && liveStroke.retouchCanvas.value) {
    ctx.drawImage(liveStroke.retouchCanvas.value, 0, 0)
  }

  // Patch drag: preview the donor pixels IN the destination — what will land,
  // not an outline of it — plus a dashed box over the donor area itself.
  if (patchDrag && strokeSource && props.selectionMask) {
    const { start, current, bounds, preview } = patchDrag
    const dx = current.x - start.x
    const dy = current.y - start.y

    const previewCtx = preview.getContext('2d')!
    previewCtx.clearRect(0, 0, preview.width, preview.height)
    previewCtx.drawImage(strokeSource, -dx, -dy)
    previewCtx.globalCompositeOperation = 'destination-in'
    previewCtx.drawImage(props.selectionMask, 0, 0)
    previewCtx.globalCompositeOperation = 'source-over'
    ctx.drawImage(preview, 0, 0)

    ctx.save()
    ctx.strokeStyle = 'rgba(255,255,255,0.8)'
    ctx.lineWidth = Math.max(1, scale.value)
    ctx.setLineDash([5 * scale.value, 4 * scale.value])
    ctx.strokeRect(bounds.x + dx, bounds.y + dy, bounds.width, bounds.height)
    ctx.restore()
  }
}

function onPointerDown(event: PointerEvent) {
  if (!props.source) return
  const point = pointFrom(event)

  // Patch is a drag of the selection, not a stroke. No selection or a grab
  // outside it does nothing — the selection tools own making one.
  if (props.engineId === 'patch') {
    const mask = props.selectionMask
    if (!mask || !pointInMask(point)) return
    const maskCtx = mask.getContext('2d', { willReadFrequently: true })!
    const bounds = getSelectionBounds(maskCtx)
    if (!bounds) return
    const preview = document.createElement('canvas')
    preview.width = props.source.width
    preview.height = props.source.height
    layerRevision += 1
    prepareStroke()
    activePointerId = event.pointerId
    overlay.value?.setPointerCapture(event.pointerId)
    patchDrag = { start: point, current: point, bounds, preview }
    drawOverlay()
    return
  }

  // Alt-click sets the clone source, the way it works everywhere else. The
  // OFFSET is only known once painting starts, so the anchor is held here and
  // resolved against the first destination point of the stroke.
  if (props.engineId === 'clone' && event.altKey) {
    cloneAnchor.value = point
    return
  }
  if (props.engineId === 'clone' && !cloneAnchor.value) return
  layerRevision += 1
  prepareStroke()
  if (props.engineId === 'clone') {
    liveStroke.setCloneSource(strokeSource ?? props.source, cloneAnchor.value, point)
  }

  activePointerId = event.pointerId
  overlay.value?.setPointerCapture(event.pointerId)
  drawing = true
  stamp(point)
}

function onPointerMove(event: PointerEvent) {
  if (activePointerId !== null && event.pointerId !== activePointerId) return
  const rect = overlay.value?.getBoundingClientRect()
  if (rect) cursor.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  if (patchDrag) {
    patchDrag.current = pointFrom(event)
    drawOverlay()
    return
  }
  // Fill is a click operation. Re-running a flood fill for every move event
  // wastes a full-image traversal and makes its result depend on pointer noise.
  if (drawing && props.engineId !== 'fill') stamp(pointFrom(event))
}

function releasePointer(pointerId: number) {
  const canvas = overlay.value
  if (canvas?.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId)
}

function onPointerUp(event: PointerEvent) {
  if (activePointerId === null || event.pointerId !== activePointerId) return
  releasePointer(event.pointerId)
  activePointerId = null

  if (patchDrag) {
    // The final pointer position is authoritative. A coalesced or lost move
    // must not make the patch land at the last preview frame instead.
    patchDrag.current = pointFrom(event)
    const { start, current, bounds } = patchDrag
    const offset = { x: current.x - start.x, y: current.y - start.y }
    patchDrag = null
    try {
      // A couple of pixels is a click, not a drag — applying it would sample
      // the selection onto itself.
      if (strokeSource && Math.hypot(offset.x, offset.y) > 2) {
        liveStroke.applyPatchTool(strokeSource, offset, bounds, PATCH_BLEND_WIDTH)
        finishStroke(true)
        // The patch consumed the selection; ants over fixed pixels would lie.
        emit('patchApplied')
      } else {
        liveStroke.endStroke()
        liveStroke.clearLayer()
        strokeSource = null
      }
    } finally {
      // Never strand the deliberately crisp drag preview if blending throws.
      drawOverlay()
    }
    return
  }

  if (!drawing) return
  drawing = false
  finishStroke(PIXEL_READING.has(props.engineId))
}

/**
 * Pointer capture is not a completion guarantee: WebKit can drop it when the
 * pointer crosses another overlay or leaves the element. The snapshot editor's
 * working gesture path listened on window for this reason. These fallbacks only
 * act when the event was not already retargeted to the captured canvas.
 */
function onWindowPointerMove(event: PointerEvent) {
  if (event.target !== overlay.value && activePointerId === event.pointerId) {
    onPointerMove(event)
  }
}

function onWindowPointerUp(event: PointerEvent) {
  if (event.target !== overlay.value && activePointerId === event.pointerId) {
    onPointerUp(event)
  }
}

function onPointerCancel(event: PointerEvent) {
  if (activePointerId !== event.pointerId) return
  releasePointer(event.pointerId)
  activePointerId = null
  drawing = false
  patchDrag = null
  liveStroke.endStroke()
  liveStroke.clearLayer()
  strokeSource = null
  drawOverlay()
}

/** The old editor's patch edge blend, kept as its default. */
const PATCH_BLEND_WIDTH = 15

/** Start a new layer: the next stroke creates the next Paint step. */
function reset() {
  // Invalidate any async hand-off still referring to the previous layer.
  layerRevision += 1
  loadedInitialLayer = null
  pendingPreviews = []
  strokeSource = null
  liveStroke.clearLayer()
  layer.clearLayer()
  drawOverlay()
}

function resize() {
  const canvas = overlay.value
  if (!canvas || !props.source) return
  canvas.width = props.source.width
  canvas.height = props.source.height
  layer.initLayer({ width: props.source.width, height: props.source.height })
  liveStroke.initLayer({ width: props.source.width, height: props.source.height })
  if (props.initialLayer && props.initialLayer !== loadedInitialLayer) {
    layer.loadFromSnapshot(props.initialLayer)
    loadedInitialLayer = props.initialLayer
  } else if (!props.initialLayer) {
    loadedInitialLayer = null
  }
  drawOverlay()
}

defineExpose({
  reset,
  /**
   * Remove only the preview revisions the freshly rendered composite now owns.
   * A newer live stroke is a separate canvas, so an older async handoff can
   * never hide it.
   */
  clearDisplay(revision: number) {
    pendingPreviews = pendingPreviews.filter(pending => pending.revision > revision)
    drawOverlay()
  },
})

// Strokes respect the active selection, which is what makes Select → Paint work
// without either side knowing about the other.
watch(() => props.selectionMask, mask => {
  liveStroke.setSelectionMask(mask ? mask.getContext('2d') : null)
}, { immediate: true })

watch(() => props.source, resize)
watch(() => props.initialLayer, resize)
onMounted(() => {
  resize()
  window.addEventListener('pointermove', onWindowPointerMove)
  window.addEventListener('pointerup', onWindowPointerUp)
  window.addEventListener('pointercancel', onPointerCancel)
})
onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
})
</script>

<template>
  <div class="absolute inset-0">
    <canvas
      ref="overlay"
      class="w-full h-full touch-none"
      :class="engineId === 'patch'
        ? (selectionMask ? 'cursor-move' : 'cursor-default')
        : 'cursor-crosshair'"
      :style="{ width: displayWidth + 'px', height: displayHeight + 'px' }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerCancel"
      @pointerleave="cursor = null"
    />
    <div
      v-if="cursor && brush && engineId !== 'patch'"
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
