<template>
  <div class="border-b border-edge-subtle bg-surface">
    <!-- Header bar with sequence title, scene counter & collapse toggle -->
    <div class="flex items-center justify-between px-6 py-2.5 bg-surface-raised/40">
      <div class="flex items-center gap-2.5 min-w-0">
        <span class="inline-flex items-center gap-1 rounded-md bg-accent/15 px-2 py-0.5 font-mono text-[11px] font-bold text-accent uppercase">
          Séquence {{ sequenceNumber }}
        </span>
        <h2 class="text-xs font-semibold text-content truncate">
          Scènes de la séquence ({{ scenes.length }})
        </h2>
        <span class="text-[11px] text-content-muted hidden sm:inline">
          · Cliquez sur une scène pour charger ses références, ses vidéos et son chat
        </span>
      </div>

      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
          @click="isCollapsed = !isCollapsed"
        >
          <span>{{ isCollapsed ? 'Déplier le tableau' : 'Replier' }}</span>
          <svg
            class="h-3.5 w-3.5 transition-transform"
            :class="{ 'rotate-180': isCollapsed }"
            fill="none"
            viewBox="0 0 24 24"
            stroke-width="2"
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 15.75 7.5-7.5 7.5 7.5" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Collapsible Table of Scenes -->
    <div v-show="!isCollapsed" class="overflow-x-auto border-t border-edge-subtle/60 custom-scrollbar">
      <table class="w-full min-w-[700px] border-collapse text-left text-xs">
        <thead>
          <tr class="border-b border-edge-subtle/80 bg-surface/50 text-[10px] font-semibold uppercase tracking-wider text-content-tertiary">
            <th class="w-16 px-4 py-2">#</th>
            <th class="px-4 py-2">Scène & Action</th>
            <th class="w-36 px-4 py-2">Générations</th>
            <th class="w-36 px-4 py-2">Statut</th>
            <th class="w-28 px-4 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-edge-subtle/40">
          <tr
            v-for="(scene, index) in scenes"
            :key="scene.id"
            class="group cursor-pointer transition-colors"
            :class="selectedSceneId === scene.id ? 'bg-accent/10 font-medium' : 'hover:bg-overlay-faint'"
            @click="$emit('select-scene', scene.id)"
          >
            <!-- Scene Index Badge -->
            <td class="px-4 py-2.5 align-middle">
              <div class="flex items-center gap-2">
                <span
                  class="flex h-6 w-6 items-center justify-center rounded-md font-mono text-[11px] font-bold transition-colors"
                  :class="selectedSceneId === scene.id
                    ? 'bg-accent text-accent-contrast shadow-sm'
                    : 'bg-overlay-subtle text-content-secondary group-hover:bg-overlay-medium'"
                >
                  {{ String(scene.scene_number || index + 1).padStart(2, '0') }}
                </span>
              </div>
            </td>

            <!-- Title & Description preview -->
            <td class="px-4 py-2.5 align-middle">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span
                    class="font-semibold transition-colors"
                    :class="selectedSceneId === scene.id ? 'text-accent' : 'text-content group-hover:text-content'"
                  >
                    {{ scene.title }}
                  </span>
                  <span
                    v-if="selectedSceneId === scene.id"
                    class="rounded-full bg-accent/20 px-1.5 py-0.2 text-[9px] font-semibold text-accent"
                  >
                    Active
                  </span>
                </div>
                <p v-if="cleanSummary(scene)" class="mt-0.5 line-clamp-1 text-[11px] text-content-muted">
                  {{ cleanSummary(scene) }}
                </p>
              </div>
            </td>

            <!-- Generation count & state -->
            <td class="px-4 py-2.5 align-middle">
              <div class="flex items-center gap-1.5">
                <span
                  class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
                  :class="(scene.generation_count || 0) > 0
                    ? 'bg-accent/15 text-accent font-semibold'
                    : 'bg-overlay-subtle text-content-muted'"
                >
                  <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
                  </svg>
                  <span>{{ (scene.generation_count || 0) }} essai{{ (scene.generation_count || 0) > 1 ? 's' : '' }}</span>
                </span>
              </div>
            </td>

            <!-- Status selector -->
            <td class="px-4 py-2.5 align-middle" @click.stop>
              <select
                :value="scene.status || 'planned'"
                class="cursor-pointer appearance-none rounded-md border border-edge-subtle bg-surface-raised px-2 py-1 text-[11px] font-medium text-content outline-none transition-colors hover:border-edge focus:border-accent"
                @change="$emit('update-scene-status', { sceneId: scene.id, status: $event.target.value })"
              >
                <option value="planned">Planifiée</option>
                <option value="in_progress">En cours</option>
                <option value="ready_for_review">À valider</option>
                <option value="complete">Validée</option>
              </select>
            </td>

            <!-- Actions (Chat link) -->
            <td class="px-4 py-2.5 text-right align-middle" @click.stop>
              <div class="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  class="inline-flex items-center gap-1 rounded-md border border-edge bg-surface-raised px-2 py-1 text-[11px] font-medium text-content-secondary hover:bg-accent hover:text-white transition-colors"
                  title="Ouvrir le chat pour cette scène"
                  @click="$emit('open-chat', scene)"
                >
                  <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
                  </svg>
                  <span>Chat</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  scenes: { type: Array, default: () => [] },
  selectedSceneId: { type: Number, default: null },
  sequenceNumber: { type: [Number, String], default: 1 }
})

defineEmits(['select-scene', 'update-scene-status', 'open-chat'])

const isCollapsed = ref(false)

function cleanSummary(scene) {
  const text = scene.description || scene.prompt || ''
  return text
    .replace(/[#*`_~[\]]/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}
</script>
