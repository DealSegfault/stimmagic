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
import { familyById } from '../../composables/imageStack/toolFamilies'
import type { FamilyId } from '../../composables/imageStack/toolFamilies'

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

    <!-- Every other family's controls are the plugin panel's, not a second
         copy of them here. -->
    <template v-else-if="family.id === 'develop'">
      <span class="text-xs text-content-tertiary">Sections switch the panel on the right.</span>
    </template>

    <div class="flex-1" />
    <span v-if="hint" class="text-[11px] text-content-tertiary">{{ hint }}</span>
  </div>
</template>
