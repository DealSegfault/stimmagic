<script setup lang="ts">
/**
 * The active family's sub-toolbar, directly beneath the tool row.
 *
 * Holds only the HOT controls. Everything with a large surface — the whole
 * Adjust control set, per-engine brush settings — lives in the selected row's
 * inspector, which is what lets a 40-knob tool exist without a second layout
 * system. Nobody gets forty controls in a toolbar; nobody loses them either.
 */
import { computed } from 'vue'
import { AdjustmentsHorizontalIcon, ClockIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import Button from '../../components/ui/Button.vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolbarPopover from './ToolbarPopover.vue'
import ToolIcon from './ToolIcon.vue'
import BrushPicker from '../ported/BrushPicker.vue'
import ColorPicker from '../ported/ColorPicker.vue'
import PaintPicker from './PaintPicker.vue'
import ReferenceImageStrip from './ReferenceImageStrip.vue'
import ToolAdvancedParams from './ToolAdvancedParams.vue'
import {
  CROP_ASPECTS,
} from '../stack/adjustSections'
import {
  PAINT_ENGINES, TEXT_STYLES,
  familyById,
} from '../stack/toolFamilies'
import { FILTER_CATEGORIES, LEVEL_EDITS, AUTO_EDITS } from '../stack/adjustSections'
import type { FamilyId } from '../stack/toolFamilies'
import type { Paint } from '../ported/shapeTypes'
import { paintCss, paintSolid } from '../stack/paints'

const props = defineProps<{
  family: FamilyId
  sub: string | null
  state: Record<string, any>
  /** The catalog tool that will run the active Generate sub-tool. */
  toolLabel?: string | null
  busy?: boolean
  canRun?: boolean
  hint?: string | null
}>()

const emit = defineEmits<{
  sub: [string]
  set: [Record<string, any>, continuous?: boolean]
  commit: ['crop' | 'annotation']
  run: []
  openToolPicker: [MouseEvent]
}>()

const family = computed(() => familyById(props.family))

/** Stroke weights the width popover offers, in canvas pixels. */
const STROKE_WEIGHTS = [2, 4, 8, 14, 22]

/**
 * The universal shape effects, as a small icon menu.
 *
 * Gradient is not one: it is a color, chosen in the stroke or fill well.
 */
const SHAPE_EFFECTS = [
  { id: 'none', label: 'None' },
  { id: 'neon', label: 'Neon' },
] as const

/** The current effect's label, shown on the toolbar chip so the state reads at a glance. */
const shapeEffectLabel = computed(
  () => SHAPE_EFFECTS.find(fx => fx.id === (props.state.annotateShapeEffect ?? 'none'))?.label ?? 'None',
)

/** Which annotate sub-tools show which style controls. */
const strokeSubs = ['arrow', 'draw', 'rectangle', 'ellipse', 'line']
const fillSubs = ['rectangle', 'ellipse']
// Sharpie strokes take their glow from the brush, not the shape style, so the
// effect menu would lie on Draw.
const effectSubs = ['arrow', 'rectangle', 'ellipse', 'line']
const retouchAdjustmentSubs = ['light', 'color', 'detail', 'mixer', 'point', 'grade']
const retouchModelSubs = ['remove', 'repaint']

/**
 * A SELECTED shape overrides the sub-tool: the controls shown are the ones the
 * shape actually has, and they read/write its values. With nothing selected
 * they are the latent tool's initial conditions.
 */
const shapeKind = computed<string | null>(() => props.state.selectedShapeKind ?? null)

const strokeKinds = ['arrow', 'curved-arrow', 'line', 'path', 'rectangle', 'ellipse']
const fillKinds = ['rectangle', 'ellipse']
const effectKinds = ['arrow', 'curved-arrow', 'line', 'rectangle', 'ellipse']

const showStroke = computed(() =>
  shapeKind.value ? strokeKinds.includes(shapeKind.value) : strokeSubs.includes(props.sub ?? '')
)
const showFill = computed(() =>
  shapeKind.value ? fillKinds.includes(shapeKind.value) : fillSubs.includes(props.sub ?? '')
)
const showEffect = computed(() =>
  shapeKind.value ? effectKinds.includes(shapeKind.value) : effectSubs.includes(props.sub ?? '')
)
const showText = computed(() =>
  shapeKind.value ? shapeKind.value === 'text' : props.sub === 'text'
)

/**
 * Whether this slot can hold a gradient.
 *
 * Pen strokes are stamped pixels rather than a path the canvas can hand a
 * gradient to, so Draw's color is a flat one — offering the tab there would
 * be a promise the renderer cannot keep.
 */
const allowGradient = computed(() =>
  shapeKind.value ? shapeKind.value !== 'path' : props.sub !== 'draw'
)

/** A well previews whatever paint it holds, gradient included. */
function wellCss(paint: Paint | null) {
  return paintCss(paint)
}

function chipClass(active: boolean, pending = false) {
  if (pending) return 'text-content-tertiary/60 cursor-not-allowed'
  return active
    ? 'bg-selection/15 text-content'
    : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'
}
</script>

<template>
  <div
    class="flex items-center gap-1.5 flex-wrap border-b border-edge-subtle bg-surface/80 backdrop-blur-sm"
    :class="family.id === 'filters' ? 'pt-2' : 'px-4 py-2'"
  >
    <!-- Sub-tools, for the families that have them. -->
    <template v-if="family.subTools.length">
      <template
        v-for="option in family.subTools"
        :key="option.id"
      >
        <Tooltip
          :text="option.pending ? 'Not built yet' : option.hint ?? option.label"
        >
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md transition-colors"
            :class="chipClass(sub === option.id, option.pending)"
            :disabled="option.pending"
            :aria-label="option.label"
            @click="emit('sub', option.id)"
          >
            <ToolIcon v-if="option.icon" :name="option.icon" />
            <span v-if="!option.icon || option.labeled">{{ option.label }}</span>
          </button>
        </Tooltip>
        <span
          v-if="family.id === 'retouch' && (option.id === 'patch' || option.id === 'repaint')"
          class="w-px h-5 bg-edge-subtle mx-1"
        />
      </template>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
    </template>

    <!-- Generate ------------------------------------------------------- -->
    <!--
      Generate gets two rows: the tool and the knobs on one, the prompt on its
      own below. It is the only family whose main input is a sentence, and a
      sentence squeezed between a brush slider and a Run button gets forty
      characters of room.
    -->
    <template v-if="family.id === 'generate'">
      <div class="w-full flex flex-col gap-2">
        <div class="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md border border-edge-subtle text-content-secondary hover:text-content hover:bg-overlay-subtle"
            @click="emit('openToolPicker', $event)"
          >
            {{ toolLabel || 'No tool' }}
            <svg viewBox="0 0 24 24" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <span class="w-px h-5 bg-edge-subtle mx-1" />

          <template v-if="sub === 'expand'">
            <button
              v-for="factor in [1.15, 1.25, 1.5]"
              :key="factor"
              type="button"
              class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
              :class="chipClass(state.expandFactor === factor)"
              @click="emit('set', { expandFactor: factor })"
            >
              +{{ Math.round((factor - 1) * 100) }}%
            </button>
          </template>

          <div class="flex-1" />

          <label class="flex items-center gap-1.5 text-xs text-content-tertiary">
            Variations
            <input
              type="number" min="1" max="8"
              class="w-12 px-2 py-1 bg-surface-raised rounded-md text-content"
              :value="state.candidateCount"
              @input="emit('set', { candidateCount: Number(($event.target as HTMLInputElement).value) })"
            />
          </label>
          <Button size="sm" :disabled="!canRun" :loading="busy" @click="emit('run')">
            {{ sub === 'expand' ? 'Expand' : 'Run' }}
          </Button>
        </div>

        <textarea
          rows="2"
          class="w-full px-3 py-2 text-sm bg-surface-raised rounded-md text-content resize-none
                 placeholder:text-content-tertiary focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :placeholder="sub === 'expand'
            ? 'Describe what surrounds it'
            : 'Describe the change'"
          :value="state.prompt"
          @input="emit('set', { prompt: ($event.target as HTMLTextAreaElement).value })"
          @keydown.enter.meta="emit('run')"
        />
        <ReferenceImageStrip
          v-if="sub === 'expand' && (state.referenceMax > 0 || state.referenceImages?.length)"
          :model-value="state.referenceImages || []"
          :min-items="state.referenceMin || 0"
          :max-items="state.referenceMax || 0"
          :disabled="busy"
          @update:model-value="emit('set', { referenceImages: $event })"
        />
      </div>
    </template>

    <!-- Crop ------------------------------------------------------------ -->
    <template v-else-if="family.id === 'crop'">
      <button
        v-for="preset in CROP_ASPECTS"
        :key="preset.id"
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
        :class="chipClass(state.cropAspect === preset.id)"
        @click="emit('set', { cropAspect: preset.id })"
      >
        {{ preset.label }}
      </button>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <!-- The lollipop on the crop is the primary straightening control; this
           mirrors it for fine values and shows the angle in degrees. -->
      <!-- Shown as the angle the PICTURE turns, which is what the user sees
           and the opposite sign of the crop window's own tilt. -->
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Straighten
        <input
          type="range" min="-0.7854" max="0.7854" step="0.002" class="w-28"
          :value="-(state.rotation ?? 0)"
          @input="emit(
            'set',
            { rotation: -Number(($event.target as HTMLInputElement).value) },
            true,
          )"
          @change="emit('commit', 'crop')"
        />
        <span class="tabular-nums w-10">{{ (-(state.rotation ?? 0) * 180 / Math.PI).toFixed(1) }}°</span>
      </label>
      <button
        v-if="state.rotation"
        type="button"
        class="px-2 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { rotation: 0 })"
      >
        Reset
      </button>
      <button type="button" class="px-2.5 py-1.5 text-xs rounded-md" :class="chipClass(false)" @click="emit('set', { rotateQuarter: true })">
        Rotate 90°
      </button>
      <button type="button" class="px-2.5 py-1.5 text-xs rounded-md" :class="chipClass(!!state.flipX)" @click="emit('set', { flipX: !state.flipX })">
        Flip H
      </button>
      <button type="button" class="px-2.5 py-1.5 text-xs rounded-md" :class="chipClass(!!state.flipY)" @click="emit('set', { flipY: !state.flipY })">
        Flip V
      </button>
    </template>

    <!-- Retouch --------------------------------------------------------- -->
    <template v-else-if="family.id === 'retouch'">
      <!-- Remove/Repaint are one explicit model run over the shared selection,
           not a stream of brush gestures. Everything about that one run — model,
           Advanced, prompt, Count, Run — lives in a single compose card, so the
           action sits directly under its input instead of a row away. Repaint
           leads with the prompt and docks the run controls into the card's
           footer; Remove has no prompt, so the card collapses to that one row.
           Every provider parameter still lives behind Advanced. -->
      <div
        v-if="retouchModelSubs.includes(sub ?? '')"
        class="w-full"
      >
        <!-- Both states share one card shell so they read as the same panel.
             Repaint's input is the prompt; Remove has none, so where the prompt
             would be it names the gesture instead — the two stay parallel and
             neither feels cramped. -->
        <div
          class="rounded-lg border border-edge-subtle bg-surface-raised overflow-hidden"
          :class="sub === 'repaint'
            ? 'focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/30'
            : ''"
        >
          <textarea
            v-if="sub === 'repaint'"
            rows="2"
            class="w-full px-3 py-2.5 text-sm bg-transparent text-content resize-none
                   placeholder:text-content-muted focus-visible:outline-none"
            placeholder="Describe what should replace the selected area"
            :value="state.prompt"
            @input="emit('set', { prompt: ($event.target as HTMLTextAreaElement).value })"
            @keydown.enter.meta="emit('run')"
          />
          <ReferenceImageStrip
            v-if="sub === 'repaint' && (state.referenceMax > 0 || state.referenceImages?.length)"
            :model-value="state.referenceImages || []"
            :min-items="state.referenceMin || 0"
            :max-items="state.referenceMax || 0"
            :disabled="busy"
            @update:model-value="emit('set', { referenceImages: $event })"
          />
          <p v-if="sub !== 'repaint'" class="px-3 py-2.5 text-sm text-content-muted">
            Select the area to remove, then Run.
          </p>

          <!-- The run controls, docked into the card's footer under the input. -->
          <div class="flex items-center gap-1.5 px-2 py-1.5 border-t border-edge-subtle">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md
                     border border-edge-subtle text-content-secondary
                     hover:text-content hover:bg-overlay-subtle"
              @click="emit('openToolPicker', $event)"
            >
              {{ toolLabel || 'No tool' }}
              <svg viewBox="0 0 24 24" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>

            <ToolbarPopover
              label=""
              :width="360"
              :disabled="!state.activeTool"
              aria-label="Advanced settings"
            >
              <template #trigger>
                <AdjustmentsHorizontalIcon class="w-4 h-4" />
              </template>
              <ToolAdvancedParams
                v-if="state.activeTool"
                :tool="state.activeTool"
                :values="state.toolParams || {}"
                @update="(name, value) => emit('set', { toolParamPatch: { [name]: value } })"
              />
            </ToolbarPopover>

            <ToolbarPopover
              v-if="sub === 'repaint'"
              label=""
              :width="320"
              :disabled="!state.recentRepaintPrompts?.length"
              close-on-select
              aria-label="Recent Repaint prompts"
            >
              <template #trigger>
                <ClockIcon class="w-3.5 h-3.5" />
              </template>
              <div class="space-y-1">
                <p class="px-2 pb-1 text-xs font-semibold text-content-secondary">
                  Recent prompts
                </p>
                <!-- The row is the container so the whole strip highlights and
                     reveals its remove control; the prompt and the × are
                     siblings, not nested buttons. Only the prompt closes the
                     popover, so removing several in a row keeps it open. -->
                <div
                  v-for="recent in state.recentRepaintPrompts"
                  :key="recent"
                  class="group/recent flex items-center gap-1 rounded-md pr-1
                         hover:bg-overlay-subtle"
                >
                  <button
                    type="button"
                    data-close-popover
                    class="min-w-0 flex-1 rounded-md px-2 py-2 text-left text-xs leading-5
                           text-content-secondary group-hover/recent:text-content
                           focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
                    @click="emit('set', { prompt: recent })"
                  >
                    {{ recent }}
                  </button>
                  <button
                    type="button"
                    class="grid h-6 w-6 shrink-0 place-items-center rounded-md
                           text-content-tertiary opacity-0 transition-opacity
                           group-hover/recent:opacity-100 hover:text-content
                           focus-visible:opacity-100 focus-visible:outline-none
                           focus-visible:ring-2 ring-accent/60"
                    aria-label="Remove from recent prompts"
                    @click="emit('set', { removeRecentPrompt: recent })"
                  >
                    <XMarkIcon class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </ToolbarPopover>

            <div class="flex-1" />
            <label
              class="flex items-center gap-1.5 text-xs text-content-tertiary"
              title="Grow the mask past the selection edge before the model runs — a mask that hugs the object leaves its outline behind. Negative shrinks."
            >
              Expand mask
              <span class="flex items-center gap-0.5">
                <input
                  type="number"
                  min="-50"
                  max="50"
                  class="w-12 px-2 py-1 rounded-md font-mono tabular-nums text-content bg-overlay-subtle"
                  :value="state.maskExpandPercent"
                  @input="emit('set', {
                    maskExpandPercent: Number(($event.target as HTMLInputElement).value),
                  })"
                />
                %
              </span>
            </label>
            <label class="flex items-center gap-1.5 text-xs text-content-tertiary">
              Variations
              <input
                type="number"
                min="1"
                max="8"
                class="w-12 px-2 py-1 rounded-md font-mono tabular-nums text-content bg-overlay-subtle"
                :value="state.candidateCount"
                @input="emit('set', {
                  candidateCount: Number(($event.target as HTMLInputElement).value),
                })"
              />
            </label>
            <Button size="sm" :disabled="!canRun" :loading="busy" @click="emit('run')">
              Run
            </Button>
          </div>
        </div>
      </div>

      <!-- The sub-tool chip above says what manual repair is being authored.
           The brush only defines its region; it is not itself a Paint stroke. -->
      <ToolbarPopover
        v-else-if="sub !== 'patch' && !retouchAdjustmentSubs.includes(sub ?? '')"
        :label="`${Math.round(state.retouchBrush.size)}px`"
      >
        <template #trigger>
          <span
            class="w-4 h-4 rounded-full bg-content"
            :style="{
              opacity: state.retouchBrush.opacity / 100,
              filter: `blur(${(100 - state.retouchBrush.hardness) / 40}px)`,
            }"
          />
        </template>
        <BrushPicker
          :model-value="state.retouchBrush"
          :stroke-color="state.paintColor"
          @update:model-value="emit('set', { retouchBrush: $event })"
        />
      </ToolbarPopover>
    </template>

    <!-- Paint ----------------------------------------------------------- -->
    <template v-else-if="family.id === 'paint'">
      <Tooltip
        v-for="engine in PAINT_ENGINES"
        :key="engine.id"
        :text="engine.pending
          ? 'Not built yet'
          : engine.id === 'clone'
            ? 'Clone — alt-click to set the source, then paint'
            : engine.id === 'patch'
            ? 'Patch — select the flawed area, then drag it over clean pixels'
            : engine.label"
      >
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md transition-colors"
          :class="chipClass(state.engineId === engine.id, engine.pending)"
          :disabled="engine.pending"
          @click="emit('set', { engineId: engine.id })"
        >
          <ToolIcon :name="engine.icon" />
        </button>
      </Tooltip>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <!-- A brush is not a property of the layer it painted, so it hangs off
           the toolbar rather than appearing in the Edits inspector. -->
      <ToolbarPopover :label="`${Math.round(state.paintBrush.size)}px`">
        <template #trigger>
          <span
            class="w-4 h-4 rounded-full bg-content"
            :style="{
              opacity: state.paintBrush.opacity / 100,
              filter: `blur(${(100 - state.paintBrush.hardness) / 40}px)`,
            }"
          />
        </template>
        <BrushPicker
          :model-value="state.paintBrush"
          :stroke-color="state.paintColor"
          @update:model-value="emit('set', { paintBrush: $event })"
        />
      </ToolbarPopover>
      <!-- What the engine does with the stroke, for the engines that take a
           direction or a strength. -->
      <template v-if="state.engineId === 'dodge' || state.engineId === 'burn'">
        <label class="flex items-center gap-2 text-xs text-content-tertiary">
          Exposure
          <input
            type="range" min="1" max="100" class="w-20"
            :value="state.paintExposure"
            @input="emit('set', { paintExposure: Number(($event.target as HTMLInputElement).value) })"
          />
          <span class="w-8 text-right font-mono tabular-nums text-content-secondary">
            {{ state.paintExposure }}%
          </span>
        </label>
        <button
          v-for="range in ['shadows', 'midtones', 'highlights']"
          :key="range"
          type="button"
          class="px-2 py-1.5 text-xs rounded-md capitalize"
          :class="chipClass(state.paintRange === range)"
          @click="emit('set', { paintRange: range })"
        >
          {{ range }}
        </button>
      </template>
      <template v-else-if="state.engineId === 'sponge'">
        <label class="flex items-center gap-2 text-xs text-content-tertiary">
          Strength
          <input
            type="range" min="1" max="100" class="w-20"
            :value="state.paintStrength"
            @input="emit('set', { paintStrength: Number(($event.target as HTMLInputElement).value) })"
          />
          <span class="w-8 text-right font-mono tabular-nums text-content-secondary">
            {{ state.paintStrength }}%
          </span>
        </label>
        <button
          type="button"
          class="px-2 py-1.5 text-xs rounded-md"
          :class="chipClass(state.paintSaturate)"
          @click="emit('set', { paintSaturate: true })"
        >
          Saturate
        </button>
        <button
          type="button"
          class="px-2 py-1.5 text-xs rounded-md"
          :class="chipClass(!state.paintSaturate)"
          @click="emit('set', { paintSaturate: false })"
        >
          Desaturate
        </button>
      </template>
      <label
        v-else-if="state.engineId === 'blur' || state.engineId === 'sharpen'"
        class="flex items-center gap-2 text-xs text-content-tertiary"
      >
        Strength
        <input
          type="range" min="1" max="100" class="w-20"
          :value="state.paintStrength"
          @input="emit('set', { paintStrength: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="w-8 text-right font-mono tabular-nums text-content-secondary">
          {{ state.paintStrength }}%
        </span>
      </label>
      <ToolbarPopover
        v-if="state.engineId === 'paint' || state.engineId === 'fill'"
        label="Color"
        :width="292"
      >
        <template #trigger>
          <span
            class="w-4 h-4 rounded-md border border-edge-subtle"
            :style="{ background: wellCss(state.paintColor) }"
          />
        </template>
        <ColorPicker
          :model-value="state.paintColor"
          :image-palette="state.imagePalette"
          embedded
          @update:model-value="emit('set', { paintColor: $event })"
        />
      </ToolbarPopover>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { newLayer: true })"
      >
        New layer
      </button>
    </template>

    <!-- Filters: picking one IS applying it, so the strip belongs where the
         decision is made rather than behind a selected step. -->
    <template v-else-if="family.id === 'filters'">
      <!-- One row that scrolls, rather than wrapping: the strip is a strip,
           and wrapping it would push the canvas down every time it grew. It
           runs edge to edge — the lead-in padding lives INSIDE the overflow
           region so the first tile doesn't touch the edge but the scroll
           track still spans the full bar. -->
      <div class="w-full min-w-0 flex items-start gap-1.5 overflow-x-auto custom-scrollbar px-3">
        <template v-for="category in FILTER_CATEGORIES" :key="category.id">
          <span v-if="category.label" class="w-px h-10 bg-edge-subtle mx-1 shrink-0" />
          <Tooltip
            v-for="preset in category.filters"
            :key="preset.id"
            :text="category.label ? `${category.label} · ${preset.label}` : preset.label"
          >
            <button
              type="button"
              class="w-20 shrink-0 rounded-md p-0.5 transition-colors"
              :class="state.appliedStripIds?.includes(preset.id)
                ? 'bg-selection/25 text-content'
                : 'text-content-tertiary hover:text-content hover:bg-overlay-subtle'"
              @click="emit('set', { applyFilter: preset.id })"
            >
              <img
                v-if="state.filterThumbs?.[preset.id]"
                :src="state.filterThumbs[preset.id]"
                class="w-full h-16 rounded-media object-cover"
                alt=""
              />
              <div v-else class="w-full h-16 rounded-media bg-matte" />
              <span class="block text-[10px] leading-tight truncate">{{ preset.label }}</span>
            </button>
          </Tooltip>
        </template>
      </div>
    </template>

    <!-- Adjust: six addable edits. Each click makes its own focused step —
         a Light, a Color, a Detail, or an Auto (a Light edit seeded from the
         histogram) — whose controls live in its Properties. Same rule as the
         strip: the bar offers what you can ADD. -->
    <template v-else-if="family.id === 'levels'">
      <Tooltip
        v-for="edit in LEVEL_EDITS"
        :key="edit.id"
        :text="edit.label"
      >
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md
                 text-content-secondary hover:text-content hover:bg-overlay-subtle"
          :aria-label="edit.label"
          @click="emit('set', { addLevel: edit.id })"
        >
          <ToolIcon :name="edit.icon" />
          {{ edit.label }}
        </button>
      </Tooltip>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        v-for="auto in AUTO_EDITS"
        :key="auto.id"
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { auto: auto.id })"
      >
        {{ auto.label }}
      </button>
    </template>

    <!-- Annotate: the latent shape's full initial conditions, compact — every
         control is an icon opening a popover. With a shape selected the same
         controls edit it, so the strip doubles as a remote for the selection. -->
    <template v-else-if="family.id === 'annotate'">
      <template v-if="showStroke">
        <!-- Stroke weight -->
        <ToolbarPopover label="" :width="148">
          <template #trigger>
            <svg viewBox="0 0 16 16" class="w-4 h-4" fill="currentColor" aria-label="Stroke width">
              <rect x="2" y="3" width="12" height="1" rx="0.5" />
              <rect x="2" y="6.5" width="12" height="2" rx="1" />
              <rect x="2" y="10.5" width="12" height="3.5" rx="1.5" />
            </svg>
          </template>
          <button
            v-for="weight in STROKE_WEIGHTS"
            :key="weight"
            type="button"
            class="w-full flex items-center gap-3 px-2 py-1.5 rounded-md transition-colors"
            :class="state.annotateStrokeWidth === weight
              ? 'bg-selection/15 text-content'
              : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
            @click="emit('set', { annotateStrokeWidth: weight })"
          >
            <span
              class="flex-1 rounded-full bg-current"
              :style="{ height: Math.min(weight, 12) + 'px' }"
            />
            <span class="text-[11px] tabular-nums w-8 text-right">{{ weight }}px</span>
          </button>
        </ToolbarPopover>

        <!-- Stroke color: a ring, because the stroke is an outline. -->
        <ToolbarPopover label="" :width="292">
          <template #trigger>
            <span
              class="w-4 h-4 rounded-full ring-inset"
              aria-label="Stroke color"
              :style="{
                background: wellCss(allowGradient ? state.annotatePaint : paintSolid(state.annotatePaint)),
                mask: 'radial-gradient(circle, transparent 0 34%, #000 34%)',
                WebkitMask: 'radial-gradient(circle, transparent 0 34%, #000 34%)',
              }"
            />
          </template>
          <PaintPicker
            :model-value="allowGradient ? state.annotatePaint : paintSolid(state.annotatePaint)"
            :image-palette="state.imagePalette"
            :allow-gradient="allowGradient"
            @update:model-value="emit('set', { annotatePaint: $event })"
          />
        </ToolbarPopover>

        <!-- Fill: a solid square, because the fill is the inside. -->
        <ToolbarPopover v-if="showFill" label="" :width="292">
          <template #trigger>
            <span
              class="w-4 h-4 rounded-[4px] border border-edge-subtle"
              aria-label="Fill color"
              :style="state.annotateFillColor
                ? { background: wellCss(state.annotateFillColor) }
                : { background: 'repeating-linear-gradient(45deg, transparent 0 3px, rgba(255,255,255,.25) 3px 5px)' }"
            />
          </template>
          <button
            type="button"
            class="w-full mb-2 px-2 py-1.5 text-xs rounded-md text-left transition-colors"
            :class="!state.annotateFillColor
              ? 'bg-selection/15 text-content'
              : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
            @click="emit('set', { annotateFillColor: null })"
          >
            No fill
          </button>
          <PaintPicker
            :model-value="state.annotateFillColor ?? { r: 0, g: 0, b: 0, a: 0.5 }"
            :image-palette="state.imagePalette"
            :allow-gradient="allowGradient"
            @update:model-value="emit('set', { annotateFillColor: $event })"
          />
        </ToolbarPopover>

        <!-- Effect: none, or the neon glow. -->
        <ToolbarPopover v-if="showEffect" :label="shapeEffectLabel" :width="148">
          <template #trigger>
            <span class="sr-only">Effect</span>
          </template>
          <button
            v-for="fx in SHAPE_EFFECTS"
            :key="fx.id"
            type="button"
            class="w-full flex items-center gap-3 px-2 py-1.5 rounded-md transition-colors"
            :class="(state.annotateShapeEffect ?? 'none') === fx.id
              ? 'bg-selection/15 text-content'
              : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
            @click="emit('set', { annotateShapeEffect: fx.id })"
          >
            <svg viewBox="0 0 24 16" class="w-6 h-4 shrink-0" fill="none">
              <path
                v-if="fx.id === 'neon'"
                d="M2 8 h20" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"
                style="filter: drop-shadow(0 0 3px currentColor)"
              />
              <path v-else d="M2 8 h20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
            <span class="text-xs">{{ fx.label }}</span>
          </button>
        </ToolbarPopover>
      </template>

      <template v-if="showText">
        <!-- Text color shares the stroke well; the presets carry the rest. -->
        <ToolbarPopover label="" :width="292">
          <template #trigger>
            <span
              class="w-4 h-4 rounded-full"
              aria-label="Text color"
              :style="{
                background: wellCss(state.annotatePaint),
                mask: 'radial-gradient(circle, transparent 0 34%, #000 34%)',
                WebkitMask: 'radial-gradient(circle, transparent 0 34%, #000 34%)',
              }"
            />
          </template>
          <PaintPicker
            :model-value="state.annotatePaint"
            :image-palette="state.imagePalette"
            :allow-gradient="allowGradient"
            @update:model-value="emit('set', { annotatePaint: $event })"
          />
        </ToolbarPopover>
        <button
          v-for="style in TEXT_STYLES"
          :key="style.id"
          type="button"
          class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
          :class="chipClass(state.textStyle === style.id)"
          @click="emit('set', { textStyle: style.id })"
        >
          {{ style.label }}
        </button>
      </template>

      <!-- Opacity, inline: one slider does not deserve a popover. -->
      <label
        v-if="sub !== 'redact'"
        class="flex items-center gap-2 text-xs text-content-tertiary"
        title="Opacity"
      >
        <svg viewBox="0 0 16 16" class="w-4 h-4" fill="none" stroke="currentColor">
          <circle cx="8" cy="8" r="6" />
          <path d="M8 2 a6 6 0 0 1 0 12 Z" fill="currentColor" stroke="none" opacity="0.5" />
        </svg>
        <input
          type="range" min="10" max="100" class="w-20"
          :value="Math.round((state.annotateOpacity ?? 1) * 100)"
            @input="emit(
              'set',
              { annotateOpacity: Number(($event.target as HTMLInputElement).value) / 100 },
              true,
            )"
            @change="emit('commit', 'annotation')"
        />
      </label>
    </template>

    <!-- Only rendered with a hint: an empty spacer wraps to a phantom second
         flex line, and the row-gap above it reads as padding under the bar. -->
    <template v-if="hint">
      <div class="flex-1" />
      <span class="text-[11px] text-content-tertiary">{{ hint }}</span>
    </template>
  </div>
</template>
