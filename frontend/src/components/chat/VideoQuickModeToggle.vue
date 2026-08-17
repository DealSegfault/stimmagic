<template>
  <button
    type="button"
    class="relative flex h-8 w-8 items-center justify-center rounded-full text-sm text-content-muted transition-colors hover:bg-overlay-subtle hover:text-content-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50"
    :class="modelValue ? 'bg-accent/15 text-accent' : ''"
    :disabled="disabled"
    :aria-pressed="modelValue"
    :aria-label="label"
    :title="label"
    @click="toggle"
  >
    <span aria-hidden="true">⚡</span>
    <span v-if="modelValue" class="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
  </button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const label = computed(() => props.modelValue
  ? 'Mode vidéo rapide : activé — MiniMax H3 ⚡'
  : 'Mode vidéo rapide : désactivé — MiniMax H3 standard')

function toggle() {
  emit('update:modelValue', !props.modelValue)
}
</script>
