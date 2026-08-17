<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-end justify-between gap-3 px-0.5">
      <div>
        <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Tableau de tournage</p>
        <p class="mt-1 text-xs text-content-muted">Une ligne par scène, avec son brief, ses ressources, ses essais et son chat.</p>
      </div>
      <div class="flex items-center gap-2 font-mono text-[11px] tabular-nums text-content-tertiary">
        <span>{{ scenes.length }} scène{{ scenes.length === 1 ? '' : 's' }}</span>
        <span class="text-content-tertiary/50">·</span>
        <span>{{ totalGenerationCount }} génération{{ totalGenerationCount === 1 ? '' : 's' }}</span>
      </div>
    </div>

    <div v-if="!scenes.length" class="rounded-lg border border-dashed border-edge-subtle px-4 py-8 text-center text-xs text-content-muted">
      Aucune scène associée à ce brief.
    </div>

    <template v-else>
      <div class="overflow-x-auto rounded-xl border border-edge-subtle bg-surface">
        <table class="min-w-[1080px] w-full border-collapse text-left">
          <thead>
            <tr class="border-b border-edge-subtle bg-surface-raised/45">
              <th class="w-[250px] px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-content-tertiary">Scènes à tourner</th>
              <th class="w-[230px] px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-content-tertiary">Brief</th>
              <th v-for="lane in lanes" :key="lane.id" class="px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-content-tertiary">
                {{ lane.label }}
              </th>
              <th class="w-[150px] px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-content-tertiary">Raccord</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(scene, index) in scenes"
              :key="scene.id"
              class="border-b border-edge-subtle/80 transition-colors last:border-b-0"
              :class="activeSceneId === scene.id ? 'bg-accent/[0.045]' : 'hover:bg-overlay-faint'"
            >
              <td class="px-3 py-2.5 align-top">
                <button
                  type="button"
                  class="flex w-full items-start gap-2.5 rounded-lg text-left outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  :aria-pressed="activeSceneId === scene.id"
                  @click="selectScene(scene, 'brief')"
                >
                  <span class="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-accent/10 font-mono text-[11px] font-semibold text-accent">
                    {{ String(index + 1).padStart(2, '0') }}
                  </span>
                  <span class="min-w-0">
                    <span class="block text-[10px] font-semibold uppercase tracking-[0.08em] text-content-tertiary">
                      S{{ scene.scene_number }} · Seq. {{ scene.sequence_number }}
                    </span>
                    <span class="mt-0.5 block truncate text-sm font-semibold text-content">{{ scene.title }}</span>
                  </span>
                </button>
              </td>

              <td class="px-3 py-2.5 align-top">
                <button type="button" class="w-full rounded-lg px-2 py-1 text-left outline-none transition-colors hover:bg-overlay-faint focus-visible:ring-2 focus-visible:ring-accent" @click="selectScene(scene, 'brief')">
                  <span v-if="briefPreview(scene).summary" class="line-clamp-2 text-xs leading-4 text-content-secondary">{{ briefPreview(scene).summary }}</span>
                  <span v-else class="text-xs italic text-content-muted">Brief à compléter</span>
                  <span class="mt-1 block text-[10px] text-content-tertiary">{{ isBriefDirty(scene) ? 'Modifications non enregistrées' : (scene.description ? 'Brief renseigné' : 'Brief vide') }}</span>
                </button>
              </td>

              <td v-for="lane in lanes" :key="`${scene.id}-${lane.id}`" class="px-3 py-2.5 align-top">
                <button
                  type="button"
                  class="flex min-h-10 w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left outline-none transition-colors hover:bg-overlay-faint focus-visible:ring-2 focus-visible:ring-accent"
                  :class="activeSceneId === scene.id && activeLane === lane.id ? 'bg-accent/10 text-accent' : 'text-content-secondary'"
                  @click="selectScene(scene, lane.id)"
                >
                  <span class="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-overlay-faint text-[11px]" :class="lane.id === 'chat' && chatCache[scene.id] ? 'text-accent' : ''">
                    <template v-if="lane.id === 'generations'">{{ generationCache[scene.id]?.length ?? scene.generation_count ?? 0 }}</template>
                    <template v-else-if="lane.id === 'chat'">⌁</template>
                    <template v-else>{{ itemsForLane(lane.id).length }}</template>
                  </span>
                  <span class="min-w-0 truncate text-xs">{{ lane.id === 'chat' ? (chatCache[scene.id] ? 'Ouvrir' : 'Associer') : lane.action }}</span>
                </button>
              </td>

              <td class="px-3 py-2.5 align-top">
                <button
                  type="button"
                  class="flex min-h-10 w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-content-secondary outline-none transition-colors hover:bg-overlay-faint focus-visible:ring-2 focus-visible:ring-accent"
                  :class="activeSceneId === scene.id && activeLane === 'continuity' ? 'bg-accent/10 text-accent' : ''"
                  @click="selectScene(scene, 'continuity')"
                >
                  <span class="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-overlay-faint text-[12px]">{{ continuityCache[scene.id]?.last_frame ? '↳' : '—' }}</span>
                  <span class="min-w-0 truncate">{{ continuityCache[scene.id]?.last_frame ? 'Dernière frame' : 'En attente' }}</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <Transition name="scene-detail" mode="out-in">
        <section v-if="activeScene" :key="activeScene.id" class="overflow-hidden rounded-xl border border-accent/20 bg-surface shadow-sm">
          <header class="flex flex-wrap items-center justify-between gap-3 border-b border-edge-subtle bg-surface-raised/40 px-4 py-3">
            <div class="flex min-w-0 items-center gap-3">
              <span class="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-accent/10 font-mono text-xs font-semibold text-accent">S{{ activeScene.scene_number }}</span>
              <div class="min-w-0">
                <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-content-tertiary">Scène sélectionnée</p>
                <h3 class="truncate text-sm font-semibold text-content">{{ activeScene.title }}</h3>
              </div>
            </div>
            <span class="text-[11px] text-content-muted">Les contenus changent ici, dans le board</span>
          </header>

          <div class="border-b border-edge-subtle px-3 py-2">
            <nav class="flex gap-1 overflow-x-auto" aria-label="Contenu de la scène">
              <button
                v-for="tab in detailTabs"
                :key="tab.id"
                type="button"
                class="flex-none rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                :class="activeLane === tab.id ? 'bg-accent text-on-accent' : 'text-content-muted hover:bg-overlay-faint hover:text-content'"
                @click="selectLane(tab.id)"
              >
                {{ tab.label }}
              </button>
            </nav>
          </div>

          <div class="p-4">
            <div v-if="activeLane === 'brief'" class="space-y-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-accent">Brief de scène</p>
                  <h4 class="mt-1 text-base font-semibold tracking-tight text-content">{{ activeScene.title }}</h4>
                  <p class="mt-1 text-xs text-content-muted">
                    {{ briefMap.rows.length ? `${briefMap.rows.length} plans structurés` : 'Brief non structuré' }}
                    <span v-if="briefMap.summary"> · {{ briefMap.summary }}</span>
                  </p>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="briefSaveState[activeScene.id] === 'saved'" class="text-xs text-accent" role="status">Enregistré</span>
                  <span v-else-if="isBriefDirty(activeScene)" class="text-xs text-amber-500">Non enregistré</span>
                  <button type="button" class="rounded-md border border-edge-subtle px-2.5 py-1.5 text-xs font-medium text-content-secondary transition-colors hover:bg-overlay-faint hover:text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="showBriefEditor = !showBriefEditor">
                    {{ showBriefEditor ? 'Fermer l’éditeur' : 'Modifier le brief' }}
                  </button>
                </div>
              </div>

              <div v-if="showBriefEditor" class="rounded-lg border border-accent/20 bg-accent/[0.035] p-3">
                <textarea
                  v-model="briefDrafts[activeScene.id]"
                  class="min-h-40 w-full resize-y rounded-md border border-edge bg-base px-3 py-2.5 font-mono text-xs leading-5 text-content outline-none transition-colors focus:border-accent"
                  :aria-label="`Modifier le brief de ${activeScene.title}`"
                  :disabled="!projectId || briefSaveState[activeScene.id] === 'saving'"
                  @input="briefSaveState[activeScene.id] = 'dirty'"
                  @keydown.meta.enter.prevent="saveBrief(activeScene)"
                  @keydown.ctrl.enter.prevent="saveBrief(activeScene)"
                />
                <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <span class="text-[11px] text-content-muted">Source Markdown · ⌘↵ pour enregistrer</span>
                  <button type="button" class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-on-accent transition-opacity disabled:cursor-not-allowed disabled:opacity-40" :disabled="!projectId || !isBriefDirty(activeScene) || briefSaveState[activeScene.id] === 'saving'" @click="saveBrief(activeScene)">
                    {{ briefSaveState[activeScene.id] === 'saving' ? 'Enregistrement…' : 'Enregistrer' }}
                  </button>
                </div>
                <p v-if="briefSaveState[activeScene.id] === 'error'" class="mt-2 text-xs text-red-400" role="alert">Impossible d’enregistrer le brief.</p>
              </div>

              <div v-if="briefMap.rows.length" class="overflow-hidden rounded-lg border border-edge-subtle">
                <div class="flex items-center justify-between border-b border-edge-subtle bg-surface-raised/35 px-3 py-2.5">
                  <div>
                    <p class="text-xs font-semibold text-content">Shot map</p>
                    <p class="mt-0.5 text-[10px] text-content-muted">Clique sur un plan pour afficher son détail.</p>
                  </div>
                  <span class="rounded-full bg-overlay-faint px-2 py-1 font-mono text-[10px] text-content-tertiary">{{ briefMap.rows.length }} lignes</span>
                </div>
                <div class="max-h-[440px] overflow-auto">
                  <table class="w-full min-w-[760px] border-collapse text-left">
                    <thead class="sticky top-0 z-10 bg-surface">
                      <tr class="border-b border-edge-subtle">
                        <th v-for="(column, columnIndex) in briefMap.columns.slice(0, 5)" :key="`${column}-${columnIndex}`" class="max-w-[220px] px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-content-tertiary">
                          {{ column || `Colonne ${columnIndex + 1}` }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(row, rowIndex) in briefMap.rows"
                        :key="`brief-row-${rowIndex}`"
                        class="cursor-pointer border-b border-edge-subtle/70 transition-colors last:border-b-0 hover:bg-overlay-faint focus:bg-overlay-faint focus:outline-none"
                        :class="selectedBriefRowIndex === rowIndex ? 'bg-accent/[0.07]' : ''"
                        tabindex="0"
                        role="button"
                        @click="selectBriefRow(rowIndex)"
                        @keydown.enter.prevent="selectBriefRow(rowIndex)"
                        @keydown.space.prevent="selectBriefRow(rowIndex)"
                      >
                        <td v-for="(value, columnIndex) in row.values.slice(0, 5)" :key="`${rowIndex}-${columnIndex}`" class="max-w-[220px] px-3 py-2 align-top text-xs text-content-secondary">
                          <div class="line-clamp-2 leading-4">{{ cleanInline(value) || '—' }}</div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div v-else class="rounded-lg border border-dashed border-edge-subtle px-4 py-7 text-center">
                <p class="text-sm font-medium text-content">Brief à structurer</p>
                <p class="mt-1 text-xs leading-5 text-content-muted">Ajoute un tableau Markdown au brief pour obtenir une vue plan par plan.</p>
              </div>

              <div v-if="selectedBriefRow" class="rounded-lg border border-accent/15 bg-accent/[0.035] p-3">
                <div class="flex items-center justify-between gap-2">
                  <div>
                    <p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-accent">Plan {{ selectedBriefRow.values[0] || selectedBriefRowIndex + 1 }}</p>
                    <p class="mt-1 text-xs text-content-muted">Détail extrait du shot map</p>
                  </div>
                  <button type="button" class="text-xs text-content-muted hover:text-content" @click="selectedBriefRowIndex = null">Fermer</button>
                </div>
                <dl class="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                  <div v-for="(value, index) in selectedBriefRow.values" :key="`selected-field-${index}`" class="min-w-0">
                    <dt class="text-[10px] font-semibold uppercase tracking-[0.08em] text-content-tertiary">{{ briefMap.columns[index] || `Colonne ${index + 1}` }}</dt>
                    <dd class="mt-0.5 whitespace-pre-wrap text-xs leading-5 text-content-secondary">{{ cleanInline(value) || '—' }}</dd>
                  </div>
                </dl>
              </div>
            </div>

            <div v-else-if="['assets', 'references', 'variants'].includes(activeLane)">
              <div class="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-accent">{{ laneLabel(activeLane) }}</p>
                  <h4 class="mt-1 text-sm font-semibold text-content">Ressources disponibles pour préparer la scène</h4>
                </div>
                <span class="font-mono text-[11px] text-content-tertiary">{{ itemsForLane(activeLane).length }} élément{{ itemsForLane(activeLane).length === 1 ? '' : 's' }}</span>
              </div>
              <div v-if="itemsForLane(activeLane).length" class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                <div v-for="item in itemsForLane(activeLane)" :key="`${activeLane}-${item.media_id || item.id}`" class="group overflow-hidden rounded-lg border border-edge-subtle bg-matte">
                  <div class="aspect-square">
                    <MediaImage :media-id="mediaIdOf(item)" :file-hash="item.file_hash" :file-format="item.file_format" :is-video="isVideo(item)" thumbnail thumbnail-mode="fit" :thumbnail-size="256" :contain="true" :alt="item.original_filename || 'Asset'" :enable-context-menu="false" container-class="h-full w-full" img-class="h-full w-full object-contain" />
                  </div>
                  <p class="truncate px-2 py-1.5 text-[10px] text-content-muted">{{ item.original_filename || `Asset ${mediaIdOf(item)}` }}</p>
                </div>
              </div>
              <div v-else class="mt-3 rounded-lg border border-dashed border-edge-subtle px-4 py-7 text-center text-xs text-content-muted">Aucun élément dans cette colonne pour le moment.</div>
            </div>

            <div v-else-if="activeLane === 'generations'">
              <div class="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-accent">Générations</p>
                  <h4 class="mt-1 text-sm font-semibold text-content">Essais liés à cette scène</h4>
                </div>
                <button type="button" class="text-xs font-medium text-accent hover:underline" @click="loadGenerations(activeScene, true)">Actualiser</button>
              </div>
              <div v-if="generationLoading[activeScene.id]" class="mt-3 grid gap-2 sm:grid-cols-2">
                <div v-for="item in 2" :key="item" class="h-24 animate-pulse rounded-lg border border-edge-subtle bg-overlay-faint" />
              </div>
              <div v-else-if="generationError[activeScene.id]" class="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-3 text-xs text-red-400" role="alert">{{ generationError[activeScene.id] }}</div>
              <div v-else-if="!generationCache[activeScene.id]?.length" class="mt-3 rounded-lg border border-dashed border-edge-subtle px-4 py-7 text-center text-xs text-content-muted">Aucun essai pour l’instant. Les générations lancées depuis le chat de cette scène apparaîtront ici.</div>
              <div v-else class="mt-3 grid gap-2 sm:grid-cols-2">
                <article v-for="generation in generationCache[activeScene.id]" :key="generation.id" class="flex gap-3 rounded-lg border border-edge-subtle bg-surface-raised/25 p-2.5">
                  <div class="h-16 w-20 flex-none overflow-hidden rounded-md bg-matte">
                    <MediaImage v-if="generation.result_media_id && !generation.media_deleted" :media-id="generation.result_media_id" :file-hash="generation.result_file_hash" :file-format="generation.result_file_format" :is-video="isVideoGeneration(generation)" thumbnail thumbnail-mode="fit" :thumbnail-size="256" :contain="true" :alt="`Résultat ${generation.id}`" :enable-context-menu="false" container-class="h-full w-full" img-class="h-full w-full object-contain" />
                    <div v-else class="flex h-full items-center justify-center text-[10px] text-content-tertiary">{{ statusLabel(generation.status) }}</div>
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <p class="text-xs font-semibold text-content">#{{ generation.id }} · {{ generation.model_name || 'Modèle' }}</p>
                        <p class="mt-1 text-[10px] text-content-muted">{{ formatDate(generation.created_at) }}</p>
                      </div>
                      <span class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold" :class="statusClass(generation.status)">{{ statusLabel(generation.status) }}</span>
                    </div>
                    <p v-if="generation.prompt" class="mt-2 line-clamp-2 text-[10px] leading-4 text-content-secondary">{{ generation.prompt }}</p>
                  </div>
                </article>
              </div>
            </div>

            <div v-else-if="activeLane === 'chat'" class="flex flex-col items-start justify-between gap-4 rounded-lg border border-accent/15 bg-accent/[0.035] p-4 sm:flex-row sm:items-center">
              <div>
                <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-accent">Chat associé</p>
                <h4 class="mt-1 text-sm font-semibold text-content">Un fil dédié aux décisions de {{ activeScene.title }}</h4>
                <p class="mt-1 max-w-xl text-xs leading-5 text-content-muted">Le contexte de la scène et le raccord précédent sont injectés automatiquement dans ce chat.</p>
                <p v-if="chatError[activeScene.id]" class="mt-2 text-xs text-red-400" role="alert">{{ chatError[activeScene.id] }}</p>
              </div>
              <button type="button" class="flex-none rounded-md bg-accent px-3 py-2 text-xs font-medium text-on-accent transition-opacity disabled:cursor-not-allowed disabled:opacity-50" :disabled="chatLoading[activeScene.id]" @click="openSceneChat(activeScene)">
                {{ chatLoading[activeScene.id] ? 'Ouverture…' : (chatCache[activeScene.id] ? 'Ouvrir le chat' : 'Créer le chat') }}
              </button>
            </div>

            <div v-else-if="activeLane === 'continuity'">
              <div class="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-accent">Raccord automatique</p>
                  <h4 class="mt-1 text-sm font-semibold text-content">Dernière frame de la scène précédente</h4>
                </div>
                <span v-if="continuityLoading[activeScene.id]" class="text-[11px] text-content-muted">Extraction…</span>
              </div>
              <div v-if="continuityError[activeScene.id]" class="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-3 text-xs text-red-400" role="alert">{{ continuityError[activeScene.id] }}</div>
              <div v-else-if="continuityCache[activeScene.id]?.last_frame" class="mt-3 grid gap-4 md:grid-cols-[240px_minmax(0,1fr)]">
                <div class="overflow-hidden rounded-lg border border-edge-subtle bg-matte">
                  <img :src="continuityFrameUrl(activeScene)" :alt="`Dernière frame de ${continuityCache[activeScene.id].previous_scene.title}`" class="aspect-video h-full w-full object-contain" loading="lazy" />
                </div>
                <div class="self-center">
                  <p class="text-xs text-content-muted">Extrait depuis</p>
                  <p class="mt-1 text-sm font-semibold text-content">S{{ continuityCache[activeScene.id].previous_scene.scene_number }} · {{ continuityCache[activeScene.id].previous_scene.title }}</p>
                  <p class="mt-2 text-xs leading-5 text-content-secondary">Cette image est disponible comme contexte de raccord pour la scène sélectionnée et son chat associé.</p>
                  <span class="mt-3 inline-flex rounded-full bg-accent/10 px-2 py-1 text-[10px] font-medium text-accent">{{ continuityCache[activeScene.id].last_frame.extracted ? 'Frame vidéo extraite automatiquement' : 'Image de référence précédente' }}</span>
                </div>
              </div>
              <div v-else class="mt-3 rounded-lg border border-dashed border-edge-subtle px-4 py-7 text-center text-xs text-content-muted">La scène précédente n’a pas encore de rendu terminé à utiliser comme raccord.</div>
            </div>
          </div>
        </section>
      </Transition>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { MediaImage } from './media'
import { useProjectDirectionApi } from '../composables/useProjectDirectionApi'
import { useToasts } from '../composables/useToasts'
import { getApiBase } from '../apiConfig'

const props = defineProps({
  scenes: { type: Array, default: () => [] },
  sections: { type: Array, default: () => [] },
  projectId: { type: Number, default: null }
})

const emit = defineEmits(['scene-updated'])
const router = useRouter()
const { getSceneGenerations, getSceneContinuity, updateScene, createSceneChat } = useProjectDirectionApi()
const { addToast } = useToasts()

const lanes = [
  { id: 'assets', label: 'Assets', action: 'Préparer' },
  { id: 'references', label: 'Références', action: 'Consulter' },
  { id: 'variants', label: 'Variantes', action: 'Explorer' },
  { id: 'generations', label: 'Générations', action: 'Voir les essais' },
  { id: 'chat', label: 'Chat', action: 'Ouvrir' }
]
const detailTabs = [
  { id: 'brief', label: 'Brief' },
  ...lanes.map(({ id, label }) => ({ id, label })),
  { id: 'continuity', label: 'Raccord' }
]

const scenes = computed(() => props.scenes || [])
const activeSceneId = ref(scenes.value[0]?.id || null)
const activeLane = ref('brief')
const showBriefEditor = ref(false)
const selectedBriefRowIndex = ref(null)
const briefDrafts = reactive({})
const briefSaveState = reactive({})
const generationCache = reactive({})
const generationLoading = reactive({})
const generationError = reactive({})
const continuityCache = reactive({})
const continuityLoading = reactive({})
const continuityError = reactive({})
const chatCache = reactive({})
const chatLoading = reactive({})
const chatError = reactive({})
const generationRequestTokens = reactive({})

const activeScene = computed(() => scenes.value.find((scene) => scene.id === activeSceneId.value) || null)
const parsedBriefs = computed(() => Object.fromEntries(scenes.value.map((scene) => [scene.id, parseSceneBrief(scene.description)])))
const briefMap = computed(() => {
  const parsed = parseSceneBrief(activeScene.value?.description || '')
  const codeIndex = parsed.columns.findIndex((column) => /^code$/i.test(cleanInline(column)))
  return {
    ...parsed,
    columns: parsed.columns.filter((_, index) => index !== codeIndex),
    rows: parsed.rows.map((row) => ({
      ...row,
      values: row.values.filter((_, index) => index !== codeIndex)
    }))
  }
})
const selectedBriefRow = computed(() => {
  if (selectedBriefRowIndex.value == null) return null
  return briefMap.value.rows[selectedBriefRowIndex.value] || null
})
const totalGenerationCount = computed(() => scenes.value.reduce((sum, scene) => sum + (generationCache[scene.id]?.length ?? scene.generation_count ?? 0), 0))

function syncDrafts() {
  for (const scene of scenes.value) {
    if (!Object.hasOwn(briefDrafts, scene.id) || !['dirty', 'saving'].includes(briefSaveState[scene.id])) {
      briefDrafts[scene.id] = scene.description || ''
      briefSaveState[scene.id] = briefSaveState[scene.id] === 'saved' ? 'saved' : 'idle'
    }
  }
  if (!activeSceneId.value && scenes.value.length) activeSceneId.value = scenes.value[0].id
}

watch(() => scenes.value.map((scene) => `${scene.id}:${scene.description || ''}`), syncDrafts, { immediate: true })
watch(activeSceneId, () => {
  selectedBriefRowIndex.value = null
  showBriefEditor.value = false
})

function normalize(value) {
  return String(value || '').trim().toLowerCase()
}

function sectionMatches(section, pattern) {
  return pattern.test(normalize(section?.name))
}

function itemsForLane(lane) {
  const sections = props.sections || []
  const matching = sections.filter((section) => {
    if (lane === 'references') return sectionMatches(section, /reference|référence|ref/)
    if (lane === 'variants') return sectionMatches(section, /variant|option|essai/)
    if (lane === 'assets') return sectionMatches(section, /asset|approved|final|deliverable|livrable|default/)
    return false
  })
  const fallback = lane === 'assets' && !matching.length
    ? sections.filter((section) => !sectionMatches(section, /brief|reference|référence|ref|variant|option|essai/))
    : matching
  const seen = new Set()
  return fallback.flatMap((section) => section.items || []).filter((item) => {
    const key = mediaIdOf(item)
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function mediaIdOf(item) {
  return item?.media_id || (typeof item?.id === 'number' ? item.id : null)
}

function isVideo(item) {
  return /video|mp4|webm|mov|avi|mkv|ogg/i.test(`${item?.file_format || ''}`)
}

function briefPreview(scene) {
  return parsedBriefs.value[scene.id] || { summary: '', fields: [] }
}

function cleanInline(value) {
  return String(value || '')
    .replace(/<br\s*\/?>(\s*)/gi, ' ')
    .replace(/<[^>]+>/g, '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/[`*_~]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function tokenText(token) {
  if (!token) return ''
  if (Array.isArray(token.tokens)) return token.tokens.map(tokenText).join('')
  return token.text || token.raw || ''
}

function parseSceneBrief(source) {
  const text = String(source || '').trim()
  if (!text) return { summary: '', columns: [], rows: [], fields: [] }
  try {
    const tokens = marked.lexer(text)
    const paragraph = tokens.find((token) => token.type === 'paragraph')
    const heading = tokens.find((token) => token.type === 'heading')
    const table = tokens.find((token) => token.type === 'table' && token.rows?.length)
    const headers = table?.header?.map((cell) => cleanInline(tokenText(cell))) || []
    const rows = table?.rows?.map((row) => ({ values: row.map((cell) => cleanInline(tokenText(cell))) })).filter((row) => row.values.some(Boolean)) || []
    const firstRow = rows.find((row) => row.values.some(Boolean)) || { values: [] }
    const preferredIndex = headers.findIndex((header) => /plan|texte|description|action|shot/i.test(header))
    const summary = cleanInline(tokenText(paragraph)) || cleanInline(tokenText(heading)) || cleanInline(firstRow.values?.[preferredIndex >= 0 ? preferredIndex : 0]) || cleanInline(text.split(/\n+/).find(Boolean))
    return { summary, columns: headers, rows, fields: headers.map((label, index) => ({ label, value: firstRow.values?.[index] || '' })).filter((field) => field.label && field.value).slice(0, 4) }
  } catch (error) {
    return { summary: cleanInline(text), columns: [], rows: [], fields: [] }
  }
}

function isBriefDirty(scene) {
  return (briefDrafts[scene.id] || '') !== (scene.description || '')
}

function selectBriefRow(rowIndex) {
  selectedBriefRowIndex.value = selectedBriefRowIndex.value === rowIndex ? null : rowIndex
}

async function saveBrief(scene) {
  if (!props.projectId || !isBriefDirty(scene)) return
  briefSaveState[scene.id] = 'saving'
  try {
    const updated = await updateScene(props.projectId, scene.id, { description: briefDrafts[scene.id] || '' })
    briefDrafts[scene.id] = updated.description || ''
    briefSaveState[scene.id] = 'saved'
    emit('scene-updated', updated)
  } catch (error) {
    console.error('[SceneBriefPanel] Failed to save scene brief:', error)
    briefSaveState[scene.id] = 'error'
    addToast('Impossible d’enregistrer le brief', 'error', 5000)
  }
}

async function selectScene(scene, lane = activeLane.value) {
  activeSceneId.value = scene.id
  activeLane.value = lane
  await Promise.all([loadGenerations(scene), loadContinuity(scene)])
  if (lane === 'chat') await ensureChat(scene)
}

function selectLane(lane) {
  activeLane.value = lane
  if (!activeScene.value) return
  if (lane === 'generations') loadGenerations(activeScene.value)
  if (lane === 'continuity') loadContinuity(activeScene.value)
  if (lane === 'chat') ensureChat(activeScene.value)
}

async function loadGenerations(scene, force = false) {
  if (!props.projectId || (!force && Object.hasOwn(generationCache, scene.id))) return
  const token = (generationRequestTokens[scene.id] || 0) + 1
  generationRequestTokens[scene.id] = token
  generationLoading[scene.id] = true
  generationError[scene.id] = ''
  try {
    const payload = await getSceneGenerations(props.projectId, scene.id)
    if (generationRequestTokens[scene.id] === token) generationCache[scene.id] = payload.generations || []
  } catch (error) {
    if (generationRequestTokens[scene.id] === token) generationError[scene.id] = error.response?.data?.detail || 'Impossible de charger les générations.'
  } finally {
    if (generationRequestTokens[scene.id] === token) generationLoading[scene.id] = false
  }
}

async function loadContinuity(scene, force = false) {
  if (!props.projectId || (!force && Object.hasOwn(continuityCache, scene.id))) return
  continuityLoading[scene.id] = true
  continuityError[scene.id] = ''
  try {
    continuityCache[scene.id] = await getSceneContinuity(props.projectId, scene.id)
  } catch (error) {
    continuityError[scene.id] = error.response?.data?.detail || 'Impossible de charger le raccord.'
  } finally {
    continuityLoading[scene.id] = false
  }
}

async function ensureChat(scene) {
  if (!props.projectId || chatCache[scene.id] || chatLoading[scene.id]) return chatCache[scene.id]
  chatLoading[scene.id] = true
  chatError[scene.id] = ''
  try {
    chatCache[scene.id] = await createSceneChat(props.projectId, scene.id)
    return chatCache[scene.id]
  } catch (error) {
    chatError[scene.id] = error.response?.data?.detail || 'Impossible de préparer le chat.'
    return null
  } finally {
    chatLoading[scene.id] = false
  }
}

async function openSceneChat(scene) {
  const chat = await ensureChat(scene)
  if (chat?.chat_id) router.push({ name: 'chat', params: { id: chat.chat_id } })
}

function continuityFrameUrl(scene) {
  const path = continuityCache[scene.id]?.last_frame?.frame_url
  return path ? `${getApiBase()}${path}` : ''
}

function laneLabel(lane) {
  return lanes.find((entry) => entry.id === lane)?.label || lane
}

function isVideoGeneration(generation) {
  return /video|mp4|webm|mov|avi|mkv/i.test(`${generation.task_type || ''} ${generation.result_file_format || ''}`)
}

function statusLabel(status) {
  return { queued: 'En file', assigned: 'Assignée', processing: 'En cours', running: 'En cours', completed: 'Terminée', failed: 'Échec', cancelled: 'Annulée' }[status] || status || 'Inconnue'
}

function statusClass(status) {
  if (status === 'completed') return 'bg-emerald-500/10 text-emerald-400'
  if (['failed', 'cancelled'].includes(status)) return 'bg-red-500/10 text-red-400'
  if (['processing', 'running'].includes(status)) return 'bg-accent/10 text-accent'
  return 'bg-overlay-faint text-content-secondary'
}

function formatDate(value) {
  if (!value) return 'Date inconnue'
  try { return new Date(value).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) } catch (error) { return 'Date inconnue' }
}
</script>

<style scoped>
.scene-detail-enter-active,
.scene-detail-leave-active {
  transition: opacity 160ms ease, transform 180ms ease;
}

.scene-detail-enter-from,
.scene-detail-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

</style>
