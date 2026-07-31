<script setup lang="ts">
/**
 * The selection island: a floating pill at the bottom of the canvas, the same
 * shape as the browser's selection bar, floating OVER the matte so nothing
 * about arming a tool ever pushes the canvas or the toolbars around.
 *
 * The island carries IDENTITY only — the pointer, the six tool slots, the
 * combine modes, invert/deselect — and never a parameter. Arming a tool
 * raises a panel above the island with that tool's FULL parameter set (the
 * same gesture the Object tool has always used for its prompt), so every
 * setting has exactly one home and the bar itself never reflows. Idle shows
 * no panel at all.
 *
 * Kin tools share a slot with a hover flyout (the two marquees, the two
 * lassos, the two gradients); the slot shows whichever member was used last,
 * so the common case stays one click.
 *
 * Selection is workspace state, not a mode: clicking a tool arms it (the
 * pointer goes to the selection overlay, the open family is suspended, not
 * left); clicking the armed tool — or reaching for any family control that
 * wants the canvas back — disarms it.
 */
import { computed, nextTick, ref, watch } from 'vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolIcon from './ToolIcon.vue'
import { SELECT_TOOLS, SELECT_TOOL_GROUPS, SELECTION_MODES } from '../stack/toolFamilies'
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

const toolById = Object.fromEntries(SELECT_TOOLS.map(tool => [tool.id, tool]))
const armedTool = computed(() => (props.armed ? toolById[props.armed] : null))

/** Each slot shows its last-used member; arming any member claims the slot. */
const groupCurrent = ref<Record<string, SelectToolId>>(
  Object.fromEntries(SELECT_TOOL_GROUPS.map(group => [group.id, group.members[0]]))
)
watch(() => props.armed, armed => {
  if (!armed) return
  const group = SELECT_TOOL_GROUPS.find(g => g.members.includes(armed))
  if (group) groupCurrent.value[group.id] = armed
}, { immediate: true })

/** Combine describes how the next gesture meets the visible selection, so its
 * state remains visible/editable after a one-shot workflow disarms the tool. */
const combineEnabled = computed(() => props.armed !== null || props.hasSelection)

/**
 * The armed tool's parameters, in bar order. Feather is selection-edge state
 * shared by every geometric tool; the rest belong to one tool each. A ramp's
 * ease and an ellipse's falloff are the same idea and deliberately not the
 * same number: 100% softness on a ramp has no edge left, while 100% feather
 * on an ellipse still ends somewhere.
 */
interface PanelSlider {
  label: string
  min: number
  max: number
  unit: string
  value: number
  readout: number
  set: (value: number) => void
}

const featherSlider = (): PanelSlider => ({
  label: 'Feather',
  min: 0, max: FEATHER_SLIDER_MAX, unit: 'px',
  value: featherSliderFromPx(props.featherPx),
  readout: props.featherPx,
  set: value => emit('set', { featherPx: featherPxFromSlider(value) }),
})

const plainSlider = (
  label: string, key: string, value: number, min: number, max: number, unit: string
): PanelSlider => ({
  label, min, max, unit, value, readout: value,
  set: v => emit('set', { [key]: v }),
})

const panelSliders = computed<PanelSlider[]>(() => {
  switch (props.armed) {
    case 'wand': return [
      plainSlider('Threshold', 'tolerance', props.tolerance, 1, 100, ''),
      plainSlider('Spread', 'spread', props.spread, 0, 100, '%'),
      plainSlider('Grow', 'growPx', props.growPx, -40, 40, 'px'),
      featherSlider(),
    ]
    case 'brush': return [
      plainSlider('Brush', 'selectBrushSize', props.brushSize, 8, 300, 'px'),
      featherSlider(),
    ]
    case 'linear': return [
      plainSlider('Softness', 'gradientSoftness', props.gradientSoftness, 0, 100, ''),
    ]
    case 'radial': return [
      plainSlider('Feather', 'gradientFeather', props.gradientFeather, 2, 100, ''),
    ]
    case 'rect': case 'ellipse': case 'lasso': case 'magnetic': return [featherSlider()]
    default: return []
  }
})

