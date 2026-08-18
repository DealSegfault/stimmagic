<template>
  <div class="relative">
    <button
      ref="buttonRef"
      type="button"
      class="relative flex h-8 w-8 items-center justify-center rounded-full text-content-muted transition-colors hover:bg-overlay-subtle hover:text-content-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
      :class="hasCustomSettings ? 'bg-accent/15 text-accent' : ''"
      :disabled="disabled"
      :aria-label="triggerLabel"
      aria-haspopup="dialog"
      :aria-expanded="isOpen"
      :title="triggerLabel"
      @click="toggleOpen"
      @keydown.esc="close"
    >
      <AdjustmentsHorizontalIcon class="h-4 w-4" aria-hidden="true" />
      <span v-if="hasCustomSettings" class="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <div v-if="isOpen" class="fixed inset-0 z-menu" aria-hidden="true" @click="close" />

      <div
        v-if="isOpen"
        class="fixed z-menu w-72 max-w-[calc(100vw-1rem)] overflow-y-auto rounded-lg border border-edge bg-surface p-3 shadow-2xl"
        :style="popoverPosition"
        role="dialog"
        aria-label="Réglages vidéo MiniMax H3"
        @keydown.esc="close"
      >
        <div class="flex items-start justify-between gap-3 pb-2">
          <div>
            <p class="text-xs font-semibold text-content">Réglages vidéo</p>
            <p class="mt-0.5 text-[11px] text-content-muted">MiniMax H3 · préférences de ce chat</p>
          </div>
          <button
            type="button"
            class="rounded p-1 text-content-muted transition-colors hover:bg-overlay-subtle hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            aria-label="Fermer les réglages vidéo"
            title="Fermer"
            @click="close"
          >
            <XMarkIcon class="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div class="space-y-3 pt-1">
          <label class="block">
            <span class="mb-1 flex items-center justify-between text-[11px] font-medium text-content-secondary">
              <span>Steps</span>
              <span class="text-content-muted">{{ effectiveSteps }}</span>
            </span>
            <select
              :value="effectiveSteps"
              :disabled="fast || disabled"
              aria-label="Nombre de steps vidéo"
              class="w-full rounded-md border border-edge bg-surface-raised px-2.5 py-2 text-xs text-content outline-none transition-colors focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
              @change="emit('update:steps', Number($event.target.value))"
            >
              <option v-for="option in STEP_OPTIONS" :key="option" :value="option">{{ option }} steps</option>
            </select>
            <span v-if="fast" class="mt-1 block text-[10px] text-accent">Fast impose automatiquement 8 steps.</span>
          </label>

          <label class="block">
            <span class="mb-1 block text-[11px] font-medium text-content-secondary">Résolution</span>
            <select
              :value="resolution"
              :disabled="disabled"
              aria-label="Résolution vidéo"
              class="w-full rounded-md border border-edge bg-surface-raised px-2.5 py-2 text-xs text-content outline-none transition-colors focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
              @change="emit('update:resolution', $event.target.value)"
            >
              <option v-for="option in RESOLUTION_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
            <span class="mt-1 block text-[10px] text-content-muted">Le modèle peut limiter la taille au canvas H3 pris en charge.</span>
          </label>

          <label class="block">
            <span class="mb-1 block text-[11px] font-medium text-content-secondary">Durée</span>
            <select
              :value="duration"
              :disabled="disabled"
              aria-label="Durée vidéo"
              class="w-full rounded-md border border-edge bg-surface-raised px-2.5 py-2 text-xs text-content outline-none transition-colors focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
              @change="emit('update:duration', Number($event.target.value))"
            >
              <option v-for="option in DURATION_OPTIONS" :key="option" :value="option">{{ option }} secondes</option>
            </select>
          </label>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { AdjustmentsHorizontalIcon, XMarkIcon } from '@heroicons/vue/24/outline'

const props = defineProps({
  steps: { type: Number, default: 20 },
  resolution: { type: String, default: '720' },
  duration: { type: Number, default: 5 },
  fast: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:steps', 'update:resolution', 'update:duration'])
const buttonRef = ref(null)
const isOpen = ref(false)
const popoverPosition = ref({})

const STEP_OPTIONS = [4, 8, 12, 16, 20, 24, 30, 40, 50]
const RESOLUTION_OPTIONS = [
  { value: '480', label: '480p' },
  { value: '720', label: '720p' },
  { value: '1080', label: '1080p' },
  { value: '2k', label: '2K' },
]
const DURATION_OPTIONS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15]

const effectiveSteps = computed(() => props.fast ? 8 : props.steps)
const hasCustomSettings = computed(() => (
  props.steps !== 20 || props.resolution !== '720' || props.duration !== 5 || props.fast
))
const triggerLabel = computed(() => (
  `Réglages vidéo : ${effectiveSteps.value} steps, ${props.resolution === '2k' ? '2K' : `${props.resolution}p`}, ${props.duration}s`
))

function updatePosition() {
  if (!buttonRef.value) return
  const rect = buttonRef.value.getBoundingClientRect()
  const width = 288
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))
  popoverPosition.value = {
    left: `${left}px`,
    bottom: `${window.innerHeight - rect.top + 8}px`,
    maxHeight: `${Math.max(rect.top - 16, 120)}px`,
  }
}

function toggleOpen() {
  if (isOpen.value) {
    close()
  } else {
    updatePosition()
    isOpen.value = true
  }
}

function close() {
  isOpen.value = false
}

function onResize() {
  if (isOpen.value) updatePosition()
}

onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>
