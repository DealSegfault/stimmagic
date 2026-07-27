<script setup lang="ts">
/**
 * One row in the Edits list.
 *
 * The row grammar IS the cost signal: an eye toggle and candidate chips
 * respond to the hand and are free; anything that costs is a button, never a
 * slider. Rows carry no price badges — the shape of the control says it.
 *
 * Identity, eye, candidates and advisory state only. The full control surface
 * for a selected row lives in the inspector below the stack, rendered from the
 * tool's schema, because a 40-knob tool cannot live in a 42px row.
 */
import { computed } from 'vue'
import { EyeIcon, EyeSlashIcon, TrashIcon } from '@heroicons/vue/24/outline'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import { getTaskTypeIconSvg } from '../../utils/taskTypeIcons'
import { sanitizeSvg } from '../../utils/sanitizeHtml'
import type { Op } from '../../composables/imageStack/types'

const props = defineProps<{
  op: Op
  selected: boolean
  /** Candidate thumbnails, resolved by the parent. */
  candidateThumbs?: Array<{ id: string; url: string }>
  /** Jobs still running for this op. */
  pendingCount?: number
}>()

const emit = defineEmits<{
  select: []
  toggle: [boolean]
  pick: [string]
  remove: []
}>()

const anyOp = computed(() => props.op as any)

const iconSvg = computed(() => {
  const taskType = anyOp.value.exec?.task_type
    || (props.op.class === 'parametric' ? 'filter' : 'image-to-image')
  return sanitizeSvg(
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
      stroke-linecap="round" stroke-linejoin="round">${getTaskTypeIconSvg(taskType)}</svg>`
  )
})

/** The sampling tool, so a row never hides what produced its pixels. */
const subtitle = computed(() => {
  if (props.op.class === 'patch' || props.op.class === 'whole') {
    const toolId = anyOp.value.exec?.tool_id || ''
    return toolId.split(':').slice(1).join(':') || toolId
  }
  return ''
})

const candidates = computed(() => props.candidateThumbs || [])
const picked = computed(() => anyOp.value.picked || null)
const staged = computed(() => candidates.value.length > 0 && !picked.value)
</script>

<template>
  <div
    class="group flex items-start gap-2 px-2 py-2 rounded-md cursor-default transition-colors"
    :class="selected ? 'bg-selection/15' : 'hover:bg-overlay-subtle'"
    @click="emit('select')"
  >
    <Tooltip :text="op.enabled ? 'Hide this edit' : 'Show this edit'">
      <IconButton @click.stop="emit('toggle', !op.enabled)">
        <EyeIcon v-if="op.enabled" class="w-4 h-4" />
        <EyeSlashIcon v-else class="w-4 h-4 text-content-tertiary" />
      </IconButton>
    </Tooltip>

    <div class="w-4 h-4 mt-1.5 shrink-0 text-content-secondary" v-html="iconSvg" />

    <div class="min-w-0 flex-1">
      <div class="flex items-baseline gap-2">
        <span class="text-sm truncate" :class="op.enabled ? 'text-content' : 'text-content-tertiary'">
          {{ op.label }}
        </span>
        <span v-if="subtitle" class="text-xs text-content-tertiary truncate">{{ subtitle }}</span>
      </div>

      <!-- Candidate strip. Switching picks is free and instant, so it lives on
           the row rather than behind the inspector. -->
      <div v-if="candidates.length || pendingCount" class="flex items-center gap-1.5 mt-1.5">
        <button
          v-for="candidate in candidates"
          :key="candidate.id"
          type="button"
          class="w-10 h-10 rounded-media overflow-hidden bg-matte transition-shadow focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="candidate.id === picked
            ? 'ring-2 ring-selection'
            : 'opacity-70 hover:opacity-100'"
          @click.stop="emit('pick', candidate.id)"
        >
          <img :src="candidate.url" class="w-full h-full object-cover" alt="" />
        </button>
        <div
          v-for="n in (pendingCount || 0)"
          :key="`pending-${n}`"
          class="w-10 h-10 rounded-media bg-surface-raised animate-pulse"
        />
      </div>
      <p v-if="staged" class="mt-1 text-xs text-content-tertiary">Pick one to apply it.</p>
    </div>

    <Tooltip text="Remove this edit">
      <IconButton
        variant="danger"
        class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        @click.stop="emit('remove')"
      >
        <TrashIcon class="w-4 h-4" />
      </IconButton>
    </Tooltip>
  </div>
</template>
