<script setup lang="ts">
/**
 * A whole-image op renders as a full-width band, not a sibling row.
 *
 * A checkpoint's content was sampled from everything below it, so its position
 * is not a preference — it is what the result was computed from. The band says
 * that: heavy rules, nothing that feels draggable, and by default it FOLDS the
 * steps below it behind "Built from N steps". After a whole-image edit the
 * visible list resets to short, which is the point — the common resting state
 * is a few rows, not a transcript.
 *
 * A stale band always shows its steps. That is a stable, actionable state
 * rather than a transient one, so expanding it is information, not noise.
 */
import { computed } from 'vue'
import { ChevronRightIcon, ArrowPathIcon, EyeIcon, EyeSlashIcon } from '@heroicons/vue/24/outline'
import IconButton from '../../components/ui/IconButton.vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import type { Op } from '../stack/types'
import type { Staleness } from '../stack/stackState'

const props = defineProps<{
  op: Op
  selected: boolean
  staleness: Staleness
  /** How many steps this band folds. */
  foldedCount: number
  expanded: boolean
  statusLine: string | null
  regenerating?: boolean
}>()

const emit = defineEmits<{
  select: []
  toggleExpanded: []
  toggleEnabled: [boolean]
  regenerate: []
}>()

const stale = computed(() => props.staleness === 'hard')

const prompt = computed(() => {
  const value = (props.op as any).params?.prompt
  return typeof value === 'string' ? value : ''
})

// A stale band shows its steps regardless: the state is stable and actionable.
const showsSteps = computed(() => props.expanded || stale.value)
</script>

<template>
  <div
    class="my-1.5 rounded-md border-y-2 px-3 py-2.5 cursor-default transition-colors"
    :class="[
      stale
        ? 'border-amber-500/50 bg-amber-500/10'
        : 'border-edge-strong bg-surface-raised',
      selected && !stale && 'bg-selection/15',
    ]"
    @click="emit('select')"
  >
    <div class="flex items-start gap-2">
      <Tooltip :text="op.enabled ? 'Hide this checkpoint' : 'Show this checkpoint'">
        <IconButton @click.stop="emit('toggleEnabled', !op.enabled)">
          <EyeIcon v-if="op.enabled" class="w-4 h-4" />
          <EyeSlashIcon v-else class="w-4 h-4 text-content-tertiary" />
        </IconButton>
      </Tooltip>

      <div class="min-w-0 flex-1">
        <p class="text-sm text-content truncate">{{ op.label }}</p>
        <p v-if="prompt" class="text-xs text-content-tertiary truncate">{{ prompt }}</p>
      </div>
    </div>

    <!-- Facts only: what is on screen, and how far behind it is. -->
    <div v-if="statusLine" class="mt-2 flex items-center gap-2">
      <p class="text-xs text-amber-400/90 flex-1">{{ statusLine }}</p>
      <button
        type="button"
        class="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :disabled="regenerating"
        @click.stop="emit('regenerate')"
      >
        <ArrowPathIcon class="w-3.5 h-3.5" :class="regenerating && 'animate-spin'" />
        Regenerate from here
      </button>
    </div>

    <button
      v-if="foldedCount > 0"
      type="button"
      class="mt-1.5 inline-flex items-center gap-1 text-xs text-content-tertiary hover:text-content-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60 rounded-md"
      :disabled="stale"
      @click.stop="emit('toggleExpanded')"
    >
      <ChevronRightIcon
        class="w-3 h-3 transition-transform"
        :class="showsSteps && 'rotate-90'"
      />
      Built from {{ foldedCount }} {{ foldedCount === 1 ? 'step' : 'steps' }}
    </button>
  </div>
</template>
