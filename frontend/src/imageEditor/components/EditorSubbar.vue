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
import Button from '../../components/ui/Button.vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import ToolbarPopover from './ToolbarPopover.vue'
import ToolIcon from './ToolIcon.vue'
import BrushPicker from '../ported/BrushPicker.vue'
import ColorPicker from '../ported/ColorPicker.vue'
import {
  CROP_ASPECTS,
} from '../stack/adjustSections'
import {
  PAINT_ENGINES, SELECTION_MODES, SHAPE_KINDS, TEXT_STYLES,
  familyById,
} from '../stack/toolFamilies'
import type { FamilyId, SelectionMode } from '../stack/toolFamilies'

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
  set: [Record<string, any>]
  run: []
  openToolPicker: []
}>()

const family = computed(() => familyById(props.family))

/** The three buttons the old Levels panel led with. */
const AUTO_ACTIONS = [
  { id: 'levels', label: 'Auto levels' },
  { id: 'contrast', label: 'Auto contrast' },
  { id: 'balance', label: 'Auto balance' },
]

function rgbaCss(color: { r: number; g: number; b: number; a?: number } | null) {
  if (!color) return 'transparent'
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${color.a ?? 1})`
}

function chipClass(active: boolean, pending = false) {
  if (pending) return 'text-content-tertiary/60 cursor-not-allowed'
  return active
    ? 'bg-selection/15 text-content'
    : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'
}
</script>

<template>
  <div class="flex items-center gap-1.5 flex-wrap px-4 py-2 border-b border-edge-subtle bg-surface/40">
    <!-- Sub-tools, for the families that have them. -->
    <template v-if="family.subTools.length">
      <Tooltip
        v-for="option in family.subTools"
        :key="option.id"
        :text="option.pending ? 'Not built yet' : option.label"
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
          <span v-else>{{ option.label }}</span>
        </button>
      </Tooltip>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
    </template>

    <!-- Generate ------------------------------------------------------- -->
    <template v-if="family.id === 'generate'">
      <button
        type="button"
        class="px-2 py-1.5 text-xs rounded-md border border-edge-subtle text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('openToolPicker')"
      >
        {{ toolLabel || 'No tool' }} <span class="text-content-tertiary">▾</span>
      </button>
      <span class="w-px h-5 bg-edge-subtle mx-1" />

      <template v-if="sub === 'inpaint'">
        <label class="flex items-center gap-2 text-xs text-content-tertiary">
          Brush
          <input
            type="range" min="8" max="300" class="w-24"
            :value="state.brushSize"
            @input="emit('set', { brushSize: Number(($event.target as HTMLInputElement).value) })"
          />
        </label>
        <input
          type="text"
          class="flex-1 min-w-40 px-3 py-1.5 text-sm bg-surface-raised rounded-md text-content placeholder:text-content-tertiary focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          placeholder="What should replace it? (blank = remove)"
          :value="state.prompt"
          @input="emit('set', { prompt: ($event.target as HTMLInputElement).value })"
          @keydown.enter="emit('run')"
        />
      </template>

      <template v-else-if="sub === 'whole'">
        <input
          type="text"
          class="flex-1 min-w-40 px-3 py-1.5 text-sm bg-surface-raised rounded-md text-content placeholder:text-content-tertiary focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          placeholder="Describe the change — applies to the whole image"
          :value="state.prompt"
          @input="emit('set', { prompt: ($event.target as HTMLInputElement).value })"
          @keydown.enter="emit('run')"
        />
      </template>

      <template v-else-if="sub === 'expand'">
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
        <input
          type="text"
          class="flex-1 min-w-40 px-3 py-1.5 text-sm bg-surface-raised rounded-md text-content placeholder:text-content-tertiary"
          placeholder="Describe what surrounds it"
          :value="state.prompt"
          @input="emit('set', { prompt: ($event.target as HTMLInputElement).value })"
        />
      </template>

      <template v-else-if="sub === 'upscale'">
        <button
          v-for="factor in [2, 4]"
          :key="factor"
          type="button"
          class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
          :class="chipClass(state.upscaleFactor === factor)"
          @click="emit('set', { upscaleFactor: factor })"
        >
          {{ factor }}×
        </button>
      </template>

      <label class="flex items-center gap-1.5 text-xs text-content-tertiary">
        Count
        <input
          type="number" min="1" max="8"
          class="w-12 px-2 py-1 bg-surface-raised rounded-md text-content"
          :value="state.candidateCount"
          @input="emit('set', { candidateCount: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
      <Button size="sm" :disabled="!canRun" :loading="busy" @click="emit('run')">
        {{ sub === 'expand' ? 'Expand' : sub === 'upscale' ? 'Upscale' : 'Run' }}
      </Button>
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
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Straighten
        <input
          type="range" min="-0.7854" max="0.7854" step="0.002" class="w-28"
          :value="state.rotation ?? 0"
          @input="emit('set', { rotation: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="tabular-nums w-10">{{ ((state.rotation ?? 0) * 180 / Math.PI).toFixed(1) }}°</span>
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

    <!-- Select ---------------------------------------------------------- -->
    <template v-else-if="family.id === 'select'">
      <Tooltip v-for="option in SELECTION_MODES" :key="option.id" :text="option.label">
        <button
          type="button"
          class="p-1.5 rounded-md transition-colors"
          :class="chipClass(state.combine === option.id)"
          :aria-label="option.label"
          @click="emit('set', { combine: option.id as SelectionMode })"
        >
          <ToolIcon :name="option.icon" />
        </button>
      </Tooltip>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <label v-if="sub === 'wand'" class="flex items-center gap-2 text-xs text-content-tertiary">
        Tolerance
        <input
          type="range" min="1" max="128" class="w-24"
          :value="state.tolerance"
          @input="emit('set', { tolerance: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="tabular-nums w-6">{{ state.tolerance }}</span>
      </label>
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Feather
        <input
          type="range" min="0" max="48" class="w-24"
          :value="state.featherPx"
          @input="emit('set', { featherPx: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="tabular-nums w-8">{{ state.featherPx }}px</span>
      </label>
      <span v-if="state.hasSelection" class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        v-if="state.hasSelection"
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { clearSelection: true })"
      >
        Clear selection
      </button>
    </template>

    <!-- Paint ----------------------------------------------------------- -->
    <template v-else-if="family.id === 'paint'">
      <Tooltip
        v-for="engine in PAINT_ENGINES"
        :key="engine.id"
        :text="engine.pending
          ? 'Not built yet'
          : engine.id === 'clone'
            ? 'Alt-click to set the source, then paint'
            : engine.readsPixels
            ? 'Reads the pixels below — its layer carries an advisory'
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
          :value="state.paintFlow"
          @input="emit('set', { paintFlow: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
      <ToolbarPopover label="Color">
        <template #trigger>
          <span
            class="w-4 h-4 rounded-md border border-edge-subtle"
            :style="{ background: rgbaCss(state.paintColor) }"
          />
        </template>
        <ColorPicker
          :model-value="state.paintColor"
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

    <!-- Levels ---------------------------------------------------------- -->
    <template v-else-if="family.id === 'levels'">
      <button
        v-for="auto in AUTO_ACTIONS"
        :key="auto.id"
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { auto: auto.id })"
      >
        {{ auto.label }}
      </button>
    </template>

    <!-- Annotate -------------------------------------------------------- -->
    <template v-else-if="family.id === 'annotate'">
      <template v-if="sub === 'text'">
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
      <template v-else-if="sub === 'shape'">
        <Tooltip v-for="kind in SHAPE_KINDS" :key="kind.id" :text="kind.label">
          <button
            type="button"
            class="p-1.5 rounded-md transition-colors"
            :class="chipClass(state.shapeKind === kind.id)"
            :aria-label="kind.label"
            @click="emit('set', { shapeKind: kind.id })"
          >
            <ToolIcon :name="(kind.icon as any)" />
          </button>
        </Tooltip>
      </template>
      <span v-if="sub !== 'redact'" class="w-px h-5 bg-edge-subtle mx-1" />
      <ToolbarPopover v-if="sub !== 'redact'" label="Color">
        <template #trigger>
          <span
            class="w-4 h-4 rounded-md border border-edge-subtle"
            :style="{ background: state.annotateColor }"
          />
        </template>
        <ColorPicker
          :model-value="state.annotateColorRgb"
          @update:model-value="emit('set', { annotateColorRgb: $event })"
        />
      </ToolbarPopover>
    </template>

    <div class="flex-1" />
    <span v-if="hint" class="text-[11px] text-content-tertiary">{{ hint }}</span>
  </div>
</template>
