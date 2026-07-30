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
import { computed } from 'vue'
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
  /**
   * The pointer — object select — is the workspace's IDLE state, not an armed
   * tool: this is true when no family is open and no region tool is armed.
   */
  pointerActive?: boolean
}>()

const emit = defineEmits<{
  arm: [SelectToolId]
  pointer: []
  set: [Record<string, any>]
  invert: []
  clear: []
}>()

const combineEnabled = computed(() => props.armed !== null)

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
} as const

const slot = computed(() => {
  if (props.armed === 'wand') return SLIDER_SLOTS.tolerance
  if (props.armed === 'brush') return SLIDER_SLOTS.brush
  return SLIDER_SLOTS.feather
})

const slotValue = computed(() => {
  if (props.armed === 'wand') return props.tolerance
  if (props.armed === 'brush') return props.brushSize
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

    <Tooltip v-for="tool in SELECT_TOOLS" :key="tool.id" :text="`Select — ${tool.label}`">
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
        :class="buttonClass(combineEnabled && combine === option.id, combineEnabled)"
        :aria-label="option.label"
        :disabled="!combineEnabled"
        @click="emit('set', { combine: option.id })"
      >
        <ToolIcon :name="option.icon" />
      </button>
    </Tooltip>

    <span class="w-px h-5 bg-edge-subtle mx-1" />

    <label
      class="flex items-center gap-2 text-xs text-content-tertiary"
      :class="sliderClass(combineEnabled)"
    >
      <span class="w-14 text-right">{{ slot.label }}</span>
      <input
        type="range" class="w-24"
        :min="slot.min" :max="slot.max"
        :value="slotValue"
        :disabled="!combineEnabled"
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
</template>
