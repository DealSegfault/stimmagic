<script setup lang="ts">
/**
 * The Mixer's control surface: one mode (Hue / Saturation / Luminance) shown
 * at a time over the eight fixed hue bands. The document keys are plain
 * sliders (`mixerHueRed`…); only this presentation is special.
 */
import { ref } from 'vue'
import {
  MIXER_BANDS,
  MIXER_MODES,
  mixerKey,
  type MixerMode,
} from '../stack/adjustSections'

const props = defineProps<{
  values: Record<string, any>
  disabled?: boolean
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
}>()

const mode = ref<MixerMode>('Hue')

function bandValue(band: (typeof MIXER_BANDS)[number]) {
  const value = props.values?.[mixerKey(mode.value, band.id)]
  return typeof value === 'number' ? value : 0
}

function setBand(band: (typeof MIXER_BANDS)[number], value: number) {
  const key = mixerKey(mode.value, band.id)
  emit('change', { [key]: value }, key)
}

function reset() {
  if (props.disabled) return
  const patch = Object.fromEntries(
    MIXER_MODES.flatMap(candidate =>
      MIXER_BANDS.map(band => [mixerKey(candidate.id, band.id), 0]),
    ),
  )
  emit('change', patch, 'mixer-reset')
  emit('commit')
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between gap-2">
      <div class="inline-flex items-center gap-0.5" role="radiogroup" aria-label="Mixer mode">
        <button
          v-for="option in MIXER_MODES"
          :key="option.id"
          type="button"
          class="rounded-md px-2 py-1 text-[11px] font-medium transition-colors duration-150
                 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="mode === option.id
            ? 'bg-selection/15 text-content'
            : 'text-content-tertiary hover:bg-overlay-subtle hover:text-content'"
          role="radio"
          :aria-checked="mode === option.id"
          @click="mode = option.id"
        >
          {{ option.label }}
        </button>
      </div>
      <button
        type="button"
        class="rounded-md px-2 py-1 text-[11px] text-content-tertiary
               hover:bg-overlay-subtle hover:text-content transition-colors duration-150
               focus-visible:outline-none focus-visible:ring-2 ring-accent/60
               disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="disabled"
        @click="reset"
      >
        Reset
      </button>
    </div>

    <label
      v-for="band in MIXER_BANDS"
      :key="band.id"
      class="grid grid-cols-[74px_1fr_42px] items-center gap-2 text-xs"
    >
      <span class="flex items-center gap-1.5 text-content-tertiary">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :style="{ background: band.swatch }"
        />
        {{ band.label }}
      </span>
      <input
        type="range"
        class="min-w-0"
        min="-100"
        max="100"
        step="1"
        :style="{ accentColor: band.swatch }"
        :disabled="disabled"
        :value="bandValue(band)"
        :aria-label="`${band.label} ${mode.toLowerCase()}`"
        @input="setBand(band, Number(($event.target as HTMLInputElement).value))"
        @change="emit('commit')"
      />
      <span class="text-right font-mono tabular-nums text-content-secondary">
        {{ bandValue(band) }}
      </span>
    </label>
  </div>
</template>
