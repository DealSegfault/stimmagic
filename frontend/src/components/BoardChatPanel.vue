<template>
  <div ref="rootRef" class="relative" @click.stop>
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-surface-raised px-3 py-1.5 text-xs font-medium text-content-secondary transition-colors hover:bg-overlay-light hover:text-content"
      :aria-expanded="open"
      aria-haspopup="dialog"
      title="Chats de ce board"
      @click="toggle"
    >
      <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
      </svg>
      <span>Chats</span>
      <span v-if="chats.length" class="rounded-full bg-accent/15 px-1.5 font-mono text-[10px] text-accent">{{ chats.length }}</span>
    </button>

    <div
      v-if="open"
      class="absolute right-0 top-10 z-menu w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-xl border border-edge bg-surface shadow-xl"
      role="dialog"
      aria-label="Chats du board"
    >
      <div class="flex items-start justify-between gap-3 border-b border-edge-subtle px-4 py-3">
        <div class="min-w-0">
          <p class="text-xs font-semibold text-content">Chats du board</p>
          <p class="mt-0.5 truncate text-[11px] text-content-muted">{{ boardName || 'Board sans nom' }}</p>
        </div>
        <button
          type="button"
          class="inline-flex flex-none items-center gap-1.5 rounded-md bg-accent px-2.5 py-1.5 text-[11px] font-semibold text-accent-contrast transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="creating"
          @click="createNewChat"
        >
          <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          {{ creating ? 'Création…' : 'Nouveau chat' }}
        </button>
      </div>

      <div v-if="loading" class="px-4 py-6 text-center text-xs text-content-muted">Chargement des chats…</div>
      <div v-else-if="error" class="px-4 py-5 text-xs text-red-400" role="alert">
        {{ error }}
        <button type="button" class="ml-1 underline underline-offset-2 hover:text-red-300" @click="loadChats">Réessayer</button>
      </div>
      <div v-else-if="chats.length === 0" class="px-4 py-6 text-center">
        <p class="text-xs font-medium text-content-secondary">Aucun chat pour le moment</p>
        <p class="mt-1 text-[11px] leading-4 text-content-muted">Créez plusieurs conversations séparées pour explorer ce board.</p>
      </div>
      <div v-else class="max-h-[min(420px,60vh)] overflow-y-auto p-1.5">
        <button
          v-for="chat in chats"
          :key="chat.id"
          type="button"
          class="flex w-full items-start gap-3 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-overlay-subtle"
          @click="openChat(chat)"
        >
          <span class="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-md bg-accent/10 text-accent" aria-hidden="true">
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
            </svg>
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-xs font-medium text-content">{{ chat.name || 'Chat sans titre' }}</span>
            <span class="mt-0.5 block truncate text-[11px] text-content-muted">{{ chat.last_message || 'Aucun message' }}</span>
          </span>
          <span class="flex-none pt-0.5 text-[10px] tabular-nums text-content-tertiary">{{ formatDate(chat.updated_at) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useToasts } from '../composables/useToasts'

const props = defineProps({
  boardId: { type: Number, required: true },
  boardName: { type: String, default: '' },
  projectId: { type: Number, default: null }
})

const router = useRouter()
const { addToast } = useToasts()
const rootRef = ref(null)
const open = ref(false)
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const chats = ref([])

async function loadChats() {
  if (!props.boardId) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(`/api/chats/previews?board_id=${encodeURIComponent(props.boardId)}&page=1&page_size=100`)
    if (!response.ok) throw new Error('Impossible de charger les chats.')
    const payload = await response.json()
    chats.value = payload.items || []
  } catch (err) {
    error.value = err.message || 'Impossible de charger les chats.'
  } finally {
    loading.value = false
  }
}

function toggle() {
  open.value = !open.value
  if (open.value) loadChats()
}

async function createNewChat() {
  if (creating.value) return
  creating.value = true
  try {
    const payload = { board_id: props.boardId }
    if (props.projectId != null) payload.project_id = props.projectId
    const response = await fetch('/api/chats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const created = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(created.detail || 'Impossible de créer le chat.')
    open.value = false
    router.push({ name: 'chat', params: { id: created.id } })
  } catch (err) {
    addToast(err.message || 'Impossible de créer le chat.', 'error', 4000)
  } finally {
    creating.value = false
  }
}

function openChat(chat) {
  open.value = false
  router.push({ name: 'chat', params: { id: chat.id } })
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' })
}

function handleDocumentClick(event) {
  if (rootRef.value && !rootRef.value.contains(event.target)) open.value = false
}

watch(() => props.boardId, () => {
  chats.value = []
  if (open.value) loadChats()
})

onMounted(() => document.addEventListener('mousedown', handleDocumentClick))
onUnmounted(() => document.removeEventListener('mousedown', handleDocumentClick))
</script>
