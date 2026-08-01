<script setup lang="ts">
/**
 * A color well's contents: a flat color, or a gradient.
 *
 * Gradient is not a mode of the annotation, it is a kind of color — so it
 * lives here, next to Solid, rather than as an effect the shape has to be put
 * into. Every well that paints something can offer it, which is what makes a
 * gradient stroke around a solid fill expressible at all.
 *
 * ONE screen at a time. Gradient mode shows the gradient; picking a color in
 * it opens the ordinary color picker for that stop, titled with the stop it
 * belongs to. Showing both at once was two pickers with nothing binding them —
 * the panel could not say which half you were meant to be reading, and the
 * color picker never said which color it was editing.
 */
import { computed, ref, watch } from 'vue'
import ColorPicker from '../ported/ColorPicker.vue'
import GradientEditor from './GradientEditor.vue'
import ToolIcon from './ToolIcon.vue'
import type { Color } from '../ported/geometry'
import type { GradientPaint, Paint } from '../ported/shapeTypes'
import { isGradient, paintSolid, gradientFromSolid, makeGradient, colorCss } from '../stack/paints'

const props = withDefaults(defineProps<{
  modelValue: Paint | null
  /** Whether this slot can hold a gradient at all. */
  allowGradient?: boolean
  /** Gradient-tool picker: no Solid tab, and the drag owns direction. */
  gradientOnly?: boolean
  /** Whether "no fill" is a legal value. */
  allowNull?: boolean
  imagePalette?: Color[]
}>(), {
  allowGradient: false,
  gradientOnly: false,
  allowNull: false,
})

const emit = defineEmits<{
  'update:modelValue': [Paint | null]
}>()

const mode = computed<'solid' | 'gradient'>(() =>
  isGradient(props.modelValue) ? 'gradient' : 'solid'
)

/** Which stop the color screen is open on, or null on the gradient screen. */
const editing = ref<number | null>(null)

const stops = computed<Color[]>(() =>
  isGradient(props.modelValue) ? (props.modelValue.colors ?? []) : []
)

/** A stop can vanish under the open screen — from an undo, or another well. */
watch(() => props.modelValue, value => {
  if (!isGradient(value)) editing.value = null
  else if (editing.value !== null && editing.value > (value.colors?.length ?? 0) - 1) {
    editing.value = null
  }
})

/**
 * Switching modes carries the color across rather than replacing it: a solid
 * becomes a gradient starting at that color, and a gradient collapses to its
 * first stop.
 */
function chooseMode(next: 'solid' | 'gradient') {
  if (next === mode.value) return
  editing.value = null
  emit('update:modelValue', next === 'gradient'
    ? gradientFromSolid(paintSolid(props.modelValue))
    : paintSolid(props.modelValue))
}

/** What the color screen is bound to: the whole paint, or one of its stops. */
const pickerColor = computed<Color | null>(() => {
  if (!isGradient(props.modelValue)) return props.modelValue
  return props.modelValue.colors?.[editing.value ?? 0] ?? null
})

function onPickerChange(color: Color | null) {
  const paint = props.modelValue
  if (!isGradient(paint) || editing.value === null) {
    emit('update:modelValue', color)
    return
  }
  // A gradient stop cannot be "no fill"; that answer belongs to the whole well.
  if (!color) return
  const colors = [...(paint.colors ?? [])]
  colors[editing.value] = color
  emit('update:modelValue', makeGradient(colors, paint.direction))
}

function onGradientChange(paint: GradientPaint) {
  emit('update:modelValue', paint)
}

function removeEditingStop() {
  const paint = props.modelValue
  if (!isGradient(paint) || editing.value === null) return
  const colors = (paint.colors ?? []).filter((_, i) => i !== editing.value)
  if (colors.length < 2) return
  emit('update:modelValue', makeGradient(colors, paint.direction))
  editing.value = null
}

const MODES = [
  { id: 'solid', label: 'Solid' },
  { id: 'gradient', label: 'Gradient' },
] as const

/** The color screen is showing when there is no gradient to stand in front. */
const showingColor = computed(() => mode.value === 'solid' || editing.value !== null)
</script>

<template>
  <div class="space-y-2.5">
    <!-- One navigation per screen: the mode tabs on the gradient screen, the
         back arrow on the color screen. -->
    <div v-if="allowGradient && !gradientOnly && editing === null" class="flex gap-0.5 p-0.5 bg-surface-overlay rounded-lg">
      <button
        v-for="option in MODES"
        :key="option.id"
        type="button"
        class="flex-1 py-1 text-[11px] rounded-md transition-colors"
        :class="mode === option.id
          ? 'bg-surface-raised text-content'
          : 'text-content-secondary hover:text-content'"
        @click="chooseMode(option.id)"
      >
        {{ option.label }}
      </button>
    </div>

    <div v-else-if="editing !== null" class="flex items-center gap-2">
      <button
        type="button"
        class="flex items-center gap-1.5 -ml-1 px-1 py-0.5 rounded-md text-content-secondary
               hover:text-content hover:bg-overlay-subtle transition-colors"
        @click="editing = null"
      >
        <ToolIcon name="chevronLeft" />
        <span
          class="w-4 h-4 rounded border border-edge-strong"
          :style="{ background: colorCss(stops[editing]) }"
        />
        <span class="text-[11px]">Color {{ editing + 1 }} of {{ stops.length }}</span>
      </button>
      <span class="flex-1" />
      <button
        v-if="stops.length > 2"
        type="button"
        class="text-[11px] text-content-tertiary hover:text-red-400 transition-colors"
        @click="removeEditingStop"
      >
        Remove
      </button>
    </div>

    <GradientEditor
      v-if="(allowGradient || gradientOnly) && isGradient(modelValue) && editing === null"
      :paint="modelValue"
      :show-directions="!gradientOnly"
      @update:paint="onGradientChange"
      @edit="editing = $event"
    />

    <ColorPicker
      v-if="showingColor"
      :model-value="pickerColor"
      :image-palette="imagePalette"
      :allow-null="allowNull && mode === 'solid'"
      embedded
      @update:model-value="onPickerChange"
    />
  </div>
</template>
