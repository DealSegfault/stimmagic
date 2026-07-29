<script setup lang="ts">
/**
 * One row in the Edits list.
 *
 * The row grammar IS the cost signal: the eye toggle, drag grip and candidate
 * chips respond to the hand and are free; anything that costs money is a
 * button, never a slider. Rows carry no price badges — the shape of the control
 * says it.
 *
 * Layout law for the Edits list (EditRow and BaseRow both obey it, which is
 * what makes the column read):
 *   - The square preview is the row's anchor: one size, one position, in every
 *     row, so the list reads as a single column of images down the panel.
 *   - The title's first line centers on the square. Subtitles and chips flow
 *     BELOW that line, growing the row downward — so a row with one line and a
 *     row with four still align at the top, against their squares.
 *   - Controls live to the right of the text, in one cluster: eye, then
 *     remove. Both are permanent — whether a step is on, and the way to take
 *     it off, are not things to go hunting for under the cursor. Only
 *     Resample, which costs money, waits for hover.
 *
 * Rows hold identity, eye, candidates and advisory state only. The full control
 * surface for a selected row lives in the inspector below the stack, because a
 * 40-knob tool cannot live in a 42px row. There is no row overflow menu: a
 * menu of mostly-disabled verbs is not a control surface, it is a place things
 * go to be undiscoverable.
 *
 * Reordering is drag, and only drag.
 */
import { computed } from 'vue'
import {
  EyeIcon, EyeSlashIcon, TrashIcon, ArrowPathIcon,
} from '@heroicons/vue/24/outline'
import DragGrip from '../../components/ui/DragGrip.vue'
import IconButton from '../../components/ui/IconButton.vue'
import Tooltip from '../../components/ui/Tooltip.vue'
import { getTaskTypeIconSvg } from '../../utils/taskTypeIcons'
import { sanitizeSvg } from '../../utils/sanitizeHtml'
import { ROW_SQUARE, ROW_COLUMN, ROW_COLUMN_INLINE } from './rowLayout'
import type { Op } from '../stack/types'
import type { Staleness } from '../stack/stackState'

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
  /** Display name of the tool that produced this step's pixels. */
  toolName?: string
  resampling?: boolean
  draggable?: boolean
  /** This row is the one being dragged — it reads as lifted out of the list. */
  dragging?: boolean
  /** The image as of this step — the row's square. Absent until first render. */
  preview?: string
}>()

const emit = defineEmits<{
  select: []
  /** Double-click: re-enter a container op's session. */
  reenter: []
  toggle: [boolean]
  pick: [string]
  remove: []
  resample: []
  /** Hovering a gesture affordance — drives the blast-radius tint. */
  intentHover: [boolean]
  dragStart: [DragEvent]
  dragEnd: []
}>()

const anyOp = computed(() => props.op as any)


/**
 * The sampling tool, so a row never hides what produced its pixels — by its
 * display name. A slug is an internal identifier and putting one in the UI
 * asks the user to read our routing table.
 */
const subtitle = computed(() => (props.op.class === 'patch' ? props.toolName || '' : ''))

const candidates = computed(() => props.candidateThumbs || [])
const picked = computed(() => anyOp.value.picked || null)
const staged = computed(() => candidates.value.length > 0 && !picked.value)
const isGenerative = computed(() => props.op.class === 'patch')

const advisory = computed(() => props.staleness === 'advisory')
const previewTint = computed(() =>
  props.previewStaleness === 'advisory' ? 'ring-1 ring-amber-500/20' : ''
)
</script>

<template>
  <!-- `dragging` lifts the row: the one you are carrying reads as no longer
       in place, so the drop line is read against the list the move leaves. -->
  <div
    :data-op-id="op.id"
    tabindex="0"
    class="group flex items-start gap-1.5 px-2 py-2 rounded-md cursor-default transition-colors
           focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
    :class="[
      selected ? 'bg-selection/15' : 'hover:bg-overlay-subtle',
      previewTint,
      dragging && 'opacity-40',
    ]"
    :draggable="draggable"
    @click="emit('select')"
    @dblclick="emit('reenter')"
    @dragstart="emit('dragStart', $event)"
    @dragend="emit('dragEnd')"
  >
    <!-- Drag grip. Hovering it previews what the move would disturb. -->
    <span
      v-if="draggable"
      :class="[
        ROW_COLUMN_INLINE,
        'shrink-0 text-content-tertiary opacity-0 group-hover:opacity-100 cursor-grab active:cursor-grabbing',
      ]"
      @mouseenter="emit('intentHover', true)"
      @mouseleave="emit('intentHover', false)"
    >
      <DragGrip class="w-2.5 h-4" />
    </span>

    <!-- The image as of this step. A hidden step shows what the stack looks
         like without it, dimmed — the eye is no longer beside the label, so
         the square carries the disabled state. -->
    <div :class="[ROW_SQUARE, !op.enabled && 'opacity-40']">
      <img v-if="preview" :src="preview" class="w-full h-full object-cover" alt="" />
      <div v-else class="w-full h-full bg-surface-raised animate-pulse" />
    </div>

    <div :class="['min-w-0 flex-1', ROW_COLUMN]">
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

    <!-- Control cluster: one group, centered on the square like the title, so
         the controls sit on the title's line and not above it. The only
         control that costs anything is a button. -->
    <div :class="[ROW_COLUMN_INLINE, 'shrink-0']">
    <Tooltip v-if="isGenerative" text="Resample with the current input">
      <IconButton
        class="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        :disabled="resampling"
        @click.stop="emit('resample')"
      >
        <ArrowPathIcon class="w-4 h-4" :class="resampling && 'animate-spin'" />
      </IconButton>
    </Tooltip>

    <!-- The eye stays visible at rest, unlike its neighbours: whether a step
         is on is state you read, not an action you go looking for. -->
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

    <Tooltip text="Remove this edit">
      <IconButton
        variant="danger"
        @click.stop="emit('remove')"
      >
        <TrashIcon class="w-4 h-4" />
      </IconButton>
    </Tooltip>
    </div>
  </div>
</template>
