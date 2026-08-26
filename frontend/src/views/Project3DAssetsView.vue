<template>
  <div class="flex h-full min-h-0 flex-col overflow-y-auto bg-base px-6 py-6 custom-scrollbar lg:px-10">
    <div class="mx-auto w-full max-w-[1440px] space-y-6">
      <header class="flex flex-col gap-3 border-b border-edge-subtle pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="mb-1 text-[11px] font-mono uppercase tracking-[0.16em] text-accent">Atelier 3D</p>
          <h1 class="text-2xl font-semibold tracking-tight text-content">Générer des assets 3D</h1>
          <p class="mt-1 max-w-2xl text-sm text-content-secondary">
            Sélectionnez plusieurs images de référence. TRELLIS.2 les traite en parallèle sur Modal et dépose chaque GLB dans les Assets du projet.
          </p>
        </div>
        <div class="flex items-center gap-2 text-xs text-content-muted">
          <span class="h-2 w-2 rounded-full" :class="modalConfigured ? 'bg-emerald-400' : 'bg-amber-400'" />
          {{ modalConfigured ? 'Pipeline Modal prêt' : 'Pipeline Modal à configurer' }}
        </div>
      </header>

      <div v-if="error" class="rounded-md border border-red-500/25 bg-red-500/5 px-3 py-2 text-xs text-red-300">
        {{ error }}
      </div>

      <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section class="min-w-0 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-content">Images source</h2>
              <p class="mt-1 text-xs text-content-muted">{{ selectedIds.length }} sélectionnée{{ selectedIds.length > 1 ? 's' : '' }} · {{ sourceImages.length }} dans le projet</p>
            </div>
            <label class="inline-flex cursor-pointer items-center gap-2 rounded-md border border-edge-subtle bg-surface px-3 py-2 text-xs font-medium text-content-secondary transition-colors hover:border-accent/50 hover:text-content">
              <input ref="fileInput" type="file" accept="image/*" multiple class="sr-only" @change="handleUpload" />
              <span class="text-accent">＋</span>
              Ajouter des images
            </label>
          </div>

          <div v-if="loadingSources" class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
            <div v-for="i in 10" :key="i" class="aspect-square animate-pulse rounded-media bg-overlay-faint" />
          </div>
          <div v-else-if="sourceImages.length === 0" class="rounded-lg border border-dashed border-edge-subtle bg-surface/40 px-6 py-14 text-center">
            <div class="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-xl text-accent">◈</div>
            <p class="text-sm font-medium text-content">Aucune image source dans ce projet</p>
            <p class="mx-auto mt-1 max-w-md text-xs text-content-muted">Ajoutez des vues isolées de vos objets, idéalement sur fond transparent ou neutre.</p>
          </div>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
            <button
              v-for="item in sourceImages"
              :key="item.id"
              type="button"
              class="group relative aspect-square overflow-hidden rounded-media border bg-matte text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              :class="isSelected(item.id) ? 'border-accent ring-2 ring-accent/35' : 'border-edge-subtle hover:border-edge-strong'"
              @click="toggleSelection(item.id)"
            >
              <MediaImage
                :media-id="item.id"
                :file-hash="item.file_hash"
                thumbnail-size="512"
                thumbnail-mode="fit"
                :has-alpha="item.has_alpha"
                :enable-context-menu="false"
                container-class="h-full w-full"
                img-class="h-full w-full object-contain"
              />
              <span class="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-7 text-[11px] text-white">
                {{ item.original_filename || `Image ${item.id}` }}
              </span>
              <span
                class="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-md border text-xs font-semibold shadow-sm transition-colors"
                :class="isSelected(item.id) ? 'border-accent bg-accent text-accent-contrast' : 'border-white/40 bg-black/40 text-white/70 group-hover:border-white/70'"
                :aria-label="isSelected(item.id) ? 'Désélectionner' : 'Sélectionner'"
              >
                {{ isSelected(item.id) ? '✓' : '' }}
              </span>
            </button>
          </div>
        </section>

        <aside class="h-fit rounded-lg border border-edge-subtle bg-surface p-4 shadow-sm xl:sticky xl:top-0">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold text-content">Paramètres d’export</h2>
              <p class="mt-1 text-xs leading-relaxed text-content-muted">Les réglages élevés favorisent la qualité des détails et des matériaux PBR.</p>
            </div>
            <span class="rounded-md bg-accent/10 px-2 py-1 text-[10px] font-mono text-accent">TRELLIS.2</span>
          </div>

          <div class="mt-5 space-y-4">
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-content-secondary">Résolution volumique</span>
              <select v-model="settings.resolution" class="w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content focus:border-accent focus:outline-none">
                <option value="512">512³ · rapide</option>
                <option value="1024">1024³ · équilibrée</option>
                <option value="1536">1536³ · meilleure qualité</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-content-secondary">Texture PBR</span>
              <select v-model.number="settings.texture_size" class="w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content focus:border-accent focus:outline-none">
                <option :value="1024">1024 px</option>
                <option :value="2048">2048 px</option>
                <option :value="4096">4096 px · maximum</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-content-secondary">Densité de maillage</span>
              <select v-model.number="settings.decimation_target" class="w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content focus:border-accent focus:outline-none">
                <option :value="500000">500k faces · léger</option>
                <option :value="1000000">1M faces · détaillé</option>
                <option :value="2000000">2M faces · maximum</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-content-secondary">Parallélisme du batch</span>
              <select v-model.number="settings.parallelism" class="w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content focus:border-accent focus:outline-none">
                <option :value="2">2 GPU simultanés</option>
                <option :value="4">4 GPU simultanés</option>
                <option :value="8">8 GPU simultanés · rapide</option>
                <option :value="12">12 GPU simultanés · maximum</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-medium text-content-secondary">Seed (optionnel)</span>
              <input v-model.number="settings.seed" type="number" min="0" placeholder="Aléatoire" class="w-full rounded-md border border-edge bg-surface-raised px-3 py-2 text-sm text-content placeholder:text-content-muted focus:border-accent focus:outline-none" />
            </label>
          </div>

          <button
            type="button"
            class="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-accent-contrast transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45"
            :disabled="selectedIds.length === 0 || busy || !modalConfigured"
            @click="startBatch"
          >
            <span v-if="busy" class="h-4 w-4 animate-spin rounded-full border-2 border-accent-contrast/35 border-t-accent-contrast" />
            {{ busy ? 'Génération en cours…' : `Générer ${selectedIds.length || ''} GLB` }}
          </button>
          <p v-if="!modalConfigured" class="mt-2 text-center text-[11px] text-amber-400">Configurez TRELLIS2_MODAL_URL côté backend pour activer la génération.</p>
          <p v-else class="mt-2 text-center text-[11px] text-content-muted">Chaque image devient un Asset GLB indépendant.</p>
        </aside>
      </div>

      <section v-if="batch" class="space-y-4 border-t border-edge-subtle pt-6">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p class="mb-1 text-[11px] font-mono uppercase tracking-[0.16em] text-accent">Batch {{ batch.batch_id.slice(0, 8) }}</p>
            <h2 class="text-lg font-semibold text-content">Exports 3D</h2>
          </div>
          <div class="text-right text-xs text-content-muted">
            <span class="font-mono text-content">{{ batch.completed || 0 }}/{{ batch.total }}</span> terminé{{ batch.total > 1 ? 's' : '' }}
            <span v-if="batch.failed" class="ml-2 text-red-400">· {{ batch.failed }} erreur{{ batch.failed > 1 ? 's' : '' }}</span>
          </div>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-overlay-faint">
          <div class="h-full rounded-full bg-accent transition-all" :style="{ width: `${progressPercent}%` }" />
        </div>
        <div v-if="completedJobs.length" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="job in completedJobs" :key="job.id" class="overflow-hidden rounded-lg border border-edge-subtle bg-surface">
            <div class="h-64 bg-matte">
              <ModelViewer v-if="job.result_media" :src="getMediaFileUrl(job.result_media.file_hash)" />
            </div>
            <div class="flex items-center justify-between gap-3 border-t border-edge-subtle px-3 py-2.5">
              <div class="min-w-0">
                <p class="truncate text-xs font-medium text-content">{{ job.result_media?.original_filename || `Asset ${job.result_media_id}` }}</p>
                <p class="mt-0.5 text-[11px] text-emerald-400">Asset ajouté au projet</p>
              </div>
              <a
                v-if="job.result_media"
                :href="getMediaFileUrl(job.result_media.id)"
                download
                class="flex-shrink-0 rounded-md border border-edge-subtle px-2 py-1 text-[11px] font-medium text-content-secondary transition-colors hover:border-accent/50 hover:text-content"
              >Télécharger</a>
            </div>
          </article>
        </div>
        <div v-if="failedJobs.length" class="space-y-2">
          <div v-for="job in failedJobs" :key="job.id" class="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-300">
            {{ job.source_filename || `Image ${job.source_media_id}` }} · {{ job.error || 'Échec de génération' }}
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { getApiBase } from '../apiConfig'
import { useMediaApi } from '../composables/useMediaApi'
import { useLibraryUpload } from '../composables/useLibraryUpload'
import { addToast } from '../composables/useToasts'
import { MediaImage } from '../components/media'
import ModelViewer from '../components/viewers/ModelViewer.vue'

