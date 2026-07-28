<script setup lang="ts">
/**
 * Crop, on the image as it stands BELOW the crop step.
 *
 * The point of showing the uncropped image is that a crop is not destructive
 * here: the region outside it is dimmed rather than gone, so widening the crop
 * later reveals real pixels instead of edge-clamped ones. The step's input is
 * what is drawn; the crop rectangle is the bright window over it.
 *
 * The overlay and the gesture maths are the snapshot editor's, copied into
 * `imageEditor/ported/` — the even-odd dim, the dashed border, the rule of
 * thirds that follows the rotation, the corner handles, and the rotation
 * lollipop hanging perpendicular to the bottom edge. The aspect-locked corner
 * drag projects onto the aspect diagonal, which is the difference between a
 * crop that tracks the pointer and one that snaps between axes.
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useCropInteraction } from '../../imageEditor/ported/useCropInteraction'
import type { CropRect } from '../../imageEditor/ported/useCropInteraction'
import { drawCropOverlay } from '../../imageEditor/ported/cropOverlay'
import type { ViewTransform } from '../../imageEditor/ported/geometry'

const props = defineProps<{
  /** The composite BELOW the crop step — the uncropped image. */
  source: HTMLCanvasElement | null
  crop: CropRect
  /** The viewport the image is fitted into. */
  viewWidth: number
  viewHeight: number
}>()

const emit = defineEmits<{
  change: [CropRect]
  /** A drag ended: one undo step. */
  commit: []
}>()

const canvas = ref<HTMLCanvasElement | null>(null)

/** Clearance for corner handles and the rotation lollipop, in canvas pixels. */
const HANDLE_MARGIN = 44

const imageSize = computed(() =>
  props.source ? { width: props.source.width, height: props.source.height } : null
)
const canvasSize = computed(() => ({ width: props.viewWidth, height: props.viewHeight }))

/**
 * The image is fitted, never panned or zoomed, so the transform the ported
 * code takes is just the fit scale. It is left as a real ViewTransform so the
 * copied maths is untouched.
 */
const viewTransform = computed<ViewTransform>(() => {
  const size = imageSize.value
  if (!size || !props.viewWidth || !props.viewHeight) {
    return { zoom: 1, panX: 0, panY: 0, rotation: 0 }
  }
  // Leave room around the image for the handles and the rotation lollipop.
  // Fitting edge-to-edge puts the lollipop off-canvas the moment the crop
  // reaches the bottom of the frame, which is its starting state.
  const margin = HANDLE_MARGIN * 2
  const zoom = Math.min(
    (props.viewWidth - margin) / size.width,
    (props.viewHeight - margin) / size.height,
    1
  )
  return { zoom, panX: 0, panY: 0, rotation: 0 }
})

const crop = useCropInteraction(
  canvas,
  viewTransform,
  imageSize,
  canvasSize,
  () => props.crop,
  next => emit('change', next),
  () => emit('commit')
)

function draw() {
  const element = canvas.value
  const size = imageSize.value
  if (!element || !size) return
  const ctx = element.getContext('2d')!
  const { zoom } = viewTransform.value

  ctx.clearRect(0, 0, element.width, element.height)

  const width = size.width * zoom
  const height = size.height * zoom
  ctx.drawImage(
    props.source!,
    (props.viewWidth - width) / 2,
    (props.viewHeight - height) / 2,
    width,
    height
  )

  drawCropOverlay(ctx, props.crop, viewTransform.value, size, canvasSize.value)
}

function resize() {
  const element = canvas.value
  if (!element) return
  element.width = props.viewWidth
  element.height = props.viewHeight
  draw()
}

watch(() => [props.viewWidth, props.viewHeight], resize)
watch(() => props.source, resize)
watch(() => props.crop, () => nextTick(draw), { deep: true })

onMounted(() => {
  resize()
  crop.setupListeners()
})
onBeforeUnmount(() => crop.cleanupListeners())
</script>

<template>
  <canvas
    ref="canvas"
    class="absolute inset-0 touch-none"
    :style="{
      width: viewWidth + 'px',
      height: viewHeight + 'px',
      cursor: crop.cursorStyle.value,
    }"
  />
</template>
