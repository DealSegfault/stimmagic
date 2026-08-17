<template>
  <div class="relative">
    <button
      ref="buttonRef"
      type="button"
      class="relative flex h-8 w-8 items-center justify-center rounded-full transition-colors text-content-muted hover:text-content-secondary hover:bg-overlay-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
      :class="modelValue ? 'bg-accent/15 text-accent' : ''"
      :disabled="disabled"
      :aria-label="triggerLabel"
      aria-haspopup="dialog"
      :aria-expanded="isOpen"
      :title="triggerLabel"
      @click="toggleOpen"
      @keydown.esc="close"
    >
      <PhotoIcon class="h-4 w-4" aria-hidden="true" />
      <span v-if="modelValue" class="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <!-- Backdrop to close on outside click -->
      <div v-if="isOpen" class="fixed inset-0 z-menu" @click="close" />

      <!-- Popover dialog -->
      <div
        v-if="isOpen"
        class="fixed z-menu w-72 rounded-lg border border-edge bg-surface p-3 shadow-2xl overflow-y-auto flex flex-col"
        :style="popoverPosition"
        role="dialog"
        aria-label="Backend de génération d’images"
        @keydown.esc="close"
      >
        <div class="flex items-start justify-between gap-3 pb-2">
          <div>
            <p class="text-xs font-semibold text-content">Backend image</p>
            <p class="mt-0.5 text-[11px] text-content-muted">Un seul choix actif à la fois.</p>
          </div>
          <button
            type="button"
            class="rounded p-1 text-content-muted hover:bg-overlay-subtle hover:text-content transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            aria-label="Fermer le choix du backend image"
            title="Fermer"
            @click="close"
          >
            <XMarkIcon class="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div class="grid gap-1.5 py-1" role="group" aria-label="Choix du backend image">
          <button
            v-for="option in options"
            :key="option.value"
            type="button"
            :aria-pressed="modelValue === option.value"
            class="flex items-center justify-between gap-2 rounded-md border px-2.5 py-2 text-left text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
            :class="modelValue === option.value
              ? 'border-accent/60 bg-accent/15 text-accent'
              : 'border-edge bg-overlay-subtle text-content-secondary hover:border-edge-strong hover:text-content hover:bg-overlay-light'"
            :title="modelValue === option.value ? `Désactiver ${option.label}` : `Activer ${option.label}`"
            @pointerdown.stop
            @click.stop.prevent="toggle(option.value)"
          >
            <span class="truncate">{{ option.label }}</span>
            <CheckIcon v-if="modelValue === option.value" class="h-4 w-4 flex-shrink-0 text-accent" aria-hidden="true" />
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { PhotoIcon, XMarkIcon, CheckIcon } from '@heroicons/vue/24/outline'

const props = defineProps({
  modelValue: { type: String, default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])
const buttonRef = ref(null)
const isOpen = ref(false)
const popoverPosition = ref({})

const POPOVER_WIDTH = 288 // 72 * 4 = 288px

const options = [
  { value: 'codex_imagegen', label: 'ChatGPT / Codex ImageGen' },
  { value: 'antigravity', label: 'Antigravity' },
]

const triggerLabel = computed(() => props.modelValue
  ? `Backend image : ${options.find(option => option.value === props.modelValue)?.label || props.modelValue}`
  : 'Choisir un backend image')

function updatePosition() {
  if (!buttonRef.value) return
  const rect = buttonRef.value.getBoundingClientRect()
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - POPOVER_WIDTH - 8))
  popoverPosition.value = {
    left: `${left}px`,
    bottom: `${window.innerHeight - rect.top + 8}px`,
    maxHeight: `${Math.max(rect.top - 16, 120)}px`,
  }
}

function toggle(value) {
  emit('update:modelValue', props.modelValue === value ? null : value)
}

function toggleOpen() {
  if (isOpen.value) {
    close()
  } else {
    updatePosition()
    isOpen.value = true
  }
}

function requestGeneration() {
  emit('request-generation')
}

function close() {
  isOpen.value = false
}

function onResize() {
  if (isOpen.value) {
    updatePosition()
  }
}

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
})
</script>
