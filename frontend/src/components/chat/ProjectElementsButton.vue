<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import axios from 'axios'
import Modal from '../ui/Modal.vue'
import Button from '../ui/Button.vue'
import Spinner from '../ui/Spinner.vue'
import MediaImage from '../media/MediaImage.vue'
import { getApiBase } from '../../apiConfig'
import { useAssetApi, type AssetBrowserItem } from '../../composables/useAssetApi'
import {
  useProjectElementsApi,
  type ProjectElement,
  type ProjectElementType,
} from '../../composables/useProjectElementsApi'

const props = defineProps<{
  projectId: number
  projectName?: string
  elements: ProjectElement[]
  loading?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [element: ProjectElement]
  created: [element: ProjectElement]
}>()

const { fetchAssets } = useAssetApi()
const { createElement } = useProjectElementsApi()

const show = ref(false)
const view = ref<'library' | 'create'>('library')
const filter = ref<'all' | ProjectElementType>('all')
const search = ref('')
const assets = ref<AssetBrowserItem[]>([])
const assetsPage = ref(1)
const assetsTotal = ref(0)
const assetsLoading = ref(false)
const selectedAsset = ref<Partial<AssetBrowserItem> | null>(null)
const elementType = ref<ProjectElementType>('prop')
const elementName = ref('')
const description = ref('')
const creating = ref(false)
const error = ref('')
const uploadInput = ref<HTMLInputElement | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)

const filteredElements = computed(() => {
  const term = search.value.trim().toLowerCase()
  return props.elements.filter((element) => {
    if (filter.value !== 'all' && element.element_type !== filter.value) return false
    if (!term) return true
    return element.name.toLowerCase().includes(term)
      || element.reference_id.toLowerCase().includes(term)
  })
})

const canCreate = computed(() => (
  Boolean(elementName.value.trim()) && Boolean(selectedAsset.value) && !creating.value
))

const referencePreview = computed(() => {
  const prefix = { location: 'loc', character: 'char', prop: 'prop' }[elementType.value]
  const project = slugPart(props.projectName || 'project')
  const name = slugPart(elementName.value || 'name')
  return `${prefix}_${project}_${name}`
})

