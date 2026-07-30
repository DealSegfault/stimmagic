<script setup lang="ts">
/**
 * Point color: pick a color from the image, then shift only it.
 *
 * The picked reference lives in the document (`pointHue/Sat/Lum`); the edit
 * is the shifts around it. Target-match is the brand-color move: choose the
 * color this SHOULD be — in the same picker used everywhere else, which takes
 * a hex — and Match solves the shifts, which stay editable as ordinary
 * sliders afterward.
 */
import { computed, ref } from 'vue'
import ColorPicker from '../ported/ColorPicker.vue'
import ToolbarPopover from './ToolbarPopover.vue'
import {
  hslToHex,
  matchShifts,
  rgbToHslColor,
} from '../stack/pointColorMatch'

interface RgbaTarget {
  r: number
  g: number
  b: number
  a?: number
}

const props = defineProps<{
  values: Record<string, any>
  disabled?: boolean
  /** Whether the eyedropper is currently armed on the canvas. */
  picking?: boolean
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
  /** Ask the host view to arm the canvas eyedropper for this step. */
  pick: []
}>()

/** Session helper, not document state: the shifts are what persists. */
const targetColor = ref<RgbaTarget | null>(null)

function numberOf(key: string, fallback = 0) {
  const value = props.values?.[key]
  return typeof value === 'number' ? value : fallback
}

const picked = computed(() => ({
  hue: numberOf('pointHue'),
  sat: numberOf('pointSat'),
  lum: numberOf('pointLum'),
}))

/** No pick yet reads as an empty well rather than "black was picked". */
const hasPicked = computed(() =>
  picked.value.sat !== 0 || picked.value.lum !== 0 || picked.value.hue !== 0,
)

const pickedCss = computed(() =>
  `hsl(${picked.value.hue} ${picked.value.sat}% ${picked.value.lum}%)`,
)
const pickedHex = computed(() => hslToHex(picked.value))

const targetHsl = computed(() =>
  targetColor.value
    ? rgbToHslColor(targetColor.value.r, targetColor.value.g, targetColor.value.b)
    : null,
)
const targetCss = computed(() =>
  targetHsl.value ? hslToHex(targetHsl.value) : null,
)

const SLIDERS = [
  { key: 'pointHueShift', label: 'Hue shift', min: -180, max: 180, default: 0 },
  { key: 'pointSatShift', label: 'Saturation', min: -100, max: 100, default: 0 },
  { key: 'pointLumShift', label: 'Luminance', min: -100, max: 100, default: 0 },
  { key: 'pointRange', label: 'Range', min: 0, max: 100, default: 50 },
] as const

function sliderValue(slider: (typeof SLIDERS)[number]) {
  return numberOf(slider.key, slider.default)
}

function setValue(key: string, value: number) {
  emit('change', { [key]: value }, key)
}

function applyMatch() {
  if (props.disabled || !targetHsl.value || !hasPicked.value) return
  emit('change', matchShifts(picked.value, targetHsl.value), 'point-match')
  emit('commit')
}
</script>

<template>
  <div class="space-y-3">
    <div class="space-y-1.5">
      <span class="block text-xs font-semibold text-content-secondary">Picked color</span>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md
                 transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60
                 disabled:cursor-not-allowed disabled:opacity-50"
          :class="picking
            ? 'bg-selection/15 text-content'
            : 'bg-surface-raised text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          :disabled="disabled"
          @click="emit('pick')"
        >
          <svg viewBox="0 0 24 24" class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m2 22 1-1h3l9-9" /><path d="M3 21v-3l9-9" />
            <path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8a2.1 2.1 0 1 1 3-3l.4.4Z" />
          </svg>
          {{ picking ? 'Click the image…' : 'Pick from image' }}
        </button>
        <span
          v-if="hasPicked"
          class="w-6 h-6 rounded-md border border-edge-strong shrink-0"
          :style="{ background: pickedCss }"
          :title="pickedHex"
        />
        <span v-else class="text-[11px] text-content-tertiary">Nothing picked yet</span>
      </div>
    </div>

    <div class="space-y-1.5">
      <span class="block text-xs font-semibold text-content-secondary">Target</span>
      <div class="flex items-center gap-2">
        <ToolbarPopover label="" :width="272" :disabled="disabled" aria-label="Target color">
          <template #trigger>
            <span class="inline-flex items-center gap-1.5">
              <span
                class="w-6 h-6 rounded-md border border-edge-strong shrink-0"
                :class="!targetCss && `[background:repeating-conic-gradient(rgba(255,255,255,.12)_0%_25%,rgba(255,255,255,.04)_0%_50%)_0_0/8px_8px]`"
                :style="targetCss ? { background: targetCss } : undefined"
              />
              <span class="text-[11.5px] font-mono text-content-secondary">
                {{ targetCss ?? 'Choose…' }}
              </span>
            </span>
          </template>
          <ColorPicker
            :model-value="targetColor"
            @update:model-value="targetColor = $event"
          />
        </ToolbarPopover>
        <div class="flex-1" />
        <button
          type="button"
          class="px-2.5 py-1 text-[11.5px] rounded-md bg-accent/15 text-accent-hi
                 transition-colors hover:bg-accent/25
                 focus-visible:outline-none focus-visible:ring-2 ring-accent/60
                 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="disabled || !targetColor || !hasPicked"
          @click="applyMatch"
        >
          Match
        </button>
      </div>
      <p class="text-[11px] text-content-tertiary">
        Match sets the shifts below so the picked color lands on the target.
      </p>
    </div>

    <div class="space-y-2">
      <label
        v-for="slider in SLIDERS"
        :key="slider.key"
        class="grid grid-cols-[74px_1fr_42px] items-center gap-2 text-xs"
      >
        <span class="text-content-tertiary">{{ slider.label }}</span>
        <input
          type="range"
          class="min-w-0"
          :min="slider.min"
          :max="slider.max"
          step="1"
          :disabled="disabled"
          :value="sliderValue(slider)"
          @input="setValue(slider.key, Number(($event.target as HTMLInputElement).value))"
          @change="emit('commit')"
        />
        <span class="text-right font-mono tabular-nums text-content-secondary">
          {{ sliderValue(slider) }}
        </span>
      </label>
    </div>
  </div>
</template>