const props = defineProps({
  project: {
    type: Object,
    required: true,
  },
})

const { fetchMedia, getMediaFileUrl } = useMediaApi()
const { uploadFiles } = useLibraryUpload()
const sourceImages = ref([])
const selectedIds = ref([])
const loadingSources = ref(true)
const busy = ref(false)
const error = ref('')
const batch = ref(null)
const fileInput = ref(null)
let pollTimer = null

const settings = reactive({
  resolution: '1536',
  texture_size: 4096,
  decimation_target: 1000000,
  parallelism: 8,
  seed: null,
})

const modalConfigured = ref(false)
const progressPercent = computed(() => {
  if (!batch.value?.total) return 0
  return Math.round(((batch.value.completed || 0) + (batch.value.failed || 0)) / batch.value.total * 100)
})
const completedJobs = computed(() => (batch.value?.jobs || []).filter(job => job.status === 'completed'))
const failedJobs = computed(() => (batch.value?.jobs || []).filter(job => job.status === 'failed'))

function isSelected(id) {
  return selectedIds.value.includes(id)
}

function toggleSelection(id) {
  selectedIds.value = isSelected(id)
    ? selectedIds.value.filter(itemId => itemId !== id)
    : [...selectedIds.value, id]
}

async function loadSources() {
  loadingSources.value = true
  error.value = ''
  try {
    const response = await fetchMedia({
      project_id: props.project.id,
      media_types: 'images',
      page: 1,
      page_size: 200,
      sort_by: 'created_desc',
    })
    sourceImages.value = response.items || []
    selectedIds.value = selectedIds.value.filter(id => sourceImages.value.some(item => item.id === id))
  } catch (cause) {
    error.value = cause?.response?.data?.detail || 'Impossible de charger les images du projet.'
  } finally {
    loadingSources.value = false
  }
}

