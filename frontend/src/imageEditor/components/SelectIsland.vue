<script setup lang="ts">
/**
 * The selection island: a floating pill at the bottom of the canvas, the same
 * shape as the browser's selection bar. All of selection lives here — the
 * tools, the combine modes, one fixed slider slot for the armed tool's primary
 * parameter, invert/deselect — floating OVER the matte, so nothing about
 * arming a tool or opening a family ever pushes the canvas or the toolbars
 * around.
 *
 * Every control is ALWAYS present; what varies is only whether it is enabled.
 * A bar that reshapes as tools arm and disarm makes the eye re-find every
 * control on every change — dimming is calm, appearing is jumpy. Settings
 * only: the island never carries one-off actions.
 *
 * Selection is workspace state, not a mode: clicking a tool arms it (the
 * pointer goes to the selection overlay, the open family is suspended, not
 * left); clicking the armed tool — or reaching for any family control that
 * wants the canvas back — disarms it.
 */
import { computed, nextTick, ref, watch } from 'vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolIcon from './ToolIcon.vue'
import ToolbarPopover from './ToolbarPopover.vue'
import { SELECT_TOOLS, SELECTION_MODES } from '../stack/toolFamilies'
import type { SelectToolId, SelectionMode } from '../stack/toolFamilies'
import {
  FEATHER_SLIDER_MAX,
  featherPxFromSlider,
  featherSliderFromPx,
} from '../stack/featherScale'

const props = defineProps<{
  armed: SelectToolId | null
  hasSelection: boolean
  combine: SelectionMode
  featherPx: number
  tolerance: number
  spread: number
  growPx: number
  antialias: boolean
  brushSize: number
  /** Ease on a fresh linear ramp, 0-100. */
  gradientSoftness: number
  /** Falloff share on a fresh ellipse, 2-100. */
  gradientFeather: number
  /**
   * The pointer — object select — is the workspace's IDLE state, not an armed
   * tool: this is true when no family is open and no region tool is armed.
   */
  pointerActive?: boolean
  /** A prompt-to-mask request is in flight; the field shows it and re-arms after. */
  aiBusy?: boolean
  /** The last prompt-to-mask failure, shown on the field until the next keystroke. */
  aiError?: string | null
}>()

const emit = defineEmits<{
  arm: [SelectToolId]
  pointer: []
  set: [Record<string, any>]
  invert: []
  clear: []
  aiSelect: [string]
}>()

/** Combine describes how the next gesture meets the visible selection, so its
 * state remains visible/editable after a one-shot workflow disarms the tool. */
const combineEnabled = computed(() => props.armed !== null || props.hasSelection)
const toolSettingsEnabled = computed(() => props.armed !== null)

/**
 * The Object tool's popup: arming the tool raises a small panel above the
 * island carrying its second gesture — select by NAME — beside the caption
 * for its first (click the thing). It lives with the tool rather than on the
 * island row because the field is meaningless while a geometric tool owns the
 * pointer; disarming folds it away. The typed prompt survives a run —
 * re-running and refining are the common follow-ups.
 */
const aiPrompt = ref('')
const shownAiError = ref<string | null>(null)
const aiInput = ref<HTMLInputElement | null>(null)
watch(() => props.aiError, value => { shownAiError.value = value ?? null })
watch(() => props.armed, armed => {
  if (armed === 'object') nextTick(() => aiInput.value?.focus())
  else shownAiError.value = null
})

function submitAiPrompt() {
  const prompt = aiPrompt.value.trim()
  if (!prompt || props.aiBusy) return
  emit('aiSelect', prompt)
}

/**
 * ONE slider slot, fixed geometry; each tool brings its primary parameter.
 * Only the label, range and binding swap when a tool arms — a readout
 * changing, not a layout change, so no click target ever moves. The wand's
 * secondary refinements live in the fixed options slot beside the slider.
 */
const SLIDER_SLOTS = {
  feather: { label: 'Feather', key: 'featherPx', min: 0, max: FEATHER_SLIDER_MAX, unit: 'px' },
  tolerance: { label: 'Threshold', key: 'tolerance', min: 1, max: 100, unit: '' },
  brush: { label: 'Brush', key: 'selectBrushSize', min: 8, max: 300, unit: 'px' },
  // A ramp's ease and an ellipse's falloff are the same idea and deliberately
  // not the same number: 100% softness on a ramp has no edge left, while 100%
  // feather on an ellipse still ends somewhere.
  softness: { label: 'Softness', key: 'gradientSoftness', min: 0, max: 100, unit: '' },
  falloff: { label: 'Feather', key: 'gradientFeather', min: 2, max: 100, unit: '' },
} as const

