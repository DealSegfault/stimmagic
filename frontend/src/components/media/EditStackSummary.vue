<template>
  <div v-if="summary.total">
    <!-- One line per step, in the Edits list's order. The full stack — every
         candidate, mask and slider — stays in the editor, one click away. -->
    <div class="divide-y divide-edge-subtle">
      <div v-for="step in visibleSteps" :key="step.key" class="py-1.5">
        <div class="flex items-baseline justify-between gap-3">
          <span class="min-w-0 flex-1 text-xs text-content truncate" :title="step.name">
            {{ step.name }}
          </span>
          <span
            v-if="step.detail"
            class="min-w-0 max-w-[60%] text-xs text-content-tertiary text-right truncate"
            :title="step.detail"
          >
            {{ step.detail }}
          </span>
        </div>
        <p
          v-if="step.note"
          class="m-0 mt-0.5 text-xs leading-relaxed text-content-tertiary line-clamp-2"
          :title="step.note"
        >
          {{ step.note }}
        </p>
      </div>
      <!-- Last child inside the rules, so nothing trails the list. -->
      <button
        v-if="hiddenCount"
        type="button"
        class="w-full py-1.5 text-left text-xs text-content-tertiary hover:text-content-secondary transition-colors"
        @click="expanded = true"
      >
        Show {{ hiddenCount }} more
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * What an editor save did, in one line per step.
 *
 * An image that came out of the editor has no model and no prompt to show, so
 * without this its lineage entry says only that the Image Editor touched it.
 * The saved stack summary is the account of the work: which repairs, which
 * adjustments, and whether a model was asked to make new pixels.
 */
import { computed, onMounted, ref } from 'vue'
import { useProvidersApi } from '../../composables/useProvidersApi'
import { toolDisplayName } from '../../utils/toolDisplay'
import { summarizeStack } from '../../imageEditor/stack/stackSummary'

/** Steps beyond this fold behind a disclosure; deep stacks are common. */
const COLLAPSE_AFTER = 6

const props = defineProps<{
  /** `generation_metadata.parameters.stack`, as recorded at save. */
  stack: unknown
}>()

const { cachedTools, fetchProvidersAndTools } = useProvidersApi()
const expanded = ref(false)

const summary = computed(() =>
  summarizeStack(props.stack, id => toolDisplayName(id, cachedTools.value)),
)

const visibleSteps = computed(() =>
  expanded.value ? summary.value.steps : summary.value.steps.slice(0, COLLAPSE_AFTER),
)
const hiddenCount = computed(() => summary.value.steps.length - visibleSteps.value.length)

// Tool names come from the cache; it is shared and idempotent, and a failure
// just leaves the humanized id in place.
onMounted(() => { fetchProvidersAndTools().catch(() => {}) })
</script>
