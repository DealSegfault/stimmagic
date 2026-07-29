<script setup lang="ts">
/**
 * The strip that floats over a selected annotation.
 *
 * Two things are true of an annotation at once: it is a row in the stack, and
 * it is an object with handles on it. The inspector serves the first — every
 * knob the shape has, in a panel that stays put. This serves the second: the
 * few verbs that are about the object AS an object rather than about its
 * properties, put where the object is so the eye never leaves it.
 *
 * Verbs only, and only the ones with no home in the inspector — text entry,
 * un-rotating, z-order, duplicate, delete. Anything that has a value belongs in
 * Properties, where it stays visible and mutable; a floating strip that also
 * carried settings would be a second, worse inspector that comes and goes.
 *
 * Placement follows the shape's ROTATED bounding box, which is where the
 * selection handles are. When the shape sits too near the top of the frame the
 * strip flips below it rather than leaving the picture — and the two sides need
 * different clearances, because the rotate handle hangs off the bottom edge.
 */
import { computed, ref, watch } from 'vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolIcon from './ToolIcon.vue'
import { getShapeBounds, getShapeCenter } from '../ported/shapes'
import type { Shape } from '../ported/shapeTypes'

const props = defineProps<{
  /** Whether the strip belongs on screen. Not a v-if: it fades. */
  visible: boolean
  shape: Shape | null
  /** Source pixels: some bounds (star) are relative to the frame's mean side. */
  imageSize: { width: number; height: number } | null
  displayWidth: number
  displayHeight: number
  /** Whether a z-order move would actually change anything. */
  canBringToFront: boolean
  canSendToBack: boolean
}>()

const emit = defineEmits<{
  'edit-text': []
  'reset-rotation': []
  'bring-to-front': []
  'send-to-back': []
  duplicate: []
  remove: []
}>()

/**
 * The shape the strip is drawn against, held one beat longer than the
 * selection.
 *
 * Deselecting nulls the shape, and a strip that reads its geometry from the
 * live prop would lose its position on the same frame it was asked to fade —
 * so it would vanish instead. Keeping the last shape lets the fade play out
 * where the shape was; the next selection replaces it outright, because moving
 * between two shapes is a move, not a hide and a show.
 */
const drawn = ref<Shape | null>(null)
watch(() => props.shape, shape => {
  if (shape) drawn.value = shape
}, { immediate: true })

const isText = computed(() => drawn.value?.type === 'text')
const isRotated = computed(() => !!drawn.value?.rotation)

/**
 * The rotated bounding box, in the display box's pixels.
 *
 * Shapes are stored normalized, so a corner rotates about the shape's centre
 * only after both are denormalized — rotating in 0-1 space skews everything
 * drawn on a non-square image.
 */
const placement = computed(() => {
  const shape = drawn.value
  const width = props.displayWidth
  const height = props.displayHeight
  if (!shape || !width || !height) return null

  const bounds = getShapeBounds(shape, props.imageSize ?? undefined)
  const centre = getShapeCenter(shape)
  const cx = centre.x * width
  const cy = centre.y * height
  const rotation = shape.rotation || 0
  const cos = Math.cos(rotation)
  const sin = Math.sin(rotation)

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  const corners: Array<[number, number]> = [
    [bounds.x, bounds.y],
    [bounds.x + bounds.width, bounds.y],
    [bounds.x + bounds.width, bounds.y + bounds.height],
    [bounds.x, bounds.y + bounds.height],
  ]
  for (const [nx, ny] of corners) {
    const dx = nx * width - cx
    const dy = ny * height - cy
    const x = cx + dx * cos - dy * sin
    const y = cy + dx * sin + dy * cos
    minX = Math.min(minX, x); maxX = Math.max(maxX, x)
    minY = Math.min(minY, y); maxY = Math.max(maxY, y)
  }
  if (!Number.isFinite(minX)) return null

  // Above the shape there is only the dashed border and the two top corner
  // handles (7px radius) to clear, so the strip sits close — it belongs to the
  // shape, and distance reads as belonging to something else.
  const gapAbove = 16
  // Below is a different story: the rotate handle hangs off the BOTTOM edge on
  // a stem 0.03 of the frame's height long, and the strip has to clear the
  // lollipop at the end of it.
  const gapBelow = height * 0.03 + 24
  // A strip is about 34px tall; below that there is no room above the shape.
  const above = minY - gapAbove > 38

  return {
    left: `${Math.min(Math.max((minX + maxX) / 2, 0), width)}px`,
    top: `${above ? minY - gapAbove : maxY + gapBelow}px`,
    transform: above ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
  }
})

function buttonClass(enabled = true) {
  return enabled
    ? 'text-content-secondary hover:text-content hover:bg-overlay-subtle'
    : 'text-content-tertiary/50 cursor-default'
}
</script>

<template>
  <!-- The strip is chrome that comes and goes over the picture, so it fades
       rather than blinking. `pointer-events-none` while leaving: a strip on
       its way out must not still be catching clicks. -->
  <Transition
    enter-active-class="transition-opacity duration-150"
    leave-active-class="transition-opacity duration-150 pointer-events-none"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible && drawn && placement"
      class="absolute flex items-center gap-1 px-1.5 py-1 w-max
             bg-surface border border-edge-subtle rounded-lg shadow-lg"
      :style="placement"
    >
      <Tooltip v-if="isText" text="Edit text">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass()"
          aria-label="Edit text"
          @click.stop="emit('edit-text')"
        >
          <ToolIcon name="pencil" />
        </button>
      </Tooltip>

      <Tooltip v-if="isRotated" text="Reset rotation">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass()"
          aria-label="Reset rotation"
          @click.stop="emit('reset-rotation')"
        >
          <ToolIcon name="rotateCcw" />
        </button>
      </Tooltip>

      <Tooltip text="Bring to front">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass(canBringToFront)"
          aria-label="Bring to front"
          :disabled="!canBringToFront"
          @click.stop="emit('bring-to-front')"
        >
          <ToolIcon name="arrowUp" />
        </button>
      </Tooltip>

      <Tooltip text="Send to back">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass(canSendToBack)"
          aria-label="Send to back"
          :disabled="!canSendToBack"
          @click.stop="emit('send-to-back')"
        >
          <ToolIcon name="arrowDown" />
        </button>
      </Tooltip>

      <Tooltip text="Duplicate">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass()"
          aria-label="Duplicate"
          @click.stop="emit('duplicate')"
        >
          <ToolIcon name="copy" />
        </button>
      </Tooltip>

      <span class="w-px h-5 bg-edge-subtle mx-0.5" />

      <Tooltip text="Delete">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors text-content-tertiary hover:text-red-400 hover:bg-overlay-subtle"
          aria-label="Delete annotation"
          @click.stop="emit('remove')"
        >
          <ToolIcon name="trash" />
        </button>
      </Tooltip>
    </div>
  </Transition>
</template>