const slot = computed(() => {
  if (props.armed === 'wand') return SLIDER_SLOTS.tolerance
  if (props.armed === 'brush') return SLIDER_SLOTS.brush
  if (props.armed === 'linear') return SLIDER_SLOTS.softness
  if (props.armed === 'radial') return SLIDER_SLOTS.falloff
  return SLIDER_SLOTS.feather
})

const slotValue = computed(() => {
  if (props.armed === 'wand') return props.tolerance
  if (props.armed === 'brush') return props.brushSize
  if (props.armed === 'linear') return props.gradientSoftness
  if (props.armed === 'radial') return props.gradientFeather
  return featherSliderFromPx(props.featherPx)
})

const slotReadout = computed(() =>
  slot.value.key === 'featherPx' ? props.featherPx : slotValue.value
)

function onSliderInput(value: number) {
  if (slot.value.key === 'featherPx') {
    emit('set', { featherPx: featherPxFromSlider(value) })
    return
  }
  emit('set', { [slot.value.key]: value })
}

function buttonClass(active: boolean, enabled = true) {
  if (!enabled) return 'text-content-tertiary/50 cursor-default'
  return active
    ? 'bg-selection/15 text-content'
    : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'
}

function sliderClass(enabled: boolean) {
  return enabled ? '' : 'opacity-40 pointer-events-none'
}
</script>

