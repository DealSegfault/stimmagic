<template>
  <div class="border-b border-edge-subtle bg-surface px-6 py-3">
    <!-- Top row: Scene navigation, title & quick actions -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <!-- Left: Scene identity & Stepper -->
      <div class="flex min-w-0 items-center gap-3">
        <!-- Sequence badge -->
        <span class="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-accent/15 font-mono text-xs font-bold text-accent">
          S{{ currentScene?.scene_number ? String(currentScene.scene_number).padStart(2, '0') : '01' }}
        </span>

        <!-- Scene selector / Dropdown -->
        <div class="relative min-w-0">
          <div class="flex items-center gap-2">
            <select
              v-if="scenes.length > 1"
              :value="currentScene?.id"
              class="cursor-pointer appearance-none rounded-lg border border-edge-subtle bg-surface-raised py-1 pl-2.5 pr-8 text-sm font-semibold text-content outline-none transition-colors hover:border-edge focus:border-accent"
              @change="onSceneSelect($event.target.value)"
            >
              <option
                v-for="scene in scenes"
                :key="scene.id"
                :value="scene.id"
              >
                S{{ scene.scene_number ? String(scene.scene_number).padStart(2, '0') : '01' }} · {{ scene.title }}
              </option>
            </select>
            <h1 v-else class="truncate text-base font-bold text-content">
              {{ currentScene?.title || boardName || 'Scène' }}
            </h1>

            <svg
              v-if="scenes.length > 1"
              class="pointer-events-none -ml-7 h-4 w-4 text-content-muted"
              fill="none"
              viewBox="0 0 24 24"
              stroke-width="2"
              stroke="currentColor"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </div>
        </div>

        <!-- Prev / Next Scene Steppers -->
        <div v-if="scenes.length > 1" class="flex items-center gap-1">
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-md border border-edge-subtle bg-surface-raised text-content-muted transition-colors hover:bg-overlay-light hover:text-content disabled:cursor-not-allowed disabled:opacity-30"
            :disabled="!hasPreviousScene"
            title="Scène précédente"
            @click="goToPreviousScene"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
            </svg>
          </button>
          <button
            type="button"
            class="flex h-7 w-7 items-center justify-center rounded-md border border-edge-subtle bg-surface-raised text-content-muted transition-colors hover:bg-overlay-light hover:text-content disabled:cursor-not-allowed disabled:opacity-30"
            :disabled="!hasNextScene"
            title="Scène suivante"
            @click="goToNextScene"
          >
            <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        </div>

        <!-- Status Pill -->
        <div v-if="currentScene" class="hidden sm:flex items-center gap-1.5">
          <span
            class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border"
            :class="statusBadgeClass(currentScene.status)"
          >
            <span class="h-1.5 w-1.5 rounded-full" :class="statusDotClass(currentScene.status)" />
            {{ statusLabel(currentScene.status) }}
          </span>
        </div>
      </div>

      <!-- Right: Direct action buttons -->
      <div class="flex items-center gap-2 flex-shrink-0">
        <!-- Brief / Prompt Toggle Button -->
        <button
          v-if="currentScene"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-surface-raised px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
          :class="briefOpen ? 'border-accent/40 bg-accent/10 text-accent' : ''"
          @click="$emit('toggle-brief')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
          </svg>
          <span>Brief & Script</span>
        </button>

        <!-- Scene Chat Button -->
        <button
          v-if="currentScene"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-1.5 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors disabled:opacity-50"
          :disabled="chatOpening"
          @click="$emit('open-chat')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
          </svg>
          <span>{{ chatOpening ? 'Ouverture…' : 'Chat de scène' }}</span>
        </button>

        <!-- Actions Menu Trigger -->
        <slot name="menu-action" />
      </div>
    </div>

    <!-- Bottom row: Studio View Tabs -->
    <div class="mt-3 flex items-center justify-between border-t border-edge-subtle/70 pt-2.5">
      <nav class="flex items-center gap-1.5" aria-label="Onglets Studio">
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          :class="activeTab === 'board'
            ? 'bg-accent/15 text-accent font-semibold'
            : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          @click="$emit('update:active-tab', 'board')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z" />
          </svg>
          <span>Board & Références</span>
          <span v-if="assetCount > 0" class="rounded-full bg-overlay-subtle px-1.5 py-0.2 font-mono text-[10px] text-content-tertiary">
            {{ assetCount }}
          </span>
        </button>

        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          :class="activeTab === 'generations'
            ? 'bg-accent/15 text-accent font-semibold'
            : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          @click="$emit('update:active-tab', 'generations')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
          </svg>
          <span>Vidéos & Générations</span>
          <span v-if="generationCount > 0" class="rounded-full bg-accent/20 px-1.5 py-0.2 font-mono text-[10px] font-semibold text-accent">
            {{ generationCount }}
          </span>
        </button>

        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          :class="activeTab === 'continuity'
            ? 'bg-accent/15 text-accent font-semibold'
            : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          @click="$emit('update:active-tab', 'continuity')"
        >
          <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
          </svg>
          <span>Raccord de continuité</span>
        </button>
      </nav>

      <!-- Quick hint / stats -->
      <div class="hidden sm:flex items-center gap-3 text-[11px] text-content-tertiary">
        <span v-if="currentScene?.sequence_number">Séquence {{ currentScene.sequence_number }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  boardName: { type: String, default: '' },
  scenes: { type: Array, default: () => [] },
  currentSceneId: { type: Number, default: null },
  activeTab: { type: String, default: 'board' },
  assetCount: { type: Number, default: 0 },
  generationCount: { type: Number, default: 0 },
  briefOpen: { type: Boolean, default: false },
  chatOpening: { type: Boolean, default: false }
})

