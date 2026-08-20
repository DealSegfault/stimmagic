<script setup lang="ts">
import MediaImage from '../media/MediaImage.vue'
import type { ProjectElement } from '../../composables/useProjectElementsApi'
import { useMediaDetailsModal } from '../../composables/useMediaDetailsModal'

const props = defineProps<{
  element: ProjectElement
}>()

const mediaDetailsModal = useMediaDetailsModal()

function openDetails() {
  if (props.element.media_id) {
    mediaDetailsModal.open(props.element.media_id)
  }
}
</script>

<template>
  <section
    class="not-prose mt-3 w-full max-w-sm"
    :aria-label="`Aperçu de ${element.name}`"
  >
    <div class="mb-1.5 flex min-w-0 items-baseline gap-2">
      <span class="truncate text-xs font-medium text-content">{{ element.name }}</span>
      <span class="truncate font-mono text-[10px] text-content-muted">@{{ element.reference_id }}</span>
    </div>

    <button
      v-if="element.media_id || element.file_hash"
      type="button"
      class="block aspect-video w-full overflow-hidden rounded-media bg-matte text-left focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
      :aria-label="`Ouvrir les détails de ${element.name}`"
      @click="openDetails"
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
        img-class="h-full w-full object-contain"
      />
    </button>

    <div
      v-else
      class="rounded-md bg-overlay-faint px-3 py-2 text-xs text-content-muted"
      role="status"
    >
      Aucun asset visuel n’est encore associé à cet élément.
    </div>
  </section>
</template>
