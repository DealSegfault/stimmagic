<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import {
  XMarkIcon,
  SparklesIcon,
  PlusIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PhotoIcon,
  FilmIcon,
  DocumentTextIcon,
  ArrowPathIcon,
  ArrowUpTrayIcon,
  CommandLineIcon
} from '@heroicons/vue/24/outline'
import MediaImage from '../media/MediaImage.vue'
import { useProjectElementsApi, type ProjectElement, type ProjectElementType } from '../../composables/useProjectElementsApi'
import { useProjectDirectionApi } from '../../composables/useProjectDirectionApi'
import { useAssetApi, type AssetBrowserItem } from '../../composables/useAssetApi'

const props = defineProps<{
  open: boolean
  projectId?: number
  projectName?: string
}>()

const emit = defineEmits<{
  close: []
  sendToChat: [text: string]
  generateWithAntigravity: [prompt: string]
}>()

const activeTab = ref<'elements' | 'shots'>('elements')
const elements = ref<ProjectElement[]>([])
const direction = ref<any>(null)
const loading = ref(false)
const filterType = ref<'all' | ProjectElementType>('all')
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadingElement = ref<ProjectElement | null>(null)

const { listElements, createElement } = useProjectElementsApi()
const { getDirection } = useProjectDirectionApi()
const { fetchAssets } = useAssetApi()

const projectEffectiveId = computed(() => props.projectId || 1)

async function loadData() {
  if (!projectEffectiveId.value) return
  loading.value = true
  try {
    const [els, dir] = await Promise.all([
      listElements(projectEffectiveId.value),
      getDirection(projectEffectiveId.value).catch(() => null)
    ])
    elements.value = els || []
    direction.value = dir
  } catch (e) {
    console.error('Failed to load project requirements', e)
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    loadData()
  }
})

watch(() => props.projectId, () => {
  if (props.open) {
    loadData()
  }
})

onMounted(() => {
  if (props.open) {
    loadData()
  }
})

const filteredElements = computed(() => {
  if (filterType.value === 'all') return elements.value
  return elements.value.filter(el => el.element_type === filterType.value)
})

const stats = computed(() => {
  const ready = elements.value.filter(e => e.asset_id || e.media_id).length
  const total = elements.value.length
  return {
    ready,
    missing: total - ready,
    total
  }
})

function getElementAntigravityPrompt(el: ProjectElement): string {
  if (el.element_type === 'character') {
    return `/Users/mac/.local/bin/agy --dangerously-skip-permissions --print 'Character reference sheet for ${el.name}, 3-views (front, side, back profile), clean neutral background, 8k photographic character design'`
  } else if (el.element_type === 'location') {
    return `/Users/mac/.local/bin/agy --dangerously-skip-permissions --print 'Architectural location concept and panoramic view of ${el.name}, cinematic lighting, photorealistic interior/exterior details'`
  } else {
    return `/Users/mac/.local/bin/agy --dangerously-skip-permissions --print 'Detailed hero prop close-up photo of ${el.name}, macro photography, studio practical lighting, photorealistic'`
  }
}

function handleGenerateAntigravity(el: ProjectElement) {
  const prompt = `Génère l'asset de référence @${el.reference_id} (${el.name}, ${el.element_type}) avec Antigravity CLI en respectant les spécifications de notre projet.`
  emit('sendToChat', prompt)
  emit('close')
}

function handleInsertShotPrompt(shot: any) {
  const prompt = `Génère le prompt Seedance 2.0 officiel (en chinois, 15s 21:9, éclairage practicals-only, Lubezki × Deakins, handles @image, micro-acting et synchronisation caméra-émotion) pour le Plan ${shot.scene_number || shot.id}: "${shot.title || shot.description || ''}".`
  emit('sendToChat', prompt)
  emit('close')
}
</script>

