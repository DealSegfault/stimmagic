<script setup lang="ts">
import MediaImage from '../media/MediaImage.vue'
import type { ProjectElement } from '../../composables/useProjectElementsApi'

withDefaults(defineProps<{
  element: ProjectElement
  active?: boolean
}>(), { active: false })

defineEmits<{ select: [] }>()
</script>

<template>
  <button
    type="button"
    class="inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
    :class="active
      ? 'border-accent/50 bg-accent/12 text-content'
      : 'border-edge-subtle bg-overlay-faint text-content-secondary hover:border-accent/35 hover:bg-overlay-subtle'"
    :aria-expanded="active"
    :aria-label="`${active ? 'Masquer' : 'Afficher'} l’aperçu de ${element.name}`"
    @click="$emit('select')"
  >
    <span class="relative h-6 w-6 shrink-0 overflow-hidden rounded bg-surface">
      <MediaImage
        v-if="element.media_id || element.asset_id || element.file_hash"
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
    </span>
    <span class="min-w-0 truncate">{{ element.name }}</span>
  </button>
</template>
