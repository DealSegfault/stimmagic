<script setup lang="ts">
/**
 * The gradient itself: which colors, in which order, running which way.
 *
 * It shows no color picker. Picking a color is a separate screen — see
 * PaintPicker — because a gradient panel and a color panel open together are
 * two pickers with nothing binding them, and the eye cannot tell which one it
 * is meant to be reading.
 */
import { computed } from 'vue'
import type { Color } from '../ported/geometry'
import type { GradientDirection, GradientPaint } from '../ported/shapeTypes'
import { paintCss, colorCss, makeGradient, presetGradients, cssAngle } from '../stack/paints'

const props = defineProps<{
  paint: GradientPaint
}>()

const emit = defineEmits<{
  'update:paint': [GradientPaint]
  /** Open the color screen for this stop. */
  edit: [number]
}>()

const MAX_STOPS = 3

const stops = computed<Color[]>(() => props.paint.colors ?? [])
const presets = computed(() => presetGradients(props.paint.direction))

const DIRECTIONS: { id: GradientDirection; label: string }[] = [
  { id: 'horizontal', label: 'Horizontal' },
  { id: 'vertical', label: 'Vertical' },
  { id: 'diagonal', label: 'Diagonal' },
]

function samePreset(preset: GradientPaint) {
  return preset.colors.length === stops.value.length &&
    preset.colors.every((c, i) => {
      const stop = stops.value[i]
      return stop && c.r === stop.r && c.g === stop.g && c.b === stop.b
    })
}

/** A new stop repeats the last color, then opens for editing — nobody adds a
 *  stop in order to keep the color it arrived with. */
function addStop() {
  if (stops.value.length >= MAX_STOPS) return
  const last = stops.value[stops.value.length - 1]
  emit('update:paint', makeGradient([...stops.value, { ...last }], props.paint.direction))
  emit('edit', stops.value.length)
}
</script>

<template>
  <div>
    <span class="block mt-3 first:mt-0 mb-1.5 text-[10.5px] tracking-wide uppercase text-content-tertiary">Gradient</span>
    <div
      class="h-[26px] rounded-md border border-edge-strong"
      :style="{ background: paintCss(paint, '90deg') }"
    />

    <div class="flex items-center gap-1.5 mt-2">
      <button
        v-for="(color, index) in stops"
        :key="index"
        type="button"
        class="w-6 h-6 rounded-md border border-edge-strong hover:ring-1 hover:ring-selection transition-shadow"
        :style="{ background: colorCss(color) }"
        :title="`Color ${index + 1}`"
        :aria-label="`Edit color ${index + 1}`"
        @click="emit('edit', index)"
      />
      <button
        v-if="stops.length < MAX_STOPS"
        type="button"
        class="w-6 h-6 rounded-md border border-dashed border-edge-subtle
               text-content-tertiary hover:text-content hover:border-edge-strong text-xs leading-none"
        aria-label="Add color"
        title="Add color"
        @click="addStop"
      >
        +
      </button>

      <span class="flex-1" />

      <div class="flex items-center gap-1">
        <button
          v-for="option in DIRECTIONS"
          :key="option.id"
          type="button"
          class="w-8 h-6 rounded-md border transition-colors grid place-items-center"
          :class="paint.direction === option.id
            ? 'border-selection bg-selection/15'
            : 'border-edge-subtle hover:border-edge-strong'"
          :title="option.label"
          :aria-label="option.label"
          @click="emit('update:paint', makeGradient(stops, option.id))"
        >
          <span
            class="block w-5 h-2.5 rounded-sm"
            :style="{ background: paintCss(paint, cssAngle(option.id)) }"
          />
        </button>
      </div>
    </div>

    <!-- Presets are how a gradient STARTS, so they sit below the thing they
         would replace rather than above it. -->
    <span class="block mt-3 first:mt-0 mb-1.5 text-[10.5px] tracking-wide uppercase text-content-tertiary">Presets</span>
    <div class="grid grid-cols-6 gap-1">
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        class="h-[18px] rounded border transition-colors"
        :class="samePreset(preset.paint)
          ? 'border-selection ring-1 ring-selection'
          : 'border-edge-subtle hover:border-edge-strong'"
        :title="preset.name"
        :aria-label="preset.name"
        :style="{ background: paintCss(preset.paint) }"
        @click="emit('update:paint', makeGradient(preset.paint.colors, paint.direction))"
      />
    </div>
  </div>
</template>