/**
 * The Object tool's panel content: both of the tool's gestures are stated
 * there — the field for select-by-name, the placeholder caption for
 * click-to-select. The typed prompt survives a run — re-running and refining
 * are the common follow-ups.
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

function buttonClass(active: boolean, enabled = true) {
  if (!enabled) return 'text-content-tertiary/50 cursor-default'
  return active
    ? 'bg-selection/15 text-content'
    : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'
}
</script>

<template>
  <!-- The host positions this root (absolute over the matte); that same
       positioning is what the raised panel's `absolute bottom-full` anchors
       to, so the wrapper must NOT add a position class of its own. -->
  <div class="w-max">
  <!-- The armed tool's panel, raised over the island. One home for every
       parameter: the Object tool brings its prompt, everything else brings
       its sliders. Disarming folds it away. -->
  <Transition
    enter-active-class="transition duration-150 ease-out"
    enter-from-class="opacity-0 translate-y-1"
    leave-active-class="transition duration-100 ease-in"
    leave-to-class="opacity-0 translate-y-1"
  >
    <div
      v-if="armed"
      class="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 w-max
             px-3 py-2
             bg-surface border border-edge-subtle rounded-lg shadow-lg"
    >
      <template v-if="armed === 'object'">
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
        <p v-if="shownAiError" class="mt-1.5 text-xs text-red-400">{{ shownAiError }}</p>
      </template>

      <div v-else class="flex items-center gap-3">
        <span class="flex items-center gap-1.5 text-xs font-medium text-content-secondary">
          <ToolIcon v-if="armedTool" :name="armedTool.icon" />
          {{ armedTool?.label }}
        </span>
        <span class="w-px h-5 bg-edge-subtle" />
        <label
          v-for="slider in panelSliders"
          :key="slider.label"
          class="flex items-center gap-2 text-xs text-content-tertiary"
        >
          <span>{{ slider.label }}</span>
          <input
            type="range" class="w-24"
            :min="slider.min" :max="slider.max"
            :value="slider.value"
            @input="slider.set(Number(($event.target as HTMLInputElement).value))"
          />
          <span class="tabular-nums w-10 text-content-secondary">{{ slider.readout }}{{ slider.unit }}</span>
        </label>
        <label
          v-if="armed === 'wand'"
          class="flex items-center gap-1.5 text-xs text-content-secondary cursor-pointer"
        >
          <input
            type="checkbox"
            class="accent-accent"
            :checked="antialias"
            @change="emit('set', { antialias: ($event.target as HTMLInputElement).checked })"
          />
          Anti-alias
        </label>
      </div>
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

    <span
      v-for="group in SELECT_TOOL_GROUPS"
      :key="group.id"
      class="relative group/fly"
    >
      <Tooltip
        v-if="group.members.length === 1"
        :text="toolById[group.members[0]].hint ?? `Select — ${toolById[group.members[0]].label}`"
      >
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="buttonClass(armed === group.members[0])"
          :aria-label="`Select — ${toolById[group.members[0]].label}`"
          :aria-pressed="armed === group.members[0]"
          @click="emit('arm', group.members[0])"
        >
          <ToolIcon :name="toolById[group.members[0]].icon" />
        </button>
      </Tooltip>
      <template v-else>
        <!-- The slot arms its last-used member; the corner tick marks a group.
             No tooltip here — the flyout itself names the members. -->
        <button
          type="button"
          class="relative p-1.5 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="buttonClass(armed === groupCurrent[group.id])"
          :aria-label="`Select — ${toolById[groupCurrent[group.id]].label}`"
          :aria-pressed="armed === groupCurrent[group.id]"
          @click="emit('arm', groupCurrent[group.id])"
        >
          <ToolIcon :name="toolById[groupCurrent[group.id]].icon" />
          <svg
            viewBox="0 0 6 6" aria-hidden="true"
            class="absolute right-[3px] bottom-[3px] w-1.5 h-1.5 text-content-tertiary pointer-events-none"
          ><path d="M6 0v6H0z" fill="currentColor" /></svg>
        </button>
        <!-- pb-1 keeps the hover unbroken across the gap to the flyout. -->
        <div
          class="absolute bottom-full left-1/2 -translate-x-1/2 pb-1 hidden group-hover/fly:block z-menu"
        >
          <div class="flex flex-col gap-0.5 p-1 bg-surface border border-edge-subtle rounded-lg shadow-lg">
            <button
              v-for="id in group.members"
              :key="id"
              type="button"
              class="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs whitespace-nowrap transition-colors"
              :class="buttonClass(armed === id)"
              :title="toolById[id].hint"
              @click="emit('arm', id)"
            >
              <ToolIcon :name="toolById[id].icon" />
              {{ toolById[id].label }}
            </button>
          </div>
        </div>
      </template>
    </span>

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