const emit = defineEmits(['select-scene', 'update:active-tab', 'toggle-brief', 'open-chat'])

const currentSceneIndex = computed(() => {
  if (!props.scenes.length || !props.currentSceneId) return 0
  const index = props.scenes.findIndex((s) => s.id === props.currentSceneId)
  return index >= 0 ? index : 0
})

const currentScene = computed(() => {
  if (!props.scenes.length) return null
  return props.scenes[currentSceneIndex.value] || props.scenes[0]
})

const hasPreviousScene = computed(() => currentSceneIndex.value > 0)
const hasNextScene = computed(() => currentSceneIndex.value < props.scenes.length - 1)

function onSceneSelect(sceneId) {
  emit('select-scene', Number(sceneId))
}

function goToPreviousScene() {
  if (hasPreviousScene.value) {
    const prevScene = props.scenes[currentSceneIndex.value - 1]
    if (prevScene) emit('select-scene', prevScene.id)
  }
}

function goToNextScene() {
  if (hasNextScene.value) {
    const nextScene = props.scenes[currentSceneIndex.value + 1]
    if (nextScene) emit('select-scene', nextScene.id)
  }
}

function statusLabel(status) {
  return {
    planned: 'Planifiée',
    in_progress: 'En cours',
    ready_for_review: 'À valider',
    complete: 'Validée',
    blocked: 'Bloquée'
  }[status] || status || 'Planifiée'
}

function statusBadgeClass(status) {
  if (status === 'complete') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
  if (status === 'in_progress') return 'border-blue-500/30 bg-blue-500/10 text-blue-400'
  if (status === 'ready_for_review') return 'border-purple-500/30 bg-purple-500/10 text-purple-400'
  if (status === 'blocked') return 'border-amber-500/30 bg-amber-500/10 text-amber-500'
  return 'border-edge bg-surface-raised text-content-secondary'
}

function statusDotClass(status) {
  if (status === 'complete') return 'bg-emerald-400'
  if (status === 'in_progress') return 'bg-blue-400'
  if (status === 'ready_for_review') return 'bg-purple-400'
  if (status === 'blocked') return 'bg-amber-400'
  return 'bg-content-muted'
}
</script>
