<script setup lang="ts">
import MediaImage from '../media/MediaImage.vue'
import type { ProjectElement } from '../../composables/useProjectElementsApi'

defineProps<{
  elements: ProjectElement[]
  activeIndex: number
}>()

defineEmits<{ select: [element: ProjectElement] }>()
</script>

<template>
  <div
    v-if="elements.length"
    class="absolute bottom-full left-3 z-menu mb-2 w-[min(420px,calc(100%-1.5rem))] overflow-hidden rounded-lg border border-edge bg-surface shadow-2xl"
    role="listbox"
    aria-label="Project elements"
  >
    <div class="border-b border-edge-subtle px-3 py-2 text-xs font-medium text-content-secondary">
      Elements
    </div>
    <div class="max-h-64 overflow-y-auto p-1.5">
      <button
        v-for="(element, index) in elements"
        :key="element.reference_id"
        type="button"
        role="option"
        :aria-selected="index === activeIndex"
        class="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors"
        :class="index === activeIndex ? 'bg-overlay-subtle' : 'hover:bg-overlay-subtle'"
        @mousedown.prevent="$emit('select', element)"
      >
        <MediaImage
          :media-id="element.media_id || undefined"
          :asset-id="element.asset_id || undefined"
          :file-hash="element.file_hash || undefined"
          :file-format="element.file_format || undefined"
          :alt="element.name"
          :enable-context-menu="false"
          :draggable="false"
          container-class="h-10 w-10 shrink-0 overflow-hidden rounded-md bg-surface-raised"
          img-class="h-full w-full object-cover"
        />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-sm font-medium text-content">{{ element.name }}</span>
          <span class="block truncate text-xs text-content-muted">@{{ element.reference_id }}</span>
        </span>
        <span class="rounded bg-overlay-subtle px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-content-muted">
          {{ element.element_type }}
        </span>
      </button>
    </div>
  </div>
</template>