<template>
  <!-- The host positions this root (absolute over the matte); that same
       positioning is what the tool panel's `absolute bottom-full` anchors to,
       so the wrapper must NOT add a position class of its own. -->
  <div class="w-max">
  <!-- The Object tool's panel, raised over the island while the tool is
       armed. Both of the tool's gestures are stated here: the field for
       select-by-name, the caption for click-to-select. -->
  <Transition
    enter-active-class="transition duration-150 ease-out"
    enter-from-class="opacity-0 translate-y-1"
    leave-active-class="transition duration-100 ease-in"
    leave-to-class="opacity-0 translate-y-1"
  >
    <div
      v-if="armed === 'object'"
      class="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 w-max
             px-2.5 py-2 space-y-1.5
             bg-surface border border-edge-subtle rounded-lg shadow-lg"
    >
      <div class="flex items-center gap-1.5">
        <input
          ref="aiInput"
          v-model="aiPrompt"
          type="text"
          placeholder="Select by name, or click the object…"
          aria-label="Select by name"
          class="w-64 px-2.5 py-1.5 text-xs rounded-md bg-overlay-subtle/60 text-content
                 placeholder:text-content-tertiary border focus:outline-none"
          :class="[
            shownAiError ? 'border-red-400/70' : 'border-edge-subtle focus:border-accent/60',
            aiBusy ? 'animate-pulse' : '',
          ]"
          :disabled="aiBusy"
          @input="shownAiError = null"
          @keydown.enter.prevent="submitAiPrompt"
        />
        <button
          type="button"
          class="px-2.5 py-1.5 text-xs rounded-md whitespace-nowrap transition-colors"
          :class="aiPrompt.trim() && !aiBusy
            ? 'bg-accent/15 text-accent hover:bg-accent/25'
            : 'text-content-tertiary/50 cursor-default'"
          :disabled="!aiPrompt.trim() || aiBusy"
          @click="submitAiPrompt"
        >
          {{ aiBusy ? 'Selecting…' : 'Select' }}
        </button>
      </div>
      <!-- Failures only; the happy path needs no second line. -->
      <p v-if="shownAiError" class="text-xs text-red-400">{{ shownAiError }}</p>
    </div>
  </Transition>

  <div
    class="flex items-center gap-1 px-2.5 py-1.5 w-max
           bg-surface border border-edge-subtle rounded-lg shadow-lg"
  >
    <!-- The pointer: grab and edit the things on the canvas (annotations).
         Users think "select" is one idea whether the thing is pixels or an
         object, so it lives here with the region tools rather than inside
         Annotate. Clicking it leaves whatever mode is open — it IS idle. -->
    <Tooltip text="Select objects">
      <button
        type="button"
        class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :class="buttonClass(!!pointerActive)"
        aria-label="Select objects"
        :aria-pressed="!!pointerActive"
        @click="emit('pointer')"
      >
        <ToolIcon name="mousePointer" />
      </button>
    </Tooltip>
    <span class="w-px h-5 bg-edge-subtle mx-1" />

    <Tooltip
      v-for="tool in SELECT_TOOLS"
      :key="tool.id"
      :text="tool.hint ?? `Select — ${tool.label}`"
    >
      <button
        type="button"
        class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :class="buttonClass(armed === tool.id)"
        :aria-label="`Select — ${tool.label}`"
        :aria-pressed="armed === tool.id"
        @click="emit('arm', tool.id)"
      >
        <ToolIcon :name="tool.icon" />
      </button>
    </Tooltip>

    <span class="w-px h-5 bg-edge-subtle mx-1" />

    <Tooltip v-for="option in SELECTION_MODES" :key="option.id" :text="option.label">
      <button
        type="button"
        class="p-1.5 rounded-md transition-colors"
        :class="buttonClass(combine === option.id, combineEnabled)"
        :aria-label="option.label"
        :aria-pressed="combine === option.id"
        :disabled="!combineEnabled"
        @click="emit('set', { combine: option.id })"
      >
        <ToolIcon :name="option.icon" />
      </button>
    </Tooltip>

    <span class="w-px h-5 bg-edge-subtle mx-1" />

    <label
      class="flex items-center gap-2 text-xs text-content-tertiary"
      :class="sliderClass(toolSettingsEnabled)"
    >
      <span class="w-14 text-right">{{ slot.label }}</span>
      <input
        type="range" class="w-24"
        :min="slot.min" :max="slot.max"
        :value="slotValue"
        :disabled="!toolSettingsEnabled"
        @input="onSliderInput(Number(($event.target as HTMLInputElement).value))"
      />
      <span class="tabular-nums w-10 text-content-secondary">{{ slotReadout }}{{ slot.unit }}</span>
    </label>

    <ToolbarPopover
      label=""
      aria-label="Wand settings"
      :width="284"
      :disabled="armed !== 'wand'"
    >
      <template #trigger>
        <ToolIcon name="sliders" />
      </template>
      <div class="space-y-3">
        <p class="text-xs font-semibold text-content-secondary">Wand refinement</p>

        <label class="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span class="text-content-tertiary">Spread</span>
          <input
            type="range"
            min="0"
            max="100"
            :value="spread"
            @input="emit('set', { spread: Number(($event.target as HTMLInputElement).value) })"
          />
          <span class="font-mono tabular-nums text-right text-content-secondary">{{ spread }}%</span>
        </label>

        <label class="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span class="text-content-tertiary">Grow</span>
          <input
            type="range"
            min="-40"
            max="40"
            :value="growPx"
            @input="emit('set', { growPx: Number(($event.target as HTMLInputElement).value) })"
          />
          <span class="font-mono tabular-nums text-right text-content-secondary">{{ growPx }}px</span>
        </label>

        <label class="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span class="text-content-tertiary">Feather</span>
          <input
            type="range"
            min="0"
            :max="FEATHER_SLIDER_MAX"
            :value="featherSliderFromPx(featherPx)"
            @input="emit('set', {
              featherPx: featherPxFromSlider(Number(($event.target as HTMLInputElement).value)),
            })"
          />
          <span class="font-mono tabular-nums text-right text-content-secondary">{{ featherPx }}px</span>
        </label>

        <label class="flex items-center justify-between gap-3 text-xs text-content-secondary">
          <span>
            Anti-alias
            <span class="block text-content-tertiary">Smooth hard mask edges</span>
          </span>
          <input
            type="checkbox"
            class="accent-accent"
            :checked="antialias"
            @change="emit('set', { antialias: ($event.target as HTMLInputElement).checked })"
          />
        </label>
      </div>
    </ToolbarPopover>

    <span class="w-px h-5 bg-edge-subtle mx-1" />

    <button
      type="button"
      class="px-2.5 py-1.5 text-xs rounded-md whitespace-nowrap"
      :class="buttonClass(false, hasSelection)"
      :disabled="!hasSelection"
      @click="emit('invert')"
    >
      Invert
    </button>
    <button
      type="button"
      class="px-2.5 py-1.5 text-xs rounded-md whitespace-nowrap"
      :class="buttonClass(false, hasSelection)"
      :disabled="!hasSelection"
      @click="emit('clear')"
    >
      Deselect
    </button>
  </div>
  </div>
</template>
