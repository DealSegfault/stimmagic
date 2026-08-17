<template>
  <div class="h-full overflow-y-auto px-6 py-6 custom-scrollbar">
    <!-- Header bar -->
    <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-base font-bold text-content">Vidéos & Générations de la scène</h2>
        <p class="mt-0.5 text-xs text-content-secondary">
          Toutes les variantes et vidéos générées via le chat ou les outils pour cette scène.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-surface-raised px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
          :disabled="loading"
          @click="$emit('refresh')"
        >
          <svg class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
          <span>Actualiser</span>
        </button>

        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors"
          @click="$emit('open-chat')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          <span>Nouvel essai via Chat</span>
        </button>
      </div>
    </div>

    <!-- Loading skeletons -->
    <div v-if="loading && !generations.length" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 3" :key="i" class="h-64 animate-pulse rounded-xl border border-edge-subtle bg-surface" />
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center text-xs text-red-400">
      {{ error }}
    </div>

    <!-- Empty state -->
    <div v-else-if="!generations.length" class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-edge-subtle bg-surface/50 px-6 py-16 text-center">
      <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/10 text-accent mb-4">
        <svg class="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
        </svg>
      </div>
      <h3 class="text-sm font-semibold text-content">Aucune génération pour cette scène</h3>
      <p class="mt-1 max-w-sm text-xs text-content-muted">
        Ouvrez le chat de la scène pour générer des vidéos et des images en injectant automatiquement le script et les intentions.
      </p>
      <button
        type="button"
        class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors"
        @click="$emit('open-chat')"
      >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
        </svg>
        <span>Lancer une génération dans le Chat</span>
      </button>
    </div>

    <!-- Generations Grid -->
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <article
        v-for="item in generations"
        :key="item.id"
        class="group flex flex-col overflow-hidden rounded-xl border border-edge bg-surface shadow-sm transition-all hover:border-edge-strong"
      >
        <!-- Media Preview Box -->
        <div class="relative aspect-video w-full overflow-hidden bg-matte flex items-center justify-center">
          <!-- Video playback -->
          <video
            v-if="isVideo(item) && item.result_media_id && !item.media_deleted"
            :src="getMediaVideoUrl(item.result_media_id)"
            controls
            preload="metadata"
            playsinline
            class="h-full w-full object-contain"
          />

          <!-- Image playback -->
          <MediaImage
            v-else-if="item.result_media_id && !item.media_deleted"
            :media-id="item.result_media_id"
            :file-hash="item.result_file_hash"
            :file-format="item.result_file_format"
            thumbnail
            thumbnail-mode="fit"
            :thumbnail-size="512"
            :contain="true"
            :alt="`Génération ${item.id}`"
            :enable-context-menu="true"
            container-class="h-full w-full"
            img-class="h-full w-full object-contain"
          />

          <!-- Processing / Queued / Failed states -->
          <div v-else class="flex flex-col items-center justify-center p-4 text-center">
            <svg v-if="['processing', 'running'].includes(item.status)" class="h-6 w-6 animate-spin text-accent mb-2" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="text-xs font-semibold text-content-secondary">{{ statusLabel(item.status) }}</span>
            <p v-if="item.error" class="mt-1 line-clamp-2 text-[10px] text-red-400">{{ item.error }}</p>
          </div>

          <!-- Video format badge -->
          <span
            v-if="isVideo(item) && item.result_media_id"
            class="absolute top-2 left-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-white backdrop-blur-md"
          >
            Vidéo · {{ (item.result_file_format || 'mp4').toUpperCase() }}
          </span>

          <!-- Status badge -->
          <span
            class="absolute top-2 right-2 rounded-full px-2 py-0.5 text-[10px] font-semibold backdrop-blur-md border"
            :class="statusBadgeStyle(item.status)"
          >
            {{ statusLabel(item.status) }}
          </span>
        </div>

        <!-- Meta & Details -->
        <div class="flex flex-1 flex-col justify-between p-3.5 space-y-3">
          <div class="space-y-1.5">
            <div class="flex items-center justify-between text-[11px] text-content-muted">
              <span class="font-mono">#{{ item.id }} · {{ item.model_name || item.generator_name || 'Modèle' }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>

            <p v-if="item.prompt" class="line-clamp-2 text-xs leading-relaxed text-content-secondary" :title="item.prompt">
              {{ item.prompt }}
            </p>
          </div>

          <!-- Action bar -->
          <div v-if="item.result_media_id && !item.media_deleted" class="flex flex-wrap items-center gap-1.5 border-t border-edge-subtle pt-2.5">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md border border-edge bg-surface-raised px-2 py-1 text-[11px] font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
              title="Ajouter aux références du board"
              @click="$emit('add-to-board', { item, target: 'references' })"
            >
              <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              <span>Référence</span>
            </button>

            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors"
              title="Définir comme plan validé / Hero"
              @click="$emit('add-to-board', { item, target: 'approved' })"
            >
              <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
              <span>Valider ce plan</span>
            </button>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { MediaImage } from '../media'
import { getApiBase } from '../../apiConfig'

defineProps({
  generations: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  scene: { type: Object, default: null }
})

defineEmits(['refresh', 'open-chat', 'add-to-board'])

function isVideo(item) {
  const format = `${item?.task_type || ''} ${item?.result_file_format || ''}`.toLowerCase()
  return /video|mp4|webm|mov|avi|mkv/i.test(format)
}

function getMediaVideoUrl(mediaId) {
  return `${getApiBase()}/media/${mediaId}/file`
}

function statusLabel(status) {
  return {
    queued: 'En file',
    assigned: 'Assignée',
    processing: 'En cours',
    running: 'En cours',
    completed: 'Terminée',
    failed: 'Échec',
    cancelled: 'Annulée'
  }[status] || status || 'Inconnue'
}

function statusBadgeStyle(status) {
  if (status === 'completed') return 'border-emerald-500/30 bg-emerald-500/20 text-emerald-300'
  if (['failed', 'cancelled'].includes(status)) return 'border-red-500/30 bg-red-500/20 text-red-300'
  if (['processing', 'running'].includes(status)) return 'border-accent/30 bg-accent/20 text-accent'
  return 'border-edge bg-surface/80 text-content-secondary'
}

function formatDate(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return ''
  }
}
</script>
