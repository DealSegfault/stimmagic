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
 * Placement follows the selection's ROTATED bounds, which is where the
 * selection handles are. A multi-selection gets the shared object verbs while
 * shape-specific verbs stay hidden.
 */
import { computed, ref, watch } from 'vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolIcon from './ToolIcon.vue'
import { getShapeBounds, getShapeCenter } from '../ported/shapes'
import { rotatedBounds } from '../ported/annotationSelection'
import type { Shape } from '../ported/shapeTypes'

const props = defineProps<{
  /** Whether the strip belongs on screen. Not a v-if: it fades. */
  visible: boolean
  shapes: Shape[]
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
 * The selection the strip is drawn against, held one beat longer than the
 * selection.
 *
 * Deselecting empties the selection, and a strip that reads its geometry from
 * the live prop would lose its position on the same frame it was asked to
 * fade. Keeping the last non-empty selection lets the fade finish in place.
 */
const drawn = ref<Shape[]>([])
watch(() => props.shapes, shapes => {
  if (shapes.length) drawn.value = [...shapes]
}, { immediate: true })

const isMultiple = computed(() => drawn.value.length > 1)
const isText = computed(() => drawn.value.length === 1 && drawn.value[0]?.type === 'text')
const isRotated = computed(() => drawn.value.length === 1 && !!drawn.value[0]?.rotation)
const duplicateLabel = computed(() =>
  isMultiple.value ? `Duplicate ${drawn.value.length} annotations` : 'Duplicate'
)
const deleteLabel = computed(() =>
  isMultiple.value ? `Delete ${drawn.value.length} annotations` : 'Delete'
)

/**
 * The union of every rotated shape bound, in the display box's pixels.
 *
 * Shapes are stored normalized, so a corner rotates about the shape's centre
 * only after both are denormalized — rotating in 0-1 space skews everything
 * drawn on a non-square image.
 */
const placement = computed(() => {
  const width = props.displayWidth
  const height = props.displayHeight
  const imageSize = props.imageSize ?? { width, height }
  if (!drawn.value.length || !width || !height) return null

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  for (const shape of drawn.value) {
    const bounds = rotatedBounds(
      getShapeBounds(shape, imageSize),
      getShapeCenter(shape),
      shape.rotation || 0,
      imageSize
    )
    minX = Math.min(minX, bounds.x * width)
    maxX = Math.max(maxX, (bounds.x + bounds.width) * width)
    minY = Math.min(minY, bounds.y * height)
    maxY = Math.max(maxY, (bounds.y + bounds.height) * height)
  }
  if (!Number.isFinite(minX)) return null

  // Above the shape there is only the dashed border and the two top corner
  // handles (7px radius) to clear, so the strip sits close — it belongs to the
  // shape, and distance reads as belonging to something else.
  const gapAbove = 16
  // A single object has a rotate lollipop below it; a group does not.
  const gapBelow = isMultiple.value ? 16 : height * 0.03 + 24
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
      v-if="visible && drawn.length && placement"
      class="absolute flex items-center gap-1 px-1.5 py-1 w-max
             bg-surface border border-edge-subtle rounded-lg shadow-lg"
      :style="placement"
    >
      <span
        v-if="isMultiple"
        class="px-1.5 text-xs font-mono tabular-nums text-content-tertiary"
      >
        {{ drawn.length }} selected
      </span>

      <span v-if="isMultiple" class="w-px h-5 bg-edge-subtle mx-0.5" />

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

      <Tooltip :text="duplicateLabel">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="buttonClass()"
          :aria-label="duplicateLabel"
          @click.stop="emit('duplicate')"
        >
          <ToolIcon name="copy" />
        </button>
      </Tooltip>

      <span class="w-px h-5 bg-edge-subtle mx-0.5" />

      <Tooltip :text="deleteLabel">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors text-content-tertiary hover:text-red-400 hover:bg-overlay-subtle"
          :aria-label="deleteLabel"
          @click.stop="emit('remove')"
        >
          <ToolIcon name="trash" />
        </button>
      </Tooltip>
    </div>
  </Transition>
</template>
