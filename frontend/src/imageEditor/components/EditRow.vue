<script setup lang="ts">
/**
 * One row in the Edits list.
 *
 * The row grammar IS the cost signal: the eye toggle, drag grip and candidate
 * chips respond to the hand and are free; anything that costs money is a
 * button, never a slider. Rows carry no price badges — the shape of the control
 * says it.
 *
 * Rows hold identity, eye, candidates and advisory state only. The full control
 * surface for a selected row lives in the inspector below the stack, because a
 * 40-knob tool cannot live in a 42px row.
 *
 * Ordering is never required of the user: new steps auto-place on top, and the
 * common intents are row-menu verbs that perform the move mechanically. Drag
 * stays as the direct-manipulation path for people who want it.
 */
import { computed, ref } from 'vue'
import {
  EyeIcon, EyeSlashIcon, TrashIcon, EllipsisHorizontalIcon,
  ArrowPathIcon, Bars2Icon,
} from '@heroicons/vue/24/outline'
import IconButton from '../../components/ui/IconButton.vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import { getTaskTypeIconSvg } from '../../utils/taskTypeIcons'
import { sanitizeSvg } from '../../utils/sanitizeHtml'
import type { Op } from '../stack/types'
import type { Staleness } from '../stack/stackState'

export interface RowVerb {
  id: string
  label: string
  disabled?: boolean
}

const props = defineProps<{
  op: Op
  selected: boolean
  staleness: Staleness
  /** Candidate thumbnails, resolved by the parent. */
  candidateThumbs?: Array<{ id: string; url: string; fromPreviousState?: boolean }>
  /** Jobs still running for this op. */
  pendingCount?: number
  /** Blast-radius preview: this row would be disturbed by the hovered gesture. */
  previewStaleness?: Staleness | null
  /** Its spatial payload no longer intersects the frame. */
  outOfFrame?: boolean
  verbs?: RowVerb[]
  /** Display name of the tool that produced this step's pixels. */
  toolName?: string
  resampling?: boolean
  draggable?: boolean
}>()

const emit = defineEmits<{
  select: []
  /** Double-click: re-enter a container op's session. */
  reenter: []
  toggle: [boolean]
  pick: [string]
  remove: []
  resample: []
  verb: [string]
  /** Hovering a gesture affordance — drives the blast-radius tint. */
  intentHover: [boolean]
  dragStart: [DragEvent]
  dragOver: [DragEvent]
  drop: [DragEvent]
}>()

const menuOpen = ref(false)
const anyOp = computed(() => props.op as any)


/**
 * The sampling tool, so a row never hides what produced its pixels — by its
 * display name. A slug is an internal identifier and putting one in the UI
 * asks the user to read our routing table.
 */
const subtitle = computed(() => {
  if (props.op.class === 'patch' || props.op.class === 'whole') {
    return props.toolName || ''
  }
  return ''
})

const candidates = computed(() => props.candidateThumbs || [])
const picked = computed(() => anyOp.value.picked || null)
const staged = computed(() => candidates.value.length > 0 && !picked.value)
const isGenerative = computed(() => props.op.class === 'patch' || props.op.class === 'whole')

const advisory = computed(() => props.staleness === 'advisory')
const previewTint = computed(() => {
  if (props.previewStaleness === 'hard') return 'ring-1 ring-amber-500/40 bg-amber-500/[0.07]'
  if (props.previewStaleness === 'advisory') return 'ring-1 ring-amber-500/20'
  return ''
})
</script>