<template>
  <Transition
    enter-active-class="transform transition ease-in-out duration-300"
    enter-from-class="translate-x-full"
    enter-to-class="translate-x-0"
    leave-active-class="transform transition ease-in-out duration-200"
    leave-from-class="translate-x-0"
    leave-to-class="translate-x-full"
  >
    <aside
      v-if="open"
      class="fixed inset-y-0 right-0 z-40 w-96 max-w-[90vw] bg-surface border-l border-edge shadow-2xl flex flex-col"
    >
      <!-- Drawer Header -->
      <div class="px-4 py-3.5 border-b border-edge flex items-center justify-between bg-surface-raised/40">
        <div class="flex items-center gap-2 min-w-0">
          <div class="p-1 rounded-md bg-accent/15 text-accent flex-shrink-0">
            <FilmIcon class="w-4 h-4" />
          </div>
          <div class="min-w-0">
            <h2 class="text-sm font-bold text-content truncate">
              Requirements & État
            </h2>
            <p class="text-[11px] text-content-muted truncate">
              Projet: {{ projectName || 'Actif' }} (ID {{ projectEffectiveId }})
            </p>
          </div>
        </div>

        <div class="flex items-center gap-1">
          <button
            type="button"
            @click="loadData"
            class="p-1 rounded text-content-muted hover:text-content hover:bg-surface-raised transition-colors"
            title="Actualiser"
          >
            <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': loading }" />
          </button>
          <button
            type="button"
            @click="$emit('close')"
            class="p-1 rounded text-content-muted hover:text-content hover:bg-surface-raised transition-colors"
            title="Fermer"
          >
            <XMarkIcon class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Quick KPI Stats -->
      <div class="px-4 py-2.5 bg-base/50 border-b border-edge-subtle flex items-center justify-between text-xs">
        <div class="flex items-center gap-1.5 text-emerald-500 font-medium">
          <CheckCircleIcon class="w-4 h-4" />
          <span>{{ stats.ready }} Prêts</span>
        </div>
        <div class="flex items-center gap-1.5 text-amber-500 font-medium">
          <ExclamationTriangleIcon class="w-4 h-4" />
          <span>{{ stats.missing }} Manquants</span>
        </div>
        <div class="text-content-muted text-[11px]">
          Total: {{ stats.total }} assets
        </div>
      </div>

      <!-- Tab Switcher -->
      <div class="px-4 pt-3 flex gap-2 border-b border-edge bg-surface">
        <button
          type="button"
          @click="activeTab = 'elements'"
          class="pb-2 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5"
          :class="activeTab === 'elements' ? 'border-accent text-accent' : 'border-transparent text-content-muted hover:text-content'"
        >
          <PhotoIcon class="w-3.5 h-3.5" />
          Assets Requis ({{ elements.length }})
        </button>
        <button
          type="button"
          @click="activeTab = 'shots'"
          class="pb-2 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5"
          :class="activeTab === 'shots' ? 'border-accent text-accent' : 'border-transparent text-content-muted hover:text-content'"
        >
          <DocumentTextIcon class="w-3.5 h-3.5" />
          Scènes & Plans ({{ direction?.scenes?.length || 0 }})
        </button>
      </div>

      <!-- Drawer Body -->
      <div class="flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar space-y-3">
        <!-- TAB 1: ASSETS -->
        <template v-if="activeTab === 'elements'">
          <!-- Filter Buttons -->
          <div class="flex gap-1 mb-2">
            <button
              v-for="t in ['all', 'character', 'location', 'prop']"
              :key="t"
              @click="filterType = t as any"
              class="px-2 py-0.5 rounded text-[11px] font-medium transition-colors"
              :class="filterType === t ? 'bg-accent/20 text-accent font-semibold' : 'bg-surface-raised text-content-muted hover:text-content'"
            >
              {{ t === 'all' ? 'Tous' : t === 'character' ? 'Persos' : t === 'location' ? 'Lieux' : 'Props' }}
            </button>
          </div>

          <div v-if="filteredElements.length === 0" class="text-center py-8 text-xs text-content-muted">
            Aucun asset trouvé pour ce filtre.
          </div>

          <div
            v-for="el in filteredElements"
            :key="el.id"
            class="p-3 rounded-xl border border-edge bg-surface-raised/30 hover:border-edge-strong transition-all space-y-2.5"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                    :class="el.element_type === 'character' ? 'bg-purple-500/15 text-purple-400' : el.element_type === 'location' ? 'bg-blue-500/15 text-blue-400' : 'bg-amber-500/15 text-amber-400'"
                  >
                    {{ el.element_type }}
                  </span>
                  <span class="text-xs font-semibold text-content truncate">{{ el.name }}</span>
                </div>
                <div class="text-[11px] font-mono text-content-muted truncate mt-0.5">
                  @{{ el.reference_id }}
                </div>
              </div>

              <!-- Status Badge -->
              <span
                v-if="el.asset_id || el.media_id"
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-400 flex-shrink-0"
              >
                <CheckCircleIcon class="w-3 h-3" />
                Prêt
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/15 text-amber-400 flex-shrink-0"
              >
                <ExclamationTriangleIcon class="w-3 h-3" />
                Manquant
              </span>
            </div>

            <!-- Thumbnail if available -->
            <div v-if="el.media_id" class="w-full h-28 rounded-lg overflow-hidden border border-edge-subtle bg-base">
              <MediaImage
                :media-id="el.media_id"
                :thumbnail="true"
                :thumbnail-size="256"
                container-class="w-full h-full"
                img-class="w-full h-full object-cover"
              />
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center gap-2 pt-1">
              <button
                type="button"
                @click="handleGenerateAntigravity(el)"
                class="flex-1 inline-flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-lg border border-accent/30 bg-accent/10 hover:bg-accent/20 text-accent text-[11px] font-semibold transition-colors shadow-sm"
                title="Générer avec Antigravity CLI par défaut"
              >
                <SparklesIcon class="w-3.5 h-3.5" />
                Générer (Agy)
              </button>

              <button
                type="button"
                @click="$emit('sendToChat', `Ancre l'image sélectionnée comme référence pour @${el.reference_id}`)"
                class="inline-flex items-center justify-center p-1 rounded-lg border border-edge bg-surface text-content-muted hover:text-content hover:bg-overlay-light transition-colors text-[11px]"
                title="Associer une image manuellement"
              >
                <ArrowUpTrayIcon class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </template>

        <!-- TAB 2: SHOTS & SCENES -->
        <template v-if="activeTab === 'shots'">
          <div v-if="!direction?.scenes?.length" class="text-center py-8 text-xs text-content-muted">
            Aucune scène synchronisée dans ce projet.
          </div>

          <div
            v-for="sc in direction?.scenes || []"
            :key="sc.id"
            class="p-3 rounded-xl border border-edge bg-surface-raised/30 hover:border-edge-strong transition-all space-y-2"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-accent/15 text-accent">
                    #{{ sc.sequence_number || sc.scene_number || sc.id }}
                  </span>
                  <span class="text-xs font-semibold text-content truncate">{{ sc.title }}</span>
                </div>
              </div>
              <span
                class="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded"
                :class="sc.status === 'done' || sc.validation_status === 'approved' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-surface text-content-muted'"
              >
                {{ sc.status || 'draft' }}
              </span>
            </div>

            <p v-if="sc.description" class="text-[11px] text-content-secondary line-clamp-2 leading-relaxed">
              {{ sc.description }}
            </p>

            <div class="pt-1 flex items-center justify-end">
              <button
                type="button"
                @click="handleInsertShotPrompt(sc)"
                class="inline-flex items-center gap-1 py-1 px-2 rounded-lg bg-surface-raised hover:bg-overlay-light border border-edge text-[11px] font-medium text-content transition-colors"
              >
                <CommandLineIcon class="w-3.5 h-3.5 text-accent" />
                Prompt Seedance 2.0 (中文)
              </button>
            </div>
          </div>
        </template>
      </div>
    </aside>
  </Transition>
</template>
