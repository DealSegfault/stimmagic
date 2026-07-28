<script setup lang="ts">
/**
 * Place vector annotations: pen, arrows, shapes, text, redaction.
 *
 * Annotate is a container op with parametric physics — the shapes ARE the
 * params, so re-rendering at any size is free and re-entering the step is
 * lossless.
 *
 * The gestures and the renderer are the snapshot editor's, copied into
 * `imageEditor/ported/`: the arrow that smooths as you drag it, neon and
 * gradient styling, canvas-native text editing with a real caret, hit testing,
 * resize handles and rotation. That composable reaches the outside world only
 * through getState / updateState / pushHistory, which is exactly the seam the
 * op stack needs — the state it asks for is the op's payload, and pushHistory
 * is a journal entry.
 *
 * This component is the adapter between those two and nothing else.
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useAnnotation } from '../ported/useAnnotation'
import type { AnnotationState } from '../ported/useAnnotation'
import { renderShapes, drawSelectionHandles, getShapeBounds, getShapeCenter } from '../ported/shapes'
import type { Shape, AnnotateTool } from '../ported/shapeTypes'
import type { Color, ViewTransform } from '../ported/geometry'

const props = withDefaults(defineProps<{
  source: HTMLCanvasElement | null
  /** The op's shapes. Owned by the stack; this component proposes changes. */
  shapes: Shape[]
  displayWidth: number
  displayHeight: number
  tool?: AnnotateTool
  strokeColor?: Color
  fillColor?: Color | null
  strokeWidth?: number
  textStyle?: 'pill' | 'plain' | 'outline' | 'neon'
}>(), {
  tool: 'arrow',
  strokeColor: () => ({ r: 255, g: 255, b: 255, a: 1 }),
  fillColor: null,
  // Pixels, not normalized: the renderer converts positions and sizes out of
  // 0-1 space but assigns strokeWidth to lineWidth directly. A normalized value
  // here draws a sub-pixel line that looks like nothing rendered at all.
  strokeWidth: 8,
  textStyle: 'pill',
})

const emit = defineEmits<{
  /** The whole shape list after a gesture — shapes move and die, not just appear. */
  change: [Shape[]]
  /** A gesture finished and is worth an undo step. */
  commit: [string]
  /** Selection changed, so the inspector can follow it. */
  select: [string | null]
}>()

const overlay = ref<HTMLCanvasElement | null>(null)

// -- the state the ported composable reads and writes -----------------------

const selectedShapeId = ref<string | null>(null)

/**
 * The live shape list.
 *
 * Props cannot serve here. Vue pushes props during the parent's next render,
 * so within one gesture handler `props.shapes` still holds the pre-gesture
 * list — and the ported code reads its own state back inside a single tick.
 * Creating a text box does exactly that: it appends the shape and immediately
 * looks it up to start editing, which silently found nothing and left the box
 * empty and uneditable. The list is therefore owned here and mirrored out.
 */
const shapes = ref<Shape[]>([])
watch(() => props.shapes, incoming => {
  // Only adopt a list this component did not just produce, so a stale prop
  // arriving a tick late cannot roll a gesture back.
  if (incoming !== shapes.value) shapes.value = incoming
}, { immediate: true })

/**
 * Text presets, which the old editor expressed as raw style fields. Kept as
 * the four the sub-bar offers rather than exposing every knob in the toolbar —
 * the per-shape knobs belong in the inspector, where they stay mutable.
 */
const textPreset = computed(() => {
  const colour = props.strokeColor
  switch (props.textStyle) {
    case 'plain':
      return { annotateTextColor: colour, annotateTextBgColor: null, annotateTextFontWeight: 'normal' as const }
    case 'outline':
      return { annotateTextColor: colour, annotateTextBgColor: null, annotateTextEffect: 'outline' as const }
    case 'neon':
      return {
        annotateTextColor: colour, annotateTextBgColor: null,
        annotateTextEffect: 'neon' as const, annotateTextGlowIntensity: 70,
      }
    default:
      return {
        annotateTextColor: colour,
        annotateTextBgColor: { r: 0, g: 0, b: 0, a: 0.65 },
        annotateTextBackgroundPadding: 0.35,
        annotateTextBackgroundCornerRadius: 1,
      }
  }
})

