<script setup lang="ts">
/**
 * The base of the stack, as the last row in the Edits list.
 *
 * The list is ordered the way the image is built — top of the stack reads
 * first — so the image every edit applies to belongs at the BOTTOM, as the row
 * everything above it sits on. It is a row and not a caption because it is
 * genuinely the first entry in the order; it just isn't a step, so it carries
 * none of a step's affordances: no eye (hiding the thing being edited means
 * nothing), no drag grip, no remove.
 *
 * It obeys the Edits list's layout law (see rowLayout.ts and EditRow): same
 * grip column, same square, same centering — that shared column is what makes
 * the list read as one structure rather than a row and a caption.
 */
import MediaImage from '../../components/media/MediaImage.vue'
import { ROW_SQUARE, ROW_COLUMN } from './rowLayout'

defineProps<{
  mediaId: number
  width?: number
  height?: number
}>()
</script>

<template>
  <div class="flex items-start gap-1.5 px-2 py-2 rounded-md cursor-default">
    <!-- Grip column: reserved at the grip's exact width, never filled. The
         base does not reorder, but the squares below and above it must line
         up, so the column is held open. -->
    <span class="w-2.5 shrink-0" aria-hidden="true" />

    <MediaImage
      :media-id="mediaId"
      thumbnail
      :thumbnail-size="128"
      :draggable="false"
      :enable-context-menu="false"
      :container-class="ROW_SQUARE"
      img-class="w-full h-full object-cover"
    />

    <div :class="['min-w-0 flex-1', ROW_COLUMN]">
      <span class="text-sm text-content-tertiary">Original image</span>
      <p v-if="width && height" class="text-xs text-content-tertiary/70">
        {{ width }} × {{ height }}
      </p>
    </div>
  </div>
</template>
