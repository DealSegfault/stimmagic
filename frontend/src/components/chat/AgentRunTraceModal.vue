<template>
  <Modal
    :show="show"
    size="custom"
    custom-class="max-w-5xl w-full max-h-[88vh] flex flex-col"
    @close="$emit('close')"
  >
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <div>
          <h2 class="text-base font-semibold text-content">Agent run trace</h2>
          <p class="mt-0.5 text-xs text-content-muted">
            Operational decisions, tool calls, references, jobs and results.
            Private chain-of-thought is not stored here.
          </p>
        </div>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs text-content-muted hover:bg-surface-raised hover:text-content"
          :disabled="loading"
          @click="loadRuns"
        >
          Refresh
        </button>
      </div>
    </template>

    <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden p-4 sm:flex-row">
      <aside class="w-full shrink-0 overflow-y-auto sm:w-72" aria-label="Agent runs">
        <div v-if="error" role="alert" class="rounded border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">
          {{ error }}
        </div>
        <div v-else-if="loading && !runs.length" class="space-y-2" aria-busy="true" aria-label="Loading agent traces">
          <div v-for="index in 3" :key="index" class="h-16 animate-pulse rounded border border-edge bg-surface" />
        </div>
        <div v-else-if="!runs.length" role="status" class="rounded border border-dashed border-edge p-4 text-center text-xs text-content-muted">
          No agent runs yet. Start a chat action to create the first trace.
        </div>
        <div v-else class="space-y-2">
          <button
            v-for="run in runs"
            :key="run.id"
            type="button"
            class="w-full rounded border p-3 text-left transition-colors"
            :class="selectedRunId === run.id ? 'border-accent bg-accent/10' : 'border-edge bg-surface hover:bg-surface-raised'"
            @click="selectRun(run.id)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="truncate text-xs font-medium text-content">{{ run.workflow }}</span>
              <span class="font-mono text-[10px]" :class="statusClass(run.status)">{{ run.status }}</span>
            </div>
            <p class="mt-1 line-clamp-2 text-[11px] text-content-secondary">{{ run.request_summary || 'Agent continuation' }}</p>
            <div class="mt-2 flex items-center justify-between text-[10px] text-content-muted">
              <span>{{ run.step_count ?? 0 }} steps</span>
              <span>{{ formatTime(run.started_at) }}</span>
            </div>
          </button>
        </div>
      </aside>

      <section class="min-h-0 min-w-0 flex-1 overflow-y-auto rounded border border-edge bg-base p-4" aria-live="polite" :aria-busy="detailLoading">
        <div v-if="!selectedRun && detailLoading" class="text-xs text-content-muted">Loading trace…</div>
        <div v-else-if="!selectedRun" class="flex h-full items-center justify-center text-center text-xs text-content-muted">
          Select a run to inspect its loop.
        </div>
        <div v-else>
          <div class="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-edge pb-3">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-semibold text-content">{{ selectedRun.summary || 'Agent execution' }}</h3>
                <span class="font-mono text-[10px]" :class="statusClass(selectedRun.status)">{{ selectedRun.status }}</span>
              </div>
              <p class="mt-1 text-[11px] text-content-muted">Run {{ selectedRun.id }}</p>
            </div>
            <button
              type="button"
              class="rounded border border-edge px-2 py-1 text-[11px] text-content-secondary hover:bg-surface-raised"
              @click="copyTrace"
            >
              Copy trace JSON
            </button>
          </div>

          <div v-if="selectedRun.error" class="mb-4 rounded border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">
            {{ selectedRun.error }}
          </div>

          <ol class="space-y-3" aria-label="Agent loop steps">
            <li v-for="step in selectedRun.steps || []" :key="step.id" class="relative pl-7">
              <span class="absolute left-0 top-1.5 flex h-4 w-4 items-center justify-center rounded-full border text-[9px]" :class="stepStatusClass(step.status)">
                {{ step.sequence }}
              </span>
              <div class="rounded border border-edge bg-surface p-3">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="flex items-center gap-2">
                    <span class="font-mono text-[10px] uppercase tracking-wide text-accent">{{ step.stage }}</span>
                    <span class="text-xs font-medium text-content">{{ step.name }}</span>
                  </div>
                  <span class="font-mono text-[10px]" :class="statusClass(step.status)">{{ step.status }}</span>
                </div>
                <p class="mt-1 text-xs text-content-secondary">{{ step.summary }}</p>
                <p v-if="step.detail?.decision_summary" class="mt-2 rounded bg-accent/5 px-2 py-1 text-[11px] text-content-secondary">
                  Decision: {{ step.detail.decision_summary }}
                </p>
                <div v-if="step.detail?.action" class="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-content-muted">
                  <span class="rounded bg-accent/10 px-1.5 py-0.5 text-accent">{{ step.detail.action.kind }}</span>
                  <span v-if="step.detail.action.prompt_preview || step.detail.action.code_preview" class="max-w-full truncate" :title="step.detail.action.prompt_preview || step.detail.action.code_preview">
                    {{ step.detail.action.prompt_preview ? 'prompt' : 'code' }}: {{ step.detail.action.prompt_preview || step.detail.action.code_preview }}
                  </span>
                </div>
                <div v-if="step.generation_job_id || step.media_ids?.length" class="mt-2 flex flex-wrap gap-2 text-[10px] text-content-muted">
                  <span v-if="step.generation_job_id" class="rounded bg-overlay-faint px-1.5 py-0.5">job {{ step.generation_job_id }}</span>
                  <span v-for="mediaId in step.media_ids || []" :key="mediaId" class="rounded bg-overlay-faint px-1.5 py-0.5">media {{ mediaId }}</span>
                </div>
                <div v-if="step.detail?.action?.reference_media_ids?.length" class="mt-2 flex flex-wrap gap-2 text-[10px] text-content-muted">
                  <span class="text-content-secondary">references</span>
                  <span v-for="mediaId in step.detail.action.reference_media_ids" :key="mediaId" class="rounded bg-overlay-faint px-1.5 py-0.5">media {{ mediaId }}</span>
                </div>
                <details v-if="step.detail && Object.keys(step.detail).length" class="mt-2">
                  <summary class="cursor-pointer text-[11px] text-content-muted hover:text-content-secondary">Inputs / outputs / decision data</summary>
                  <pre class="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-base p-2 text-[10px] text-content-secondary">{{ pretty(step.detail) }}</pre>
                </details>
              </div>
            </li>
          </ol>
        </div>
      </section>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import Modal from '../ui/Modal.vue'
