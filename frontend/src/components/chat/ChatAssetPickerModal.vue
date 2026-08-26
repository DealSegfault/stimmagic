<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import Modal from '../ui/Modal.vue'
import Button from '../ui/Button.vue'
import Spinner from '../ui/Spinner.vue'
import MediaImage from '../media/MediaImage.vue'
import { getApiBase } from '../../apiConfig'
import { useAssetApi, type AssetBrowserItem } from '../../composables/useAssetApi'

type AssetFilter = 'all' | 'image' | 'video' | 'audio'

const props = withDefaults(defineProps<{
  show: boolean
  excludeIds?: number[]
}>(), {
  excludeIds: () => [],
})

const emit = defineEmits<{
  close: []
  select: [assets: Partial<AssetBrowserItem>[]]
}>()

const { fetchAssets } = useAssetApi()

const filter = ref<AssetFilter>('all')
const assets = ref<AssetBrowserItem[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const selectedAssets = ref<Partial<AssetBrowserItem>[]>([])
const uploadInput = ref<HTMLInputElement | null>(null)

const mediaTypes = computed(() => {
  if (filter.value === 'image') return 'images'
  if (filter.value === 'video') return 'videos'
  if (filter.value === 'audio') return 'audio'
  return 'images,videos,audio'
})

const visibleAssets = computed(() => {
  const excluded = new Set(props.excludeIds)
  return assets.value.filter((asset) => !excluded.has(asset.media_id))
})

const canAdd = computed(() => selectedAssets.value.length > 0 && !loading.value)
const addButtonLabel = computed(() => {
  const count = selectedAssets.value.length
  if (count === 0) return 'Add to chat'
  return `Add ${count} ${count === 1 ? 'Asset' : 'Assets'} to chat`
})

function isSelected(asset: Partial<AssetBrowserItem>) {
  return selectedAssets.value.some((selected) => selected.media_id === asset.media_id)
}

function selectionOrder(asset: Partial<AssetBrowserItem>) {
  return selectedAssets.value.findIndex((selected) => selected.media_id === asset.media_id) + 1
}

function assetSelectionLabel(asset: AssetBrowserItem) {
  const name = asset.asset_title || `Asset ${asset.asset_id}`
  return `${isSelected(asset) ? 'Remove' : 'Add'} ${name} ${isSelected(asset) ? 'from selection' : 'to selection'}`
}

function selectedAssetLabel(asset: Partial<AssetBrowserItem>) {
  return `Remove ${asset.asset_title || `Asset ${asset.asset_id}`} from selection`
}

function isVideoFormat(fileFormat?: string | null) {
  const normalized = (fileFormat || '').toLowerCase().replace(/^\./, '')
  return ['mp4', 'webm', 'mov', 'avi', 'mkv', 'm4v', 'mpg', 'mpeg'].includes(normalized)
}

function isAudioFormat(fileFormat?: string | null) {
  const normalized = (fileFormat || '').toLowerCase().replace(/^\./, '')
  return ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg'].includes(normalized)
}

function reset() {
  page.value = 1
  total.value = 0
  assets.value = []
  selectedAssets.value = []
  error.value = ''
}

async function loadAssets(resetList = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  if (resetList) {
    page.value = 1
    assets.value = []
  }

  try {
    const result = await fetchAssets({
      page: page.value,
      page_size: 48,
      media_types: mediaTypes.value,
      sort_by: 'created_desc',
    })
    assets.value = resetList ? result.items : [...assets.value, ...result.items]
    total.value = result.total
    page.value += 1
  } catch (cause) {
    console.error('Failed to load chat Assets:', cause)
    error.value = 'Unable to load your Assets.'
  } finally {
    loading.value = false
  }
}

function selectAsset(asset: AssetBrowserItem) {
  const existingIndex = selectedAssets.value.findIndex((selected) => selected.media_id === asset.media_id)
  if (existingIndex >= 0) {
    selectedAssets.value = selectedAssets.value.filter((_, index) => index !== existingIndex)
    return
  }
  selectedAssets.value = [...selectedAssets.value, asset]
}

function removeSelectedAsset(mediaId?: number) {
  if (mediaId == null) return
  selectedAssets.value = selectedAssets.value.filter((asset) => asset.media_id !== mediaId)
}

function openUpload() {
  uploadInput.value?.click()
}

async function uploadExternal(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  const isVideo = file.type.startsWith('video/') || isVideoFormat(file.name.split('.').pop())
  const isAudio = file.type.startsWith('audio/') || isAudioFormat(file.name.split('.').pop())
  const isImage = file.type.startsWith('image/')
  if (!isImage && !isVideo && !isAudio) {
    error.value = 'Choose an image, video, or audio file.'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const body = new FormData()
    body.append('file', file)
    const endpoint = isVideo
      ? '/generate/upload-reference-video'
      : isAudio
        ? '/generate/upload-reference-audio'
        : '/generate/upload-reference'
    const response = await axios.post(`${getApiBase()}${endpoint}`, body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const fileFormat = (response.data.file_format || file.name.split('.').pop() || (isVideo ? 'mp4' : isAudio ? 'wav' : 'png')).toLowerCase()
    const uploadedAsset = {
      asset_id: response.data.asset_id,
      media_id: response.data.media_id,
      file_hash: response.data.file_hash,
      file_format: fileFormat,
      asset_title: file.name,
    }
    selectedAssets.value = [
      ...selectedAssets.value.filter((asset) => asset.media_id !== uploadedAsset.media_id),
      uploadedAsset,
    ]
  } catch (cause) {
    console.error('Failed to upload chat Asset:', cause)
    error.value = 'Unable to upload this file.'
  } finally {
    loading.value = false
  }
}

function confirmSelection() {
  if (!canAdd.value) return
  emit('select', [...selectedAssets.value])
}

watch(() => props.show, (show) => {
  if (show) {
    reset()
    void loadAssets(true)
  }
})

watch(filter, () => {
  if (props.show) void loadAssets(true)
})
</script>

<template>
  <Modal
    :show="show"
    size="custom"
    custom-class="w-[960px] max-w-[calc(100vw-2rem)] h-[min(720px,calc(100vh-2rem))] flex flex-col overflow-hidden"
    @close="emit('close')"
  >
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <div class="min-w-0">
          <h2 class="text-base font-semibold text-content">Add to chat</h2>
          <p class="text-xs text-content-muted">Select one or more Assets from your library, or upload a new image, video, or audio file.</p>
        </div>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-md text-content-muted hover:bg-overlay-subtle hover:text-content"
          aria-label="Close"
          @click="emit('close')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </template>

    <div class="flex min-h-0 flex-1 flex-col">
      <div class="flex flex-wrap items-center gap-2 border-b border-edge px-5 py-3">
        <button
          v-for="option in [
            { value: 'all', label: 'All' },
            { value: 'image', label: 'Images' },
            { value: 'video', label: 'Videos' },
            { value: 'audio', label: 'Audio' },
          ]"
          :key="option.value"
          type="button"
          :aria-pressed="filter === option.value"
          class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
          :class="filter === option.value ? 'bg-content text-surface' : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          @click="filter = option.value as AssetFilter"
        >
          {{ option.label }}
        </button>
        <div class="ml-auto">
          <Button variant="secondary" size="sm" :disabled="loading" @click="openUpload">
            Upload file
          </Button>
          <input
            ref="uploadInput"
            type="file"
            accept="image/*,video/*,audio/*"
            class="hidden"
            @change="uploadExternal"
          />
        </div>
      </div>

      <div class="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_260px]">
        <section class="min-h-0 overflow-y-auto p-5">
          <div v-if="loading && assets.length === 0" class="flex h-full min-h-48 items-center justify-center">
            <Spinner />
          </div>
          <div v-else-if="visibleAssets.length === 0" class="flex h-full min-h-48 flex-col items-center justify-center gap-2 text-center">
            <p class="text-sm text-content-secondary">No Assets in this view.</p>
            <p class="text-xs text-content-muted">Upload a file to add one to your library.</p>
          </div>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <button
              v-for="asset in visibleAssets"
              :key="asset.asset_id"
              type="button"
              :aria-pressed="isSelected(asset)"
              :aria-label="assetSelectionLabel(asset)"
              class="group overflow-hidden rounded-md border bg-surface-raised text-left transition-colors"
              :class="isSelected(asset) ? 'border-accent ring-1 ring-accent' : 'border-edge hover:border-content-muted'"
              @click="selectAsset(asset)"
            >
              <div class="relative">
                <MediaImage
                  :media-id="asset.media_id"
                  :asset-id="asset.asset_id"
                  :file-hash="asset.file_hash"
                  :file-format="asset.file_format"
                  :is-video="isVideoFormat(asset.file_format)"
                  :is-audio="isAudioFormat(asset.file_format)"
                  :alt="asset.asset_title || 'Asset'"
                  :enable-context-menu="false"
                  :draggable="false"
                  container-class="aspect-square w-full bg-surface"
                  img-class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
                />
                <span
                  v-if="isSelected(asset)"
                  class="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white shadow-sm"
                  aria-hidden="true"
                >
                  {{ selectionOrder(asset) }}
                </span>
              </div>
              <span class="block truncate px-2 py-1.5 text-xs text-content-secondary">
                {{ asset.asset_title || `Asset ${asset.asset_id}` }}
              </span>
            </button>
          </div>

          <div v-if="error" class="mt-4 text-xs text-red-400">{{ error }}</div>
          <div class="flex justify-center py-5">
            <Spinner v-if="loading && assets.length > 0" />
            <Button
              v-else-if="assets.length < total"
              variant="secondary"
              size="sm"
              @click="loadAssets(false)"
            >
              Load more
            </Button>
          </div>
        </section>

        <aside class="min-h-0 overflow-y-auto border-t border-edge p-5 md:border-l md:border-t-0">
          <div v-if="selectedAssets.length > 0" class="space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs font-medium text-content-secondary">Selected Assets</p>
              <span class="text-xs tabular-nums text-content-muted">{{ selectedAssets.length }}</span>
            </div>
            <ul class="space-y-2" aria-label="Selected Assets">
              <li
                v-for="(asset, index) in selectedAssets"
                :key="asset.media_id || asset.asset_id || index"
                class="flex items-center gap-2 rounded-md border border-edge bg-surface-raised p-1.5"
              >
                <MediaImage
                  :media-id="asset.media_id"
                  :asset-id="asset.asset_id"
                  :file-hash="asset.file_hash"
                  :file-format="asset.file_format"
                  :is-video="isVideoFormat(asset.file_format)"
                  :is-audio="isAudioFormat(asset.file_format)"
                  :alt="asset.asset_title || 'Selected Asset'"
                  :enable-context-menu="false"
                  :draggable="false"
                  container-class="h-12 w-12 shrink-0 rounded-sm bg-surface"
                  img-class="h-full w-full rounded-sm object-cover"
                />
                <span class="min-w-0 flex-1 truncate text-xs text-content-secondary">
                  {{ asset.asset_title || `Asset ${asset.asset_id}` }}
                </span>
                <button
                  type="button"
                  class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-content-muted hover:bg-overlay-subtle hover:text-content"
                  :aria-label="selectedAssetLabel(asset)"
                  @click="removeSelectedAsset(asset.media_id)"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="h-3.5 w-3.5" aria-hidden="true">
                    <path d="M6 6l12 12M18 6L6 18" stroke-width="1.8" stroke-linecap="round" />
                  </svg>
                </button>
              </li>
            </ul>
          </div>
          <div v-else class="flex aspect-square items-center justify-center rounded-lg border border-dashed border-edge text-xs text-content-muted">
            Select Assets
          </div>
        </aside>
      </div>
    </div>

    <template #footer>
      <Button variant="secondary" @click="emit('close')">Cancel</Button>
      <Button :disabled="!canAdd" :loading="loading" @click="confirmSelection">{{ addButtonLabel }}</Button>
    </template>
  </Modal>
</template>
