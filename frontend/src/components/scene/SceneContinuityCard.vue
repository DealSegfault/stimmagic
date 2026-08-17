<template>
  <div class="h-full overflow-y-auto px-6 py-6 custom-scrollbar">
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Title header -->
      <div>
        <h2 class="text-base font-bold text-content">Raccord de Continuité</h2>
        <p class="mt-0.5 text-xs text-content-secondary">
          Assurez la cohérence visuelle, l'éclairage et le cadrage entre la fin de la scène précédente et le début de cette scène.
        </p>
      </div>

      <!-- Loading skeleton -->
      <div v-if="loading" class="h-64 animate-pulse rounded-2xl border border-edge-subtle bg-surface" />

      <!-- Error state -->
      <div v-else-if="error" class="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center text-xs text-red-400">
        {{ error }}
      </div>

      <!-- Continuity Data available -->
      <div v-else-if="continuity?.previous_scene && continuity?.last_frame" class="rounded-2xl border border-edge bg-surface p-6 shadow-sm space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-edge-subtle pb-4">
          <div>
            <span class="inline-flex items-center gap-1 rounded-md bg-accent/15 px-2 py-0.5 font-mono text-xs font-semibold text-accent uppercase">
              Scène {{ continuity.previous_scene.scene_number }} → Scène {{ currentScene?.scene_number }}
            </span>
            <h3 class="mt-1 text-sm font-semibold text-content">
              Dernière frame de « {{ continuity.previous_scene.title }} »
            </h3>
          </div>

          <span class="rounded-full bg-overlay-subtle px-2.5 py-1 text-[11px] font-medium text-content-secondary">
            {{ continuity.last_frame.extracted ? 'Frame vidéo extraite' : 'Image de rendu' }}
          </span>
        </div>

        <!-- Frame display box -->
        <div class="grid gap-6 md:grid-cols-2">
          <!-- Previous frame -->
          <div class="space-y-2">
            <div class="flex items-center justify-between text-xs font-medium text-content-secondary">
              <span>Scène précédente (S{{ continuity.previous_scene.scene_number }})</span>
              <span class="font-mono text-[11px] text-content-muted">Fin de plan</span>
            </div>
            <div class="relative aspect-video overflow-hidden rounded-xl border border-edge bg-matte shadow-inner">
              <img
                :src="frameUrl"
                :alt="`Dernière frame de ${continuity.previous_scene.title}`"
                class="h-full w-full object-contain"
                loading="lazy"
              />
            </div>
          </div>

          <!-- Current scene context & action -->
          <div class="flex flex-col justify-between rounded-xl border border-edge-subtle bg-surface-raised/40 p-4 space-y-4">
            <div class="space-y-2">
              <h4 class="text-xs font-semibold uppercase tracking-wider text-accent">Raccord dans le chat</h4>
              <p class="text-xs leading-relaxed text-content-secondary">
                Cette image de raccord est automatiquement disponible dans le contexte du chat de la scène pour guider la cohérence des générations IA.
              </p>
            </div>

            <div class="space-y-2">
              <button
                type="button"
                class="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors"
                @click="$emit('open-chat')"
              >
                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
                </svg>
                <span>Utiliser ce raccord dans le Chat</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- No previous scene or no completed render yet -->
      <div v-else class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-edge-subtle bg-surface/50 px-6 py-16 text-center">
        <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-overlay-subtle text-content-muted mb-3">
          <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
          </svg>
        </div>
        <h3 class="text-sm font-semibold text-content">
          {{ !continuity?.previous_scene ? 'Première scène du projet' : 'Aucun rendu terminé pour la scène précédente' }}
        </h3>
        <p class="mt-1 max-w-sm text-xs text-content-muted">
          {{ !continuity?.previous_scene
            ? 'Cette scène est la première de la séquence. Aucun raccord antérieur n’est nécessaire.'
            : 'Dès qu’une vidéo ou un plan de la scène précédente sera généré, sa dernière image apparaîtra ici automatiquement.' }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { getApiBase } from '../../apiConfig'

const props = defineProps({
  continuity: { type: Object, default: () => ({}) },
  currentScene: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

defineEmits(['open-chat'])

const frameUrl = computed(() => {
  const path = props.continuity?.last_frame?.frame_url
  return path ? `${getApiBase()}${path}` : ''
})
</script>
