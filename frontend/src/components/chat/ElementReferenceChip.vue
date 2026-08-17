<script setup lang="ts">
import MediaImage from '../media/MediaImage.vue'
import type { ProjectElement } from '../../composables/useProjectElementsApi'
import { useMediaDetailsModal } from '../../composables/useMediaDetailsModal'

const props = withDefaults(defineProps<{
  element: ProjectElement
  removable?: boolean
  compact?: boolean
}>(), {
  removable: false,
  compact: false,
})

defineEmits<{ remove: [] }>()

const mediaDetailsModal = useMediaDetailsModal()

function openImage(event: MouseEvent) {
  event.stopPropagation()
  if (props.element.media_id) {
    mediaDetailsModal.open(props.element.media_id)
  }
}
</script>

<template>
  <div
    class="group inline-flex max-w-full items-center gap-2 rounded-md border border-edge bg-surface-raised p-1.5 text-left"
    :class="compact ? 'pr-2' : 'pr-3'"
  >
    <button
      v-if="element.media_id || element.file_hash"
      type="button"
      class="relative h-9 w-9 shrink-0 overflow-hidden rounded bg-surface p-0 border-0 text-left focus:outline-none"
      :class="element.media_id ? 'cursor-pointer hover:ring-1 hover:ring-accent transition-all' : 'cursor-default'"
      :title="element.media_id ? `Voir ${element.name}` : undefined"
      :disabled="!element.media_id"
      @click="openImage"
    >
      <MediaImage
        :media-id="element.media_id || undefined"
        :asset-id="element.asset_id || undefined"
        :file-hash="element.file_hash || undefined"
        :file-format="element.file_format || undefined"
        :alt="element.name"
        :enable-context-menu="false"
        :draggable="false"
        container-class="h-full w-full"
        img-class="h-full w-full object-cover"
      />
    </button>
    <div class="min-w-0">
      <div v-if="!compact" class="text-[10px] uppercase tracking-wide text-content-muted">
        {{ element.element_type }}
      </div>
      <div class="truncate text-xs font-medium text-content">
        @{{ element.reference_id }}
      </div>
    </div>
    <button
      v-if="removable"
      type="button"
      class="ml-1 flex h-6 w-6 shrink-0 items-center justify-center rounded text-content-muted hover:bg-overlay-subtle hover:text-content"
      :aria-label="`Remove @${element.reference_id}`"
      @click="$emit('remove')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="h-3.5 w-3.5" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18" stroke-width="1.8" stroke-linecap="round" />
      </svg>
    </button>
  </div>
</template>
