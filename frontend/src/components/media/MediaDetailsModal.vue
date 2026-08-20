<template>
  <Modal
    :show="mediaDetails.state.value.visible"
    size="custom"
    custom-class="relative w-[1100px] h-[75vh] flex overflow-hidden"
    :close-on-esc="false"
    @close="mediaDetails.close()"
  >
    <!-- Close -->
    <button
      class="absolute top-3 right-3 z-10 w-8 h-8 flex items-center justify-center rounded-full bg-overlay-strong text-content-tertiary hover:text-content hover:bg-overlay-medium transition-colors"
      @click="mediaDetails.close()"
      title="Close (Esc)"
    >
      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>

    <ImageDetailsCard
      v-if="media"
      :media="media"
      @navigate="navigateTo"
      @open-flow="openFlow"
    />
    <div v-else class="w-full h-full flex items-center justify-center">
      <span class="text-content-tertiary text-sm animate-pulse">{{ error || 'Loading…' }}</span>
    </div>
  </Modal>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMediaDetailsModal } from '../../composables/useMediaDetailsModal'
import { useMediaApi } from '../../composables/useMediaApi'
import { useWebSocket } from '../../composables/useWebSocket'
import ImageDetailsCard from './ImageDetailsCard.vue'
import Modal from '../ui/Modal.vue'

const router = useRouter()
const mediaDetails = useMediaDetailsModal()
const { getMediaItem } = useMediaApi()
const { on: onWsEvent } = useWebSocket()

const media = ref(null)
const error = ref(null)
const currentMediaId = ref(null)
let loadToken = 0
let wsUnsubscribes = []

async function loadMedia(id) {
  media.value = null
  error.value = null
  currentMediaId.value = id
  if (!id) return
  const token = ++loadToken
  try {
    const item = await getMediaItem(id, { includeTrashed: true })
    if (token !== loadToken) return
    media.value = item
  } catch (err) {
    if (token !== loadToken) return
    error.value = err?.response?.status === 404 ? 'Media item not found' : 'Failed to load details'
  }
}

function navigateTo(id) {
  loadMedia(id)
}

function openFlow(flowId) {
  mediaDetails.close()
  router.push({ name: 'flow', params: { id: String(flowId) } })
}

function eventTargetsCurrentMedia(data) {
  if (!media.value && !currentMediaId.value) return false
  const mediaIds = new Set(data?.media_ids || (data?.media_id ? [data.media_id] : []))
  const assetIds = new Set(data?.asset_ids || (data?.asset_id ? [data.asset_id] : []))
  return mediaIds.has(Number(currentMediaId.value)) || (media.value?.asset_id && assetIds.has(Number(media.value.asset_id)))
}

function closeWhenAssetLifecycleChanges(data) {
  if (eventTargetsCurrentMedia(data)) mediaDetails.close()
}

watch(
  () => mediaDetails.state.value.visible ? mediaDetails.state.value.mediaId : null,
  (id) => {
    if (id) loadMedia(id)
    else { media.value = null; error.value = null; currentMediaId.value = null }
  },
  { immediate: true }
)

function handleKeydown(e) {
  if (!mediaDetails.state.value.visible) return
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    mediaDetails.close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown, true)
  for (const event of ['asset_trashed', 'asset_deleted', 'assets_trashed', 'asset_identity_deleted', 'media_deleted', 'media_bulk_deleted', 'media_permanently_deleted']) {
    wsUnsubscribes.push(onWsEvent(event, closeWhenAssetLifecycleChanges))
  }
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown, true)
  wsUnsubscribes.forEach((unsubscribe) => unsubscribe())
  wsUnsubscribes = []
})
</script>
