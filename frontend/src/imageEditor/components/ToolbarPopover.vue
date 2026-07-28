<script setup lang="ts">
/**
 * A panel hanging off a toolbar chip.
 *
 * Properties that stay mutable live in the Edits inspector; properties that
 * are consumed at the moment of the gesture — which brush, which colour — do
 * not belong to any step, so they hang off the toolbar instead, the way
 * Photoshop does it.
 */
import { ref, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'

withDefaults(defineProps<{ label: string; width?: number }>(), { width: 248 })

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)

/**
 * Which edge the panel hangs from.
 *
 * A toolbar trigger has the whole window to its right; the same control inside
 * the properties panel is a handful of pixels from the screen edge, and a
 * left-aligned panel there opens mostly off-screen. Measured rather than
 * assumed, because the answer changes with the sidebar width.
 */
const alignRight = ref(false)

watch(open, async isOpen => {
  if (!isOpen) return
  alignRight.value = false
  await nextTick()
  const rect = panel.value?.getBoundingClientRect()
  if (rect && rect.right > window.innerWidth - 8) alignRight.value = true
})

function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return
  if (!root.value?.contains(event.target as Node)) open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown, true)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md transition-colors"
      :class="open
        ? 'bg-selection/15 text-content'
        : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
      :aria-expanded="open"
      @click="open = !open"
    >
      <slot name="trigger" />
      <span>{{ label }}</span>
      <svg viewBox="0 0 24 24" class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2">
        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <div
      v-if="open"
      ref="panel"
      class="popover-panel absolute top-full mt-1.5 z-30 rounded-lg
             border border-edge-subtle bg-surface shadow-xl p-3"
      :class="alignRight ? 'right-0' : 'left-0'"
      :style="{ width: width + 'px' }"
    >
      <slot />
    </div>
  </div>
</template>

<style scoped>
/*
 * The ported pickers carry their own stylesheets, written against the snapshot
 * editor's variable names. Those names alias app tokens one-for-one, so the
 * panel just republishes them rather than the pickers being rewritten.
 */
.popover-panel {
  --stimma-color-background: var(--color-surface-rgb);
  --stimma-color-foreground: var(--color-text-primary-rgb);
  --stimma-color-primary: var(--color-accent-rgb);
  --stimma-border-radius: var(--radius-md, 6px);
  --stimma-border-radius-sm: var(--radius-sm, 4px);
  --stimma-border-radius-lg: var(--radius-lg, 8px);
  --stimma-border-radius-round: 9999px;
}
</style>
