<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import {
  XMarkIcon,
  PlusIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PhotoIcon,
  FilmIcon,
  DocumentTextIcon,
  ArrowPathIcon,
  ArrowUpTrayIcon,
  TrashIcon
} from '@heroicons/vue/24/outline'
import MediaImage from '../media/MediaImage.vue'
import { useProjectElementsApi, type ProjectElement, type ProjectElementType } from '../../composables/useProjectElementsApi'
import { useProjectDirectionApi } from '../../composables/useProjectDirectionApi'
import { useAssetApi, type AssetBrowserItem } from '../../composables/useAssetApi'
import { useMediaDetailsModal } from '../../composables/useMediaDetailsModal'

const props = defineProps<{
  open: boolean
  projectId?: number
  projectName?: string
}>()

const emit = defineEmits<{
  close: []
  sendToChat: [text: string]
  generateWithAntigravity: [prompt: string]
  openProduction: []
  openProductionShot: [shotId: number]
}>()

const activeTab = ref<'elements' | 'shots'>('elements')
const elements = ref<ProjectElement[]>([])
const direction = ref<any>(null)
const loading = ref(false)
const filterType = ref<'all' | ProjectElementType>('all')
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadingElement = ref<ProjectElement | null>(null)

const { listElements, createElement, deleteElement } = useProjectElementsApi()
const { getDirection } = useProjectDirectionApi()
const { fetchAssets } = useAssetApi()
const mediaDetailsModal = useMediaDetailsModal()

async function handleDeleteElement(el: ProjectElement) {
  if (!confirm(`Supprimer l'élément @${el.reference_id} (${el.name}) du World State ?`)) return
  try {
    await deleteElement(projectEffectiveId.value, el.id)
    elements.value = elements.value.filter(e => e.id !== el.id)
  } catch (err) {
    console.error('Failed to delete element', err)
  }
}

function openMediaDetails(mediaId: number) {
  if (mediaId) mediaDetailsModal.open(mediaId)
}

const projectEffectiveId = computed(() => props.projectId || 0)

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

function handleGenerateAntigravity(el: ProjectElement) {
  const prompt = `Génère l'asset de référence @${el.reference_id} (${el.name}, ${el.element_type}) avec Antigravity CLI en respectant les spécifications de notre projet.`
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
          Séquences & Plans ({{ direction?.scenes?.length || 0 }})
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

              <!-- Status Badge & Delete Button -->
              <div class="flex items-center gap-1.5 flex-shrink-0">
                <span
                  v-if="el.asset_id || el.media_id"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-400"
                >
                  <CheckCircleIcon class="w-3 h-3" />
                  Prêt
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-amber-500/15 text-amber-400"
                >
                  <ExclamationTriangleIcon class="w-3 h-3" />
                  Manquant
                </span>
                <button
                  type="button"
                  @click.stop="handleDeleteElement(el)"
                  class="p-1 rounded text-content-muted hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  :title="`Supprimer @${el.reference_id} du World State`"
                >
                  <TrashIcon class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <!-- Thumbnail if available -->
            <button
              v-if="el.media_id"
              type="button"
              class="w-full h-28 rounded-lg overflow-hidden border border-edge-subtle bg-base p-0 text-left cursor-pointer hover:border-accent hover:ring-1 hover:ring-accent transition-all focus:outline-none"
              title="Voir l'image"
              @click="openMediaDetails(el.media_id)"
            >
              <MediaImage
                :media-id="el.media_id"
                :thumbnail="true"
                :thumbnail-size="256"
                container-class="w-full h-full"
                img-class="w-full h-full object-cover"
              />
            </button>

            <!-- Action Buttons -->
            <div class="flex flex-wrap items-center gap-1.5 pt-1">
              <button
                type="button"
                @click="handleGenerateAntigravity(el)"
                class="inline-flex items-center justify-center p-1 rounded-lg border border-edge bg-surface text-content-muted hover:text-accent hover:bg-overlay-light transition-colors text-[11px]"
                title="Générer directement avec Antigravity CLI"
              >
                <PhotoIcon class="w-3.5 h-3.5" />
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
            Aucune séquence synchronisée dans ce projet.
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

            <div v-if="sc.shots?.length" class="space-y-1.5 border-t border-edge-subtle pt-2">
              <div class="text-[10px] font-semibold uppercase tracking-wide text-content-muted">
                Plans · {{ sc.shots.length }}
              </div>
              <button
                v-for="shot in sc.shots"
                :key="shot.id"
                type="button"
                class="flex w-full items-center gap-2 rounded-md border border-edge bg-surface px-2 py-1.5 text-left hover:border-accent/50"
                @click="$emit('openProductionShot', shot.id)"
              >
                <span class="font-mono text-[10px] text-accent">P{{ String(shot.shot_number).padStart(2, '0') }}</span>
                <span class="min-w-0 flex-1 truncate text-[10px] text-content">{{ shot.title }}</span>
                <span class="shrink-0 text-[10px] text-content-muted">{{ shot.duration }}s</span>
              </button>
            </div>

            <div class="pt-1 flex justify-end">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-[11px] font-semibold text-accent hover:bg-accent/15"
                @click="$emit('openProduction')"
              >
                Gérer dans Production
                <ArrowPathIcon class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </template>
      </div>
    </aside>
  </Transition>
</template>