async function loadHealth() {
  try {
    const response = await axios.get(`${getApiBase()}/trellis2/health`)
    modalConfigured.value = response.data?.configured === true
  } catch {
    modalConfigured.value = false
  }
}

async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  const results = await uploadFiles(files, [], props.project.id)
  await loadSources()
  const uploadedIds = results.filter(item => item.status === 'success' && item.media_id).map(item => item.media_id)
  selectedIds.value = [...new Set([...selectedIds.value, ...uploadedIds])]
}

async function startBatch() {
  if (!selectedIds.value.length || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await axios.post(`${getApiBase()}/trellis2/batches`, {
      project_id: props.project.id,
      media_ids: selectedIds.value,
      ...settings,
    })
    batch.value = response.data
    await pollBatch()
  } catch (cause) {
    error.value = cause?.response?.data?.detail || 'Impossible de démarrer le batch TRELLIS.2.'
    addToast(error.value, 'error')
    busy.value = false
  }
}

async function pollBatch() {
  if (!batch.value?.batch_id) return
  try {
    const response = await axios.get(`${getApiBase()}/trellis2/batches/${batch.value.batch_id}`)
    batch.value = response.data
    if (['completed', 'completed_with_errors', 'failed'].includes(batch.value.status)) {
      busy.value = false
      if (batch.value.status === 'completed') addToast('Les assets 3D ont été ajoutés au projet.', 'success')
      return
    }
    pollTimer = window.setTimeout(pollBatch, 2500)
  } catch (cause) {
    error.value = cause?.response?.data?.detail || 'Le suivi du batch est momentanément indisponible.'
    pollTimer = window.setTimeout(pollBatch, 5000)
  }
}

onMounted(() => {
  loadSources()
  loadHealth()
})
onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>