function getState(): AnnotationState {
  return {
    activeTool: props.tool,
    annotations: shapes.value,
    selectedShapeId: selectedShapeId.value,
    annotateStrokeColor: props.strokeColor,
    annotateFillColor: props.fillColor,
    annotateStrokeWidth: props.strokeWidth,
    annotateTextFontFamily: 'Inter, system-ui, sans-serif',
    annotateTextAlign: 'center',
    annotateRedactBlockSize: 16,
    ...textPreset.value,
  }
}

function updateState(partial: Partial<AnnotationState>) {
  if ('selectedShapeId' in partial) {
    selectedShapeId.value = partial.selectedShapeId ?? null
    emit('select', selectedShapeId.value)
  }
  if (partial.annotations) {
    shapes.value = partial.annotations
    emit('change', partial.annotations)
  }
  // activeTool and the style fields are props here: the toolbar owns them, and
  // the composable only ever reads them back through getState.
}

// -- geometry ---------------------------------------------------------------

const imageSize = computed(() =>
  props.source ? { width: props.source.width, height: props.source.height } : null
)
const canvasSize = computed(() => ({ width: props.displayWidth, height: props.displayHeight }))

/**
 * Interaction happens in CSS pixels — the composable measures the element with
 * getBoundingClientRect — so the view zoom is the fit scale. Rendering is a
 * separate space: the backing store is image-sized and the renderer works in
 * image pixels, which is also the space the shapes are stored in.
 */
const viewTransform = computed<ViewTransform>(() => ({
  zoom: imageSize.value ? props.displayWidth / imageSize.value.width : 1,
  panX: 0,
  panY: 0,
  rotation: 0,
}))

const annotation = useAnnotation(
  overlay,
  viewTransform,
  imageSize,
  canvasSize,
  getState,
  updateState,
  (action: string) => emit('commit', action)
)

// -- painting ---------------------------------------------------------------

function draw() {
  const canvas = overlay.value
  const size = imageSize.value
  if (!canvas || !size) return
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  // The source is passed through because redaction samples the pixels it
  // covers rather than painting a flat block over them.
  renderShapes(ctx, shapes.value, size, props.source ?? undefined, annotation.textEditState.value)

  const selected = shapes.value.find(s => s.id === selectedShapeId.value)
  if (selected && !annotation.isEditingTextOnCanvas.value) {
    drawSelectionHandles(
      ctx,
      getShapeBounds(selected, size),
      size,
      selected.rotation,
      getShapeCenter(selected),
      // Handles are drawn in image pixels but read at display size, so they
      // are scaled back down to stay a constant size on screen.
      imageSize.value ? size.width / Math.max(1, props.displayWidth) : 1
    )
  }
}

function resize() {
  const canvas = overlay.value
  const size = imageSize.value
  if (!canvas || !size) return
  canvas.width = size.width
  canvas.height = size.height
  draw()
}

defineExpose({
  /** Typing goes to the canvas, so the view must hold its shortcuts. */
  isEditingText: () => annotation.isEditingTextOnCanvas(),
  /** Delete is a document verb, so the bottom bar can reach it. */
  deleteSelected() {
    if (!selectedShapeId.value) return
    shapes.value = shapes.value.filter(s => s.id !== selectedShapeId.value)
    emit('change', shapes.value)
    emit('commit', 'Delete annotation')
    selectedShapeId.value = null
    emit('select', null)
  },
  clearSelection() {
    selectedShapeId.value = null
    emit('select', null)
  },
})

watch(() => props.source, resize)
watch(
  () => [shapes.value, selectedShapeId.value, annotation.textEditState.value] as const,
  () => nextTick(draw),
  { deep: true }
)
// The composable listens on the canvas element, which only exists after mount.
onMounted(() => {
  resize()
  annotation.setupListeners()
})
onBeforeUnmount(() => annotation.cleanupListeners())
</script>

<template>
  <div class="absolute inset-0">
    <canvas
      ref="overlay"
      class="touch-none"
      :style="{
        width: displayWidth + 'px',
        height: displayHeight + 'px',
        cursor: annotation.cursorStyle.value,
      }"
    />
  </div>
</template>
