<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  ArrowPathIcon,
  CheckIcon,
  DocumentDuplicateIcon,
  PhotoIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import { MediaImage } from '../media'
import { useMediaApi } from '../../composables/useMediaApi'
import { useAssetApi } from '../../composables/useAssetApi'
import { useToasts } from '../../composables/useToasts'
import {
  useProjectReferencesApi,
  type ReferencePack,
} from '../../composables/useProjectReferencesApi'

interface RefAssetItem {
  id: string
  mediaId: number
  title?: string
  roleDescription: string
}

const props = defineProps<{
  projectId?: number
  packs?: ReferencePack[]
}>()

const emit = defineEmits<{
  (e: 'asset-created', assetId: number): void
}>()

const mediaApi = useMediaApi()
const assetApi = useAssetApi()
const referencesApi = useProjectReferencesApi()
const { addToast } = useToasts()

// State
const promptText = ref<string>('')
const negativePromptText = ref<string>('')
const selectedAspectRatio = ref<string>('16:9')
const isGenerating = ref<boolean>(false)
const resultMediaId = ref<number | null>(null)
const resultImageUrl = ref<string | null>(null)

const referenceAssets = reactive<RefAssetItem[]>([])

// Asset Picker
const showAssetPicker = ref<boolean>(false)
const projectAssetsList = ref<any[]>([])
const loadingAssets = ref<boolean>(false)

const ASPECT_RATIOS: Record<string, [number, number]> = {
  '16:9': [1344, 768],
  '1:1': [1024, 1024],
  '9:16': [768, 1344],
  '4:3': [1152, 896],
  '3:4': [896, 1152],
}

function insertTag(tag: string) {
  promptText.value = (promptText.value + ' ' + tag).trim()
}

function removeRefAsset(index: number) {
  referenceAssets.splice(index, 1)
}

function handleFileUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = async () => {
    try {
      const uploaded = await mediaApi.uploadMedia(file, props.projectId)
      referenceAssets.push({
        id: `ref_${Date.now()}`,
        mediaId: uploaded.id,
        title: file.name,
        roleDescription: `Identity & Style Anchor (${file.name})`,
      })
      addToast('Image de référence ajoutée', 'success', 2500)
    } catch (err: any) {
      addToast('Erreur lors du téléversement de la référence', 'error', 4000)
    }
  }
  reader.readAsDataURL(file)
}

async function openAssetPicker() {
  showAssetPicker.value = true
  loadingAssets.value = true
  try {
    if (props.projectId) {
      const response = await assetApi.getProjectAssets(props.projectId)
      projectAssetsList.value = response.items || []
    } else {
      const response = await mediaApi.listMedia({ limit: 40 })
      projectAssetsList.value = response.items || []
    }
  } catch (err) {
    projectAssetsList.value = []
  } finally {
    loadingAssets.value = false
  }
}

function pickAsset(item: any) {
  const mId = item.primary_media_id || item.id
  referenceAssets.push({
    id: `ref_${Date.now()}`,
    mediaId: mId,
    title: item.title || item.filename || item.name,
    roleDescription: `Reference Anchor #${referenceAssets.length + 1}`,
  })
  showAssetPicker.value = false
}

async function submitGeneration() {
  if (!promptText.value.trim()) {
    addToast('Veuillez renseigner un prompt.', 'error', 3000)
    return
  }

  isGenerating.value = true
  resultMediaId.value = null
  resultImageUrl.value = null

  try {
    const dimensions = ASPECT_RATIOS[selectedAspectRatio.value] || [1344, 768]
    const mediaIds = referenceAssets.map(r => r.mediaId)

    const result = await referencesApi.generateWithReference({
      prompt: promptText.value.trim(),
      reference_media_ids: mediaIds,
      negative_prompt: negativePromptText.value.trim() || undefined,
      dimensions: dimensions,
    }, props.projectId)

    if (result?.result_media_id) {
      resultMediaId.value = result.result_media_id
      resultImageUrl.value = mediaApi.getMediaFileUrl(result.result_media_id)
      addToast('Image générée avec succès via AGY CLI !', 'success', 4000)
    }
  } catch (err: any) {
    const msg = err.response?.data?.detail || err.message || 'Erreur lors de la génération.'
    addToast(msg, 'error', 6000)
  } finally {
    isGenerating.value = false
  }
}

