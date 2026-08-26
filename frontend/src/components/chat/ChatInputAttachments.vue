<template>
  <div v-if="attachments.length > 0" class="chat-attachments flex gap-2 p-2 bg-surface/50 border-b border-edge">
    <div
      v-for="(attachment, index) in attachments"
      :key="attachment.id || index"
      class="relative w-16 h-16 bg-matte rounded-media overflow-hidden group flex-shrink-0"
    >
      <!-- Library media (has media_id) - draggable with context menu -->
      <button
        v-if="attachment.media_id"
        type="button"
        class="w-full h-full p-0 border-0 bg-transparent text-left cursor-pointer focus:outline-none hover:ring-1 hover:ring-accent transition-all"
        :title="attachmentTitle(attachment)"
        @click="mediaDetailsModal.open(attachment.media_id)"
      >
        <MediaImage
          :media-id="attachment.media_id"
          :thumbnail="true"
          :thumbnail-size="128"
          :is-audio="isAudioAttachment(attachment)"
          container-class="w-full h-full"
        />
      </button>
      <!-- Uploaded video reference preview. Library-backed media keeps the
           thumbnail above, while path-only attachments can still preview the
           actual clip without routing it through <img>. -->
      <video
        v-if="!attachment.media_id && isVideoAttachment(attachment)"
        :src="getAttachmentUrl(attachment)"
        class="w-full h-full object-cover"
        muted
        playsinline
        preload="metadata"
      />
      <!-- Reference file or blob URL - not draggable -->
      <AppImage
        v-else-if="!attachment.media_id"
        :src="getAttachmentUrl(attachment)"
        :alt="`Attachment ${index + 1}`"
        container-class="w-full h-full"
      />
      <!-- Remove button -->
      <button
        @click.stop="removeAttachment(index)"
        class="absolute top-0.5 right-0.5 w-5 h-5 bg-black/55 backdrop-blur-sm hover:bg-red-500 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-colors z-10 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-content">
          <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { MediaImage, AppImage } from '../media'
import { getApiBase } from '../../apiConfig'
import { getCurrentProfileId } from '../../composables/useProfile'
import { getCachedPin } from '../../composables/usePinLock'
import { useMediaDetailsModal } from '../../composables/useMediaDetailsModal'

const props = defineProps({
  attachments: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['remove'])
const mediaDetailsModal = useMediaDetailsModal()

function getAttachmentUrl(attachment) {
  // If it's an uploaded file with a path
  if (attachment.path) {
    const profileId = getCurrentProfileId()
    const pin = getCachedPin(profileId)
    const endpoint = isVideoAttachment(attachment)
      ? 'reference-video-file'
      : isAudioAttachment(attachment)
        ? 'reference-audio-file'
        : 'reference-file'
    let url = `${getApiBase()}/generate/${endpoint}?path=${encodeURIComponent(attachment.path)}&profile=${encodeURIComponent(profileId)}`
    if (pin) url += `&pin=${encodeURIComponent(pin)}`
    return url
  }
  // If it has a local blob URL (during upload)
  if (attachment.localUrl) {
    return attachment.localUrl
  }
  return ''
}

function isVideoAttachment(attachment) {
  if (attachment?.media_type === 'video') return true
  const format = attachment?.file_format || attachment?.filename || attachment?.path || ''
  return /\.(mp4|mov|avi|mkv|webm|m4v|mpg|mpeg)$/i.test(String(format))
}

function isAudioAttachment(attachment) {
  if (attachment?.media_type === 'audio') return true
  const format = attachment?.file_format || attachment?.filename || attachment?.path || ''
  return /\.(mp3|wav|flac|aac|m4a|ogg)$/i.test(String(format))
}

function attachmentTitle(attachment) {
  if (isVideoAttachment(attachment)) return 'Voir la vidéo'
  if (isAudioAttachment(attachment)) return "Voir l'audio"
  return "Voir l'image"
}

function removeAttachment(index) {
  emit('remove', index)
}
</script>
