<script setup lang="ts">
/**
 * The control surface for a step that came from the Looks strip.
 *
 * A look is a bundle of ordinary adjustment params, so its properties are the
 * ordinary group controls — the ones it actually moved, under their own
 * headers. That is the whole argument for authoring looks in the real schema:
 * "less Kodachrome" is reachable by moving the dials Kodachrome set, instead of
 * a single opaque Amount that could only fade the entire thing at once.
 *
 * The first group opens; the rest stay collapsed. A look touches three or four
 * groups and Mixer alone is twenty-four sliders — all of it open at once reads
 * as a wall rather than as a place to start.
 */
import { computed, ref } from 'vue'
import { touchedGroups } from '../stack/adjustSections'
import type { ToneCurveHistogram } from '../stack/toneCurve'
import PhotoAdjustmentControls from './PhotoAdjustmentControls.vue'

const props = defineProps<{
  values: Record<string, any>
  /** The look's name, for the heading. */
  label?: string | null
  histogram?: ToneCurveHistogram
  disabled?: boolean
  /** Point color only: the canvas eyedropper is currently armed. */
  picking?: boolean
  clipShadows?: boolean
  clipHighlights?: boolean
  coalescePrefix: string
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
  pick: []
  clip: [{ shadows: boolean; highlights: boolean }]
}>()

const groups = computed(() => touchedGroups(props.values))

/**
 * Which group is open, falling back to the first one this look touches. The
 * fallback also catches a stale id: selecting a different look leaves the
 * previous group name behind, and without this the panel would open nothing at
 * all because no section matches it. Empty string means the person closed the
 * open one deliberately, which is not the same as "unset".
 */
const openedId = ref<string | null>(null)
const openId = computed(() => {
  const opened = openedId.value
  if (opened !== null && (opened === '' || groups.value.some(g => g.id === opened))) {
    return opened
  }
  return groups.value[0]?.id ?? null
})

function toggle(id: string) {
  openedId.value = openId.value === id ? '' : id
}
</script>

<template>
  <div class="divide-y divide-edge-subtle">
    <section v-for="group in groups" :key="group.id">
      <button
        type="button"
        class="w-full flex items-center gap-2 px-3 py-2 text-left rounded-md
               focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        @click="toggle(group.id)"
      >
        <span class="text-xs font-medium text-content-secondary flex-1">
          {{ group.label }}
        </span>
      </button>
      <div v-if="openId === group.id" class="px-3 pb-3">
        <PhotoAdjustmentControls
          :controls="group.controls"
          :values="values"
          :histogram="histogram"
          :disabled="disabled"
          :presentation="group.presentation"
          :picking="picking"
          :clip-shadows="clipShadows"
          :clip-highlights="clipHighlights"
          :coalesce-prefix="coalescePrefix"
          @change="(patch, key) => emit('change', patch, key)"
          @commit="emit('commit')"
          @pick="emit('pick')"
          @clip="emit('clip', $event)"
        />
      </div>
    </section>

    <p v-if="!groups.length" class="px-3 py-2 text-xs text-content-tertiary">
      {{ label ?? 'This look' }} sets nothing yet.
    </p>
  </div>
</template>
