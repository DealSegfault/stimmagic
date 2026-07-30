<script setup lang="ts">
/**
 * Point color: pick a color from the image, then shift only it.
 *
 * The picked reference lives in the document (`pointHue/Sat/Lum`); the edit
 * is the shifts around it. Target is the brand-color move: choose the color
 * this SHOULD be — in the same picker used everywhere else — and the shifts
 * are solved the moment the target changes, then stay editable as ordinary
 * sliders afterward. There is no Apply step: picking a color and naming the
 * color it should be is the whole instruction, so a button between them was
 * a click that could only ever be pressed.
 */
import { computed, ref, watch } from 'vue'
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

/**
 * Solve the shifts for the current pick/target pair.
 *
 * Live (uncommitted) while the target is being dragged around the spectrum, so
 * the canvas tracks the drag the way a slider does; the commit lands on
 * release. Both coalesce under one key, so the whole exploration is one undo.
 */
function solveMatch(commit: boolean) {
  if (props.disabled || !targetHsl.value || !hasPicked.value) return
  emit('change', matchShifts(picked.value, targetHsl.value), 'point-match')
  if (commit) emit('commit')
}

// A target chosen before the pick is not a mistake — it is the person saying
// what they want first. It solves as soon as there is something to solve.
watch([targetHsl, hasPicked], () => solveMatch(false))
</script>

<template>
  <div class="space-y-3">
    <!--
      Two wells on one row: the color that IS there, and the color it should
      be. Both are the same 24px swatch, so the row reads as a before/after
      rather than as two unrelated controls, and neither carries a status
      sentence that would wrap the panel at sidebar width.
    -->
    <div class="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
      <div class="space-y-1.5 min-w-0">
        <span class="block text-xs font-semibold text-content-secondary">Picked</span>
        <button
          type="button"
          class="w-full inline-flex items-center gap-2 px-1.5 py-1.5 rounded-md
                 transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60
                 disabled:cursor-not-allowed disabled:opacity-50"
          :class="picking
            ? 'bg-selection/15 text-content'
            : 'bg-surface-raised text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          :disabled="disabled"
          :title="hasPicked ? pickedHex : undefined"
          @click="emit('pick')"
        >
          <span
            class="w-6 h-6 rounded-md border border-edge-strong shrink-0"
            :class="!hasPicked && `[background:repeating-conic-gradient(rgba(255,255,255,.12)_0%_25%,rgba(255,255,255,.04)_0%_50%)_0_0/8px_8px]`"
            :style="hasPicked ? { background: pickedCss } : undefined"
          />
          <span class="text-[11.5px] font-mono truncate">
            {{ picking ? 'Click image' : hasPicked ? pickedHex : 'Pick…' }}
          </span>
        </button>
      </div>

      <span class="pb-2 text-content-tertiary text-xs shrink-0">→</span>

      <div class="space-y-1.5 min-w-0">
        <span class="block text-xs font-semibold text-content-secondary">Target</span>
        <ToolbarPopover label="" :width="272" :disabled="disabled" aria-label="Target color">
          <template #trigger>
            <span class="w-full inline-flex items-center gap-2 px-1.5 py-1.5 rounded-md
                         bg-surface-raised text-content-secondary">
              <span
                class="w-6 h-6 rounded-md border border-edge-strong shrink-0"
                :class="!targetCss && `[background:repeating-conic-gradient(rgba(255,255,255,.12)_0%_25%,rgba(255,255,255,.04)_0%_50%)_0_0/8px_8px]`"
                :style="targetCss ? { background: targetCss } : undefined"
              />
              <span class="text-[11.5px] font-mono truncate">
                {{ targetCss ?? 'Choose…' }}
              </span>
            </span>
          </template>
          <!-- The picker emits per pointer move; the release is the commit,
               exactly as a slider's @change is. -->
          <div @pointerup="solveMatch(true)" @keyup.enter="solveMatch(true)">
            <ColorPicker
              :model-value="targetColor"
              @update:model-value="targetColor = $event"
            />
          </div>
        </ToolbarPopover>
      </div>
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