<template>
  <div
    :data-op-id="op.id"
    tabindex="0"
    class="group flex items-start gap-1.5 px-2 py-2 rounded-md cursor-default transition-colors
           focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
    :class="[
      selected ? 'bg-selection/15' : 'hover:bg-overlay-subtle',
      previewTint,
    ]"
    :draggable="draggable"
    @click="emit('select')"
    @dblclick="emit('reenter')"
    @dragstart="emit('dragStart', $event)"
    @dragover.prevent="emit('dragOver', $event)"
    @drop.prevent="emit('drop', $event)"
  >
    <!-- Drag grip. Hovering it previews what the move would disturb. -->
    <span
      v-if="draggable"
      class="mt-1.5 shrink-0 text-content-tertiary opacity-0 group-hover:opacity-100 cursor-grab"
      @mouseenter="emit('intentHover', true)"
      @mouseleave="emit('intentHover', false)"
    >
      <Bars2Icon class="w-3.5 h-3.5" />
    </span>

    <Tooltip :text="op.enabled ? 'Hide this edit' : 'Show this edit'">
      <IconButton
        @click.stop="emit('toggle', !op.enabled)"
        @mouseenter="emit('intentHover', true)"
        @mouseleave="emit('intentHover', false)"
      >
        <EyeIcon v-if="op.enabled" class="w-4 h-4" />
        <EyeSlashIcon v-else class="w-4 h-4 text-content-tertiary" />
      </IconButton>
    </Tooltip>

    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-1.5">
        <span class="text-sm truncate" :class="op.enabled ? 'text-content' : 'text-content-tertiary'">
          {{ op.label }}
        </span>
        <!-- Advisory: informational, never a blocker. Pixel-deterministic. -->
        <Tooltip v-if="advisory" text="Sampled against an earlier state · Resample">
          <span class="w-1.5 h-1.5 rounded-full bg-amber-400/80 shrink-0" />
        </Tooltip>
      </div>
      <!-- The sampling tool gets its own line: sharing the label's baseline
           squeezes both to ellipses in a 320px panel. -->
      <p v-if="subtitle" class="text-xs text-content-tertiary truncate">{{ subtitle }}</p>

      <div v-if="op.region" class="mt-1">
        <span class="inline-flex items-center px-1.5 py-0.5 text-[11px] rounded-md bg-overlay-subtle text-content-tertiary">
          Limited to a region
        </span>
      </div>

      <p v-if="outOfFrame" class="mt-1 text-xs text-content-tertiary">Out of frame</p>

      <!-- Candidate strip. Switching picks is free, so it lives on the row. -->
      <div v-if="candidates.length || pendingCount" class="flex items-center gap-1.5 mt-1.5">
        <button
          v-for="candidate in candidates"
          :key="candidate.id"
          type="button"
          class="relative w-10 h-10 rounded-media overflow-hidden bg-matte transition-shadow focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="candidate.id === picked ? 'ring-2 ring-selection' : 'opacity-70 hover:opacity-100'"
          @click.stop="emit('pick', candidate.id)"
        >
          <img :src="candidate.url" class="w-full h-full object-cover" alt="" />
          <span
            v-if="candidate.fromPreviousState"
            class="absolute bottom-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400/90"
          />
        </button>
        <div
          v-for="n in (pendingCount || 0)"
          :key="`pending-${n}`"
          class="w-10 h-10 rounded-media bg-surface-raised animate-pulse"
        />
      </div>
      <p v-if="staged" class="mt-1 text-xs text-content-tertiary">Pick one to apply it.</p>
    </div>

    <!-- The only control on the row that costs anything is a button. -->
    <Tooltip v-if="isGenerative" text="Resample with the current input">
      <IconButton
        class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        :disabled="resampling"
        @click.stop="emit('resample')"
      >
        <ArrowPathIcon class="w-4 h-4" :class="resampling && 'animate-spin'" />
      </IconButton>
    </Tooltip>

    <div v-if="verbs?.length" class="relative">
      <IconButton
        class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        @click.stop="menuOpen = !menuOpen"
      >
        <EllipsisHorizontalIcon class="w-4 h-4" />
      </IconButton>
      <div
        v-if="menuOpen"
        class="absolute right-0 top-8 z-menu min-w-44 py-1 rounded-lg bg-surface-overlay border border-edge-subtle shadow-lg"
        @mouseleave="menuOpen = false"
      >
        <button
          v-for="verb in verbs"
          :key="verb.id"
          type="button"
          class="w-full px-3 py-1.5 text-left text-xs text-content-secondary hover:text-content hover:bg-overlay-subtle disabled:opacity-40 disabled:hover:bg-transparent"
          :disabled="verb.disabled"
          @click.stop="menuOpen = false; emit('verb', verb.id)"
        >
          {{ verb.label }}
        </button>
      </div>
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