async function approveResult() {
  if (!resultMediaId.value) return
  try {
    const asset = await assetApi.createAssetFromMedia({
      media_id: resultMediaId.value,
      title: `Génération par Référence · ${new Date().toLocaleTimeString()}`,
      origin_type: 'reference_generation_studio',
      project_id: props.projectId,
    })
    addToast('Résultat approuvé et ajouté aux Assets !', 'success', 3000)
    if (asset?.id) emit('asset-created', asset.id)
  } catch (err: any) {
    addToast(err.message || "Erreur d'approbation", 'error', 4000)
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Header banner -->
    <div class="rounded-lg border border-edge bg-surface p-5">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="flex items-center gap-2 text-xs font-semibold text-accent">
            <SparklesIcon class="h-4 w-4" /> Génération par Référence · Antigravity CLI
          </div>
          <h2 class="mt-1 text-base font-semibold text-content">Génération d'Images avec Références Visuelles</h2>
          <p class="mt-0.5 max-w-2xl text-xs text-content-secondary">
            Associez des assets de référence (<span class="font-mono text-accent">@image1</span>, <span class="font-mono text-accent">&lt;Picture 1&gt;</span>) pour conserver l'identité, le style et l'architecture exacte via AGY CLI.
          </p>
        </div>
      </div>
    </div>

    <!-- Main Grid -->
    <div class="grid gap-6 lg:grid-cols-[1fr_400px]">
      <!-- Left: Prompt & Configuration -->
      <div class="space-y-5 rounded-lg border border-edge bg-surface p-5">
        <!-- Prompt Editor -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-xs font-semibold text-content">Prompt de Génération</label>
            <!-- Quick Tag Inserters -->
            <div class="flex flex-wrap items-center gap-1.5 text-[10px]">
              <span class="text-content-muted">Insérer tag:</span>
              <button
                v-for="(_, idx) in referenceAssets"
                :key="idx"
                type="button"
                class="rounded bg-overlay-subtle px-1.5 py-0.5 font-mono text-accent hover:bg-accent/20 transition-colors"
                @click="insertTag(`@image${idx + 1}`)"
              >
                @image{{ idx + 1 }}
              </button>
              <button
                v-for="(_, idx) in referenceAssets"
                :key="`pic_${idx}`"
                type="button"
                class="rounded bg-overlay-subtle px-1.5 py-0.5 font-mono text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                @click="insertTag(`<Picture ${idx + 1}>`)"
              >
                &lt;Picture {{ idx + 1 }}&gt;
              </button>
            </div>
          </div>
          <textarea
            v-model="promptText"
            rows="6"
            class="w-full resize-y rounded-md border border-edge bg-base p-3 text-xs text-content outline-none focus:border-accent"
            placeholder="Exemple: Crée une vue photoréaliste de la pièce en utilisant <Picture 1> comme référence architecturale stricte et @image2 pour le mobilier..."
          />
        </div>

        <!-- Negative Prompt -->
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-content-secondary">Exclusions & Prompt Négatif</label>
          <input
            v-model="negativePromptText"
            type="text"
            class="w-full rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent"
            placeholder="No people, no extra furniture, no text, no blur, no CGI look..."
          />
        </div>

        <!-- Aspect Ratio -->
        <div class="space-y-2">
          <label class="text-xs font-medium text-content-secondary">Ratio d'Aspect & Résolution</label>
          <div class="grid grid-cols-5 gap-2">
            <button
              v-for="(dims, ratio) in ASPECT_RATIOS"
              :key="ratio"
              type="button"
              class="rounded-md border p-2 text-center text-xs transition-colors"
              :class="selectedAspectRatio === ratio ? 'border-accent bg-accent/15 text-accent font-semibold' : 'border-edge bg-overlay-faint text-content-secondary hover:border-edge-strong'"
              @click="selectedAspectRatio = ratio"
            >
              <div>{{ ratio }}</div>
              <div class="text-[9px] font-mono opacity-70">{{ dims[0] }}×{{ dims[1] }}</div>
            </button>
          </div>
        </div>

        <!-- Generate Button -->
        <div class="pt-3 border-t border-edge">
          <Button
            class="w-full"
            :disabled="!promptText.trim() || isGenerating"
            :loading="isGenerating"
            @click="submitGeneration"
          >
            <SparklesIcon class="h-4 w-4" /> Générer avec AGY CLI
          </Button>
        </div>
      </div>

      <!-- Right: Reference Assets Manager -->
      <div class="space-y-4 rounded-lg border border-edge bg-surface p-5">
        <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
          <div>
            <h3 class="text-xs font-semibold text-content">Assets de Référence (Ordered Roles)</h3>
            <p class="text-[10px] text-content-muted">Transmis dans l'ordre strict &lt;Picture 1&gt;, &lt;Picture 2&gt;...</p>
          </div>
          <div class="flex items-center gap-1">
            <label class="cursor-pointer">
              <input type="file" accept="image/*" class="hidden" @change="handleFileUpload" />
              <Button size="sm" variant="secondary">
                <PlusIcon class="h-3.5 w-3.5" /> Fichier
              </Button>
            </label>
            <Button size="sm" variant="ghost" @click="openAssetPicker">
              <PhotoIcon class="h-3.5 w-3.5" /> Projet
            </Button>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="!referenceAssets.length" class="rounded-md border border-dashed border-edge p-8 text-center text-xs text-content-muted">
          <PhotoIcon class="mx-auto h-8 w-8 text-content-muted/60 mb-2" />
          Aucun asset de référence attaché.<br />
          Ajoutez des images pour verrouiller l'identité visuelle.
        </div>

        <!-- Assets List -->
        <div v-else class="space-y-3 max-h-[460px] overflow-y-auto pr-1 custom-scrollbar">
          <div
            v-for="(refItem, idx) in referenceAssets"
            :key="refItem.id"
            class="flex items-start gap-3 rounded-md border border-edge bg-overlay-faint p-2.5"
          >
            <div class="relative h-16 w-16 flex-shrink-0 overflow-hidden rounded border border-edge bg-matte">
              <MediaImage
                :media-id="refItem.mediaId"
                :thumbnail="true"
                :contain="true"
                container-class="h-full w-full"
                img-class="h-full w-full object-cover"
              />
              <span class="absolute top-0.5 left-0.5 rounded bg-black/80 px-1 py-0.2 text-[8px] font-bold text-accent">
                #{{ idx + 1 }}
              </span>
            </div>

            <div class="flex-1 min-w-0 space-y-1">
              <div class="flex items-center justify-between">
                <span class="font-mono text-xs font-bold text-accent">&lt;Picture {{ idx + 1 }}&gt; (@image{{ idx + 1 }})</span>
                <button
                  type="button"
                  class="text-content-muted hover:text-red-400 p-0.5"
                  title="Retirer"
                  @click="removeRefAsset(idx)"
                >
                  <XMarkIcon class="h-3.5 w-3.5" />
                </button>
              </div>
              <input
                v-model="refItem.roleDescription"
                class="w-full rounded border border-edge bg-base px-2 py-0.5 text-[11px] text-content outline-none focus:border-accent"
                placeholder="Rôle de la référence..."
              />
              <p class="truncate font-mono text-[9px] text-content-muted">Media ID: {{ refItem.mediaId }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Results Stage -->
    <div v-if="resultImageUrl" class="rounded-lg border border-edge bg-surface p-5 space-y-4">
      <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
        <div>
          <h3 class="text-sm font-semibold text-content">Image Générée (AGY CLI)</h3>
          <p class="text-xs text-content-muted">Résultat prêt à être approuvé dans le projet.</p>
        </div>
        <div class="flex items-center gap-2">
          <Button size="sm" variant="secondary" @click="approveResult">
            <CheckIcon class="h-4 w-4" /> Approuver comme Asset
          </Button>
          <a
            :href="resultImageUrl"
            download="generated_reference_result.png"
            target="_blank"
            class="rounded-md border border-edge bg-overlay-subtle px-3 py-1.5 text-xs font-medium text-content hover:bg-overlay-light"
          >
            Télécharger
          </a>
        </div>
      </div>

      <div class="flex justify-center rounded-md bg-matte p-2">
        <img :src="resultImageUrl" class="max-h-[580px] max-w-full rounded object-contain" alt="Generated Output" />
      </div>
    </div>

    <!-- Asset Picker Modal -->
    <div
      v-if="showAssetPicker"
      class="fixed inset-0 z-modal flex items-center justify-center bg-black/60 p-4"
      @click.self="showAssetPicker = false"
    >
      <div class="w-full max-w-2xl rounded-lg border border-edge bg-surface p-5 space-y-4 shadow-2xl">
        <div class="flex items-center justify-between border-b border-edge-subtle pb-3">
          <h3 class="text-sm font-semibold text-content">Choisir un Asset de Référence</h3>
          <button type="button" class="text-content-muted hover:text-content" @click="showAssetPicker = false">
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>

        <div class="max-h-96 overflow-y-auto custom-scrollbar">
          <div v-if="loadingAssets" class="py-12 text-center text-xs text-content-muted">Chargement des assets...</div>
          <div v-else-if="!projectAssetsList.length" class="py-12 text-center text-xs text-content-muted">Aucun asset trouvé dans ce projet.</div>
          <div v-else class="grid grid-cols-3 sm:grid-cols-4 gap-3">
            <div
              v-for="item in projectAssetsList"
              :key="item.id"
              class="group relative aspect-square cursor-pointer overflow-hidden rounded-md border border-edge bg-matte hover:border-accent"
              @click="pickAsset(item)"
            >
              <MediaImage
                :media-id="item.primary_media_id || item.id"
                :thumbnail="true"
                :contain="true"
                container-class="h-full w-full"
                img-class="h-full w-full object-cover transition-transform group-hover:scale-105"
              />
              <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1 text-[10px] text-white truncate">
                {{ item.title || item.filename || item.name || `#${item.id}` }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