import { getCurrentProfileId } from '../../composables/useProfile'

const props = defineProps<{ show: boolean; chatId: number | string | null }>()
defineEmits<{ (event: 'close'): void }>()

const runs = ref<any[]>([])
const selectedRunId = ref<string | null>(null)
const selectedRun = ref<any | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
let refreshTimer: ReturnType<typeof setInterval> | null = null
const terminalStatuses = new Set(['completed', 'failed', 'paused', 'cancelled'])

const profileHeaders = computed(() => ({ 'X-Profile-ID': getCurrentProfileId() }))

async function loadRuns() {
  if (!props.chatId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/chats/${props.chatId}/agent-runs?limit=30`, { headers: profileHeaders.value })
    if (!response.ok) throw new Error(`Trace request failed (${response.status})`)
    const data = await response.json()
    runs.value = data.items || []
    if (!selectedRunId.value && runs.value[0]) selectedRunId.value = runs.value[0].id
    const selectedSummary = runs.value.find((run) => run.id === selectedRunId.value)
    const selectedNeedsRefresh = selectedSummary && (
      !selectedRun.value
      || selectedRun.value.id !== selectedSummary.id
      || selectedRun.value.status !== selectedSummary.status
      || !terminalStatuses.has(selectedSummary.status)
    )
    if (selectedRunId.value && selectedNeedsRefresh) await loadDetail(selectedRunId.value)
  } catch (requestError: any) {
    error.value = requestError?.message || 'Unable to load agent traces.'
  } finally {
    loading.value = false
  }
}

async function loadDetail(runId: string) {
  detailLoading.value = true
  try {
    const response = await fetch(`/api/agent-runs/${encodeURIComponent(runId)}`, { headers: profileHeaders.value })
    if (!response.ok) throw new Error(`Trace detail failed (${response.status})`)
    selectedRun.value = await response.json()
  } catch (requestError: any) {
    error.value = requestError?.message || 'Unable to load trace details.'
  } finally {
    detailLoading.value = false
  }
}

function selectRun(runId: string) {
  selectedRunId.value = runId
  loadDetail(runId)
}

function startRefresh() {
  stopRefresh()
  void (async () => {
    await loadRuns()
    if (!props.show || !runs.value.length || runs.value.some((run) => !terminalStatuses.has(run.status))) {
      refreshTimer = setInterval(() => { void loadRuns() }, 2500)
    }
  })()
}

function stopRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = null
}

watch(() => props.show, (visible) => {
  if (visible) startRefresh()
  else stopRefresh()
})

onUnmounted(stopRefresh)

function statusClass(status: string) {
  if (status === 'completed') return 'text-emerald-400'
  if (status === 'failed' || status === 'cancelled') return 'text-red-400'
  if (status === 'paused') return 'text-amber-400'
  return 'text-sky-400'
}

function stepStatusClass(status: string) {
  if (status === 'completed') return 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
  if (status === 'failed' || status === 'cancelled') return 'border-red-500/50 bg-red-500/10 text-red-400'
  if (status === 'paused') return 'border-amber-500/50 bg-amber-500/10 text-amber-400'
  return 'border-sky-500/50 bg-sky-500/10 text-sky-400'
}

function formatTime(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2)
}

async function copyTrace() {
  if (!selectedRun.value) return
  await navigator.clipboard?.writeText(JSON.stringify(selectedRun.value, null, 2))
}
</script>