function slugPart(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

function open() {
  if (props.disabled) return
  show.value = true
  view.value = 'library'
  search.value = ''
}

function close() {
  if (creating.value) return
  show.value = false
}

function choose(element: ProjectElement) {
  emit('select', element)
  show.value = false
}

async function openCreate() {
  view.value = 'create'
  error.value = ''
  elementType.value = 'prop'
  elementName.value = ''
  description.value = ''
  selectedAsset.value = null
  await loadAssets(true)
  await nextTick()
  nameInput.value?.focus()
}

async function loadAssets(reset = false) {
  if (assetsLoading.value) return
  assetsLoading.value = true
  if (reset) {
    assetsPage.value = 1
    assets.value = []
  }
  try {
    const result = await fetchAssets({
      page: assetsPage.value,
      page_size: 48,
      sort_by: 'created_desc',
    })
    assets.value = reset ? result.items : [...assets.value, ...result.items]
    assetsTotal.value = result.total
    assetsPage.value += 1
  } catch (cause) {
    console.error('Failed to load Assets for element creation:', cause)
    error.value = 'Unable to load Assets.'
  } finally {
    assetsLoading.value = false
  }
}

function openExternalUpload() {
  uploadInput.value?.click()
}

async function uploadExternal(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  assetsLoading.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    const response = await axios.post(`${getApiBase()}/generate/upload-reference`, body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    selectedAsset.value = {
      media_id: response.data.media_id,
      file_hash: response.data.file_hash,
      file_format: response.data.file_format || file.name.split('.').pop() || 'png',
      asset_title: file.name,
    }
  } catch (cause) {
    console.error('Failed to upload element Asset:', cause)
    error.value = 'Unable to upload this file.'
  } finally {
    assetsLoading.value = false
  }
}

async function submitCreate() {
  if (!canCreate.value || !selectedAsset.value) return
  creating.value = true
  error.value = ''
  try {
    const element = await createElement(props.projectId, {
      name: elementName.value.trim(),
      element_type: elementType.value,
      asset_id: selectedAsset.value.asset_id,
      media_id: selectedAsset.value.asset_id ? undefined : selectedAsset.value.media_id,
      description: description.value.trim() || undefined,
    })
    emit('created', element)
    emit('select', element)
    show.value = false
  } catch (cause: any) {
    console.error('Failed to create project element:', cause)
    error.value = cause?.response?.data?.detail || 'Unable to create this element.'
  } finally {
    creating.value = false
  }
}

watch(() => props.projectId, () => {
  show.value = false
  assets.value = []
})
</script>

<template>
  <button
    type="button"
    class="flex h-8 w-8 items-center justify-center rounded-full text-content-muted transition-colors hover:bg-overlay-subtle hover:text-content-secondary disabled:pointer-events-none disabled:opacity-40"
    :disabled="disabled"
    title="Elements"
    aria-label="Open project elements"
    @click="open"
  >
    <span class="text-lg leading-none">@</span>
  </button>

  <Modal
    :show="show"
    size="custom"
    custom-class="w-[1180px] max-w-[calc(100vw-2rem)] h-[min(780px,calc(100vh-2rem))] flex flex-col overflow-hidden"
    @close="close"
  >
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <button
            v-if="view === 'create'"
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-md text-content-muted hover:bg-overlay-subtle hover:text-content"
            aria-label="Back to elements"
            @click="view = 'library'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div>
            <h2 class="text-base font-semibold text-content">{{ view === 'library' ? 'Elements' : 'New element' }}</h2>
            <p class="text-xs text-content-muted">
              {{ view === 'library' ? 'Reusable project references for chat context.' : 'Choose an Asset, then give it a project identity.' }}
            </p>
          </div>
        </div>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-md text-content-muted hover:bg-overlay-subtle hover:text-content"
          aria-label="Close"
          @click="close"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="h-4 w-4" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </template>

    <template v-if="view === 'library'">
      <div class="flex items-center gap-2 border-b border-edge px-5 py-3">
        <button
          v-for="option in [
            { value: 'all', label: 'All' },
            { value: 'character', label: 'Characters' },
            { value: 'location', label: 'Locations' },
            { value: 'prop', label: 'Props' },
          ]"
          :key="option.value"
          type="button"
          class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
          :class="filter === option.value ? 'bg-content text-surface' : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          @click="filter = option.value as any"
        >
          {{ option.label }}
        </button>
        <div class="ml-auto w-64">
          <input
            v-model="search"
            type="search"
            placeholder="Search elements"
            class="w-full rounded-md border border-edge bg-surface-raised px-3 py-1.5 text-sm text-content outline-none placeholder:text-content-muted focus:border-accent"
          />
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-5">
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <button
            type="button"
            class="flex aspect-[4/3] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-edge bg-surface-raised text-content-secondary transition-colors hover:border-content-muted hover:text-content"
            @click="openCreate"
          >
            <span class="flex h-10 w-10 items-center justify-center rounded-full bg-overlay-subtle text-xl">+</span>
            <span class="text-sm font-medium">New element</span>
          </button>

          <button
            v-for="element in filteredElements"
            :key="element.id"
            type="button"
            class="group overflow-hidden rounded-lg border border-edge bg-surface-raised text-left transition-colors hover:border-content-muted"
            @click="choose(element)"
          >
            <MediaImage
              :media-id="element.media_id || undefined"
              :asset-id="element.asset_id || undefined"
              :file-hash="element.file_hash || undefined"
              :file-format="element.file_format || undefined"
              :alt="element.name"
              :enable-context-menu="false"
              :draggable="false"
              container-class="aspect-video w-full bg-surface"
              img-class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
            />
            <span class="block p-3">
              <span class="block text-[10px] uppercase tracking-wide text-content-muted">{{ element.element_type }}</span>
              <span class="mt-0.5 block truncate text-sm font-medium text-content">{{ element.name }}</span>
              <span class="mt-1 block truncate text-xs text-content-secondary">@{{ element.reference_id }}</span>
            </span>
          </button>
        </div>
        <div v-if="loading" class="flex justify-center py-10"><Spinner /></div>
        <p v-else-if="filteredElements.length === 0" class="py-10 text-center text-sm text-content-muted">
          No elements match this view.
        </p>
      </div>
    </template>

    <template v-else>
      <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_340px]">
        <section class="flex min-h-0 flex-col border-r border-edge">
          <div class="flex items-center justify-between border-b border-edge-subtle px-5 py-3">
            <div>
              <h3 class="text-sm font-medium text-content">Choose an Asset</h3>
              <p class="text-xs text-content-muted">Browse your Stimma library or upload a new image.</p>
            </div>
            <Button variant="secondary" size="sm" @click="openExternalUpload">Upload file</Button>
            <input ref="uploadInput" type="file" accept="image/*" class="hidden" @change="uploadExternal" />
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto p-4">
            <div class="grid grid-cols-3 gap-3 xl:grid-cols-4">
              <button
                v-for="asset in assets"
                :key="asset.asset_id"
                type="button"
                class="overflow-hidden rounded-md border bg-surface-raised text-left transition-colors"
                :class="selectedAsset?.asset_id === asset.asset_id ? 'border-accent ring-1 ring-accent' : 'border-edge hover:border-content-muted'"
                @click="selectedAsset = asset"
              >
                <MediaImage
                  :media-id="asset.media_id"
                  :asset-id="asset.asset_id"
                  :file-hash="asset.file_hash"
                  :file-format="asset.file_format"
                  :alt="asset.asset_title || 'Asset'"
                  :enable-context-menu="false"
                  :draggable="false"
                  container-class="aspect-square w-full bg-surface"
                  img-class="h-full w-full object-cover"
                />
                <span class="block truncate px-2 py-1.5 text-xs text-content-secondary">
                  {{ asset.asset_title || `Asset ${asset.asset_id}` }}
                </span>
              </button>
            </div>
            <div class="flex justify-center py-5">
              <Spinner v-if="assetsLoading" />
              <Button
                v-else-if="assets.length < assetsTotal"
                variant="secondary"
                size="sm"
                @click="loadAssets(false)"
              >Load more</Button>
            </div>
          </div>
        </section>

        <aside class="min-h-0 overflow-y-auto p-5">
          <div v-if="selectedAsset" class="mb-5 overflow-hidden rounded-lg border border-edge bg-surface-raised">
            <MediaImage
              :media-id="selectedAsset.media_id"
              :asset-id="selectedAsset.asset_id"
              :file-hash="selectedAsset.file_hash"
              :file-format="selectedAsset.file_format"
              :alt="elementName || 'Selected Asset'"
              :enable-context-menu="false"
              :draggable="false"
              contain
              container-class="aspect-video w-full bg-surface"
              img-class="h-full w-full object-contain"
            />
          </div>
          <div v-else class="mb-5 flex aspect-video items-center justify-center rounded-lg border border-dashed border-edge text-xs text-content-muted">
            Select an Asset
          </div>

          <label class="block text-xs font-medium text-content-secondary">Type</label>
          <select
            v-model="elementType"
            class="mt-1 w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content outline-none focus:border-accent"
          >
            <option value="prop">Prop</option>
            <option value="character">Character</option>
            <option value="location">Location</option>
          </select>

          <label class="mt-4 block text-xs font-medium text-content-secondary">Name</label>
          <input
            ref="nameInput"
            v-model="elementName"
            type="text"
            placeholder="e.g. couteau"
            class="mt-1 w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content outline-none placeholder:text-content-muted focus:border-accent"
          />
          <p class="mt-1 truncate text-xs text-content-muted">@{{ referencePreview }}</p>

          <label class="mt-4 block text-xs font-medium text-content-secondary">Description <span class="font-normal text-content-muted">(optional)</span></label>
          <textarea
            v-model="description"
            rows="3"
            placeholder="How this element should be used"
            class="mt-1 w-full resize-none rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content outline-none placeholder:text-content-muted focus:border-accent"
          />

          <p v-if="error" class="mt-3 text-xs text-red-400">{{ error }}</p>
          <Button class="mt-5 w-full" :disabled="!canCreate" :loading="creating" @click="submitCreate">
            Create element
          </Button>
        </aside>
      </div>
    </template>
  </Modal>
</template>
