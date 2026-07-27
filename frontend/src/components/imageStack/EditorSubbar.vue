<script setup lang="ts">
/**
 * The active family's sub-toolbar, directly beneath the tool row.
 *
 * Holds only the HOT controls. Everything with a large surface — the whole
 * Develop control set, per-engine brush settings — lives in the selected row's
 * inspector, which is what lets a 40-knob tool exist without a second layout
 * system. Nobody gets forty controls in a toolbar; nobody loses them either.
 */
import { computed } from 'vue'
import Button from '../ui/Button.vue'
import Tooltip from '../ui/Tooltip.vue'
import {
  CROP_ASPECTS,
} from '../../composables/imageStack/developSections'
import {
  PAINT_ENGINES, PAINT_SWATCHES, SELECTION_MODES, SHAPE_KINDS, TEXT_STYLES,
  familyById,
} from '../../composables/imageStack/toolFamilies'
import type { FamilyId, SelectionMode } from '../../composables/imageStack/toolFamilies'

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
          class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
          :class="chipClass(sub === option.id, option.pending)"
          :disabled="option.pending"
          @click="emit('sub', option.id)"
        >
          {{ option.label }}
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
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Straighten
        <input
          type="range" min="-0.4" max="0.4" step="0.005" class="w-28"
          :value="state.rotation ?? 0"
          @input="emit('set', { rotation: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
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
      <button
        v-for="option in SELECTION_MODES"
        :key="option.id"
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
        :class="chipClass(state.combine === option.id)"
        @click="emit('set', { combine: option.id as SelectionMode })"
      >
        {{ option.label }}
      </button>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <label v-if="sub === 'brush'" class="flex items-center gap-2 text-xs text-content-tertiary">
        Size
        <input
          type="range" min="8" max="300" class="w-24"
          :value="state.brushSize"
          @input="emit('set', { brushSize: Number(($event.target as HTMLInputElement).value) })"
        />
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
          <!-- Stroke preview: the brush's own falloff, so the chip shows what
               it lays down rather than naming it. -->
          <span
            class="w-4 h-2 rounded-full"
            :style="{
              background: engine.readsPixels
                ? 'linear-gradient(90deg, rgb(var(--color-text-tertiary-rgb)/.7), transparent)'
                : `radial-gradient(circle, currentColor ${Math.round(engine.hardness * 100)}%, transparent 100%)`,
              opacity: engine.flow,
            }"
          />
          {{ engine.label }}
        </button>
      </Tooltip>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Size
        <input
          type="range" min="2" max="200" class="w-24"
          :value="state.brushSize"
          @input="emit('set', { brushSize: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Opacity
        <input
          type="range" min="0" max="1" step="0.05" class="w-20"
          :value="state.paintOpacity"
          @input="emit('set', { paintOpacity: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        v-for="swatch in PAINT_SWATCHES"
        :key="swatch"
        type="button"
        class="w-5 h-5 rounded-md border transition-transform"
        :class="state.paintColor === swatch ? 'border-selection scale-110' : 'border-edge-subtle'"
        :style="{ background: swatch }"
        @click="emit('set', { paintColor: swatch })"
      />
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        type="button"
        class="px-2.5 py-1.5 text-xs rounded-md text-content-secondary hover:text-content hover:bg-overlay-subtle"
        @click="emit('set', { newLayer: true })"
      >
        New layer
      </button>
    </template>

    <!-- Develop --------------------------------------------------------- -->
    <template v-else-if="family.id === 'develop'">
      <span class="text-xs text-content-tertiary">
        All controls are in the inspector below the stack — every one is free.
      </span>
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
        <button
          v-for="kind in SHAPE_KINDS"
          :key="kind.id"
          type="button"
          class="px-2.5 py-1.5 text-xs rounded-md transition-colors"
          :class="chipClass(state.shapeKind === kind.id)"
          @click="emit('set', { shapeKind: kind.id })"
        >
          {{ kind.label }}
        </button>
      </template>
      <span class="w-px h-5 bg-edge-subtle mx-1" />
      <button
        v-for="swatch in PAINT_SWATCHES"
        :key="swatch"
        type="button"
        class="w-5 h-5 rounded-md border transition-transform"
        :class="state.annotateColor === swatch ? 'border-selection scale-110' : 'border-edge-subtle'"
        :style="{ background: swatch }"
        @click="emit('set', { annotateColor: swatch })"
      />
    </template>

    <div class="flex-1" />
    <span v-if="hint" class="text-[11px] text-content-tertiary">{{ hint }}</span>
  </div>
</template>
