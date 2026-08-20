<template>
  <div class="h-full overflow-y-auto bg-base custom-scrollbar">
    <main class="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <!-- Header Banner & Stats -->
      <header class="relative overflow-hidden rounded-2xl border border-edge bg-surface p-6 shadow-sm">
        <div class="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div class="space-y-1.5 min-w-0">
            <div class="flex items-center gap-2">
              <span class="inline-flex items-center gap-1.5 rounded-full bg-accent/15 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-accent">
                <FilmIcon class="w-3.5 h-3.5" />
                Script
              </span>
              <span v-if="direction?.script_name" class="truncate text-xs font-medium text-content-muted">
                {{ direction.script_name }}
              </span>
            </div>
            <h1 class="text-2xl font-bold tracking-tight text-content">
              Script, séquences et continuité
            </h1>
            <p class="text-sm text-content-secondary max-w-2xl leading-relaxed">
              Source de vérité directrice connectée aux boards, chats, contextes IA et générations du projet.
            </p>
          </div>

          <!-- Quick Actions -->
          <div class="flex flex-wrap items-center gap-2.5 flex-shrink-0">
            <button
              v-if="direction?.scenes?.length"
              type="button"
              class="inline-flex items-center gap-2 rounded-lg border border-edge bg-surface-raised px-3.5 py-2 text-xs font-medium text-content-secondary hover:text-content hover:bg-overlay-light transition-colors"
              title="Voir et modifier le script complet"
              @click="openScriptModal"
            >
              <DocumentTextIcon class="w-4 h-4" />
              Script source
            </button>

            <button
              v-if="direction?.scenes?.length"
              type="button"
              class="inline-flex items-center gap-2 rounded-lg border border-edge bg-surface-raised px-3.5 py-2 text-xs font-medium text-content-secondary hover:text-content hover:bg-overlay-light transition-colors"
              title="Réimporter un nouveau script"
              @click="showImportSection = !showImportSection"
            >
              <ArrowPathIcon class="w-4 h-4" />
              {{ showImportSection ? 'Masquer import' : 'Réimporter' }}
            </button>

            <button
              type="button"
              class="inline-flex items-center justify-center p-2 rounded-lg border border-edge bg-surface-raised text-content-muted hover:text-content hover:bg-overlay-light transition-colors"
              title="Actualiser la direction"
              @click="load"
            >
              <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': loading }" />
            </button>
          </div>
        </div>

        <!-- Metrics KPI Cards -->
        <div v-if="direction?.progress" class="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 border-t border-edge-subtle pt-5">
          <!-- Total Sequences -->
          <div class="rounded-xl border border-edge-subtle bg-base/50 p-3.5">
            <div class="text-xs text-content-muted font-medium">Séquences totales</div>
            <div class="mt-1 flex items-baseline gap-1.5">
              <span class="text-xl font-bold text-content">{{ direction.progress.total }}</span>
              <span class="text-xs text-content-muted">séquences</span>
            </div>
          </div>

          <!-- Validated Progress -->
          <div class="rounded-xl border border-edge-subtle bg-base/50 p-3.5">
            <div class="flex items-center justify-between text-xs text-content-muted font-medium">
              <span>Validées</span>
              <span class="text-[11px] font-semibold text-emerald-500">{{ validatedPercent }}%</span>
            </div>
            <div class="mt-1 flex items-baseline gap-1.5">
              <span class="text-xl font-bold text-content">{{ direction.progress.validated }}</span>
              <span class="text-xs text-content-muted">/ {{ direction.progress.total }}</span>
            </div>
            <div class="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-overlay-subtle">
              <div
                class="h-full rounded-full bg-emerald-500 transition-all duration-500"
                :style="{ width: `${validatedPercent}%` }"
              />
            </div>
          </div>

          <!-- Total Generations -->
          <div class="rounded-xl border border-edge-subtle bg-base/50 p-3.5">
            <div class="text-xs text-content-muted font-medium">Générations</div>
            <div class="mt-1 flex items-baseline gap-1.5">
              <span class="text-xl font-bold text-content">{{ direction.progress.generated }}</span>
              <span class="text-xs text-content-muted">variantes</span>
            </div>
          </div>

          <!-- Blockers -->
          <div
            class="rounded-xl border p-3.5 transition-colors"
            :class="direction.progress.blocked > 0
              ? 'border-amber-500/40 bg-amber-500/[0.06]'
              : 'border-edge-subtle bg-base/50'"
          >
            <div class="text-xs font-medium" :class="direction.progress.blocked > 0 ? 'text-amber-500' : 'text-content-muted'">
              Blocages
            </div>
            <div class="mt-1 flex items-baseline gap-1.5">
              <span class="text-xl font-bold" :class="direction.progress.blocked > 0 ? 'text-amber-500' : 'text-content'">
                {{ direction.progress.blocked }}
              </span>
              <span class="text-xs text-content-muted">bloquée(s)</span>
            </div>
          </div>
        </div>
      </header>

      <details
        v-if="direction?.script_directives"
        class="rounded-2xl border border-accent/20 bg-accent/[0.04] shadow-sm"
      >
        <summary class="cursor-pointer list-none px-5 py-4 text-sm font-semibold text-content">
          Instructions globales du script
          <span class="ml-2 text-xs font-normal text-content-muted">hors séquences et plans</span>
        </summary>
        <div class="border-t border-accent/15 px-5 py-4">
          <pre class="whitespace-pre-wrap font-sans text-xs leading-relaxed text-content-secondary">{{ direction.script_directives }}</pre>
        </div>
      </details>

      <!-- Re-import / Script Import Section -->
      <section
        v-if="!direction?.scenes?.length || showImportSection"
        class="rounded-2xl border border-edge bg-surface p-6 shadow-sm space-y-4"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold text-content">
              {{ direction?.scenes?.length ? 'Remplacer ou réimporter un script' : 'Importer un script de départ' }}
            </h2>
            <p class="mt-1 text-sm text-content-secondary leading-relaxed">
              Les en-têtes <code class="text-xs bg-overlay-subtle px-1.5 py-0.5 rounded text-accent font-mono">SÉQUENCE</code>,
              <code class="text-xs bg-overlay-subtle px-1.5 py-0.5 rounded text-accent font-mono">SCÈNE</code>,
              <code class="text-xs bg-overlay-subtle px-1.5 py-0.5 rounded text-accent font-mono">INT.</code> ou
              <code class="text-xs bg-overlay-subtle px-1.5 py-0.5 rounded text-accent font-mono">EXT.</code>
              découpent automatiquement le document en scènes et configurent les boards associés.
            </p>
          </div>

          <button
            type="button"
            class="text-xs font-medium text-accent hover:underline flex-shrink-0"
            @click="loadSampleScript"
          >
            Insérer un exemple
          </button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-content-secondary mb-1">Nom du script (facultatif)</label>
            <input
              v-model="scriptName"
              type="text"
              class="w-full rounded-lg border border-edge bg-base px-3.5 py-2 text-sm text-content placeholder:text-content-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
              placeholder="ex. Court-métrage — Version 1.0"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-content-secondary mb-1">Texte du script / Scénario</label>
            <textarea
              v-model="script"
              rows="8"
              class="w-full rounded-lg border border-edge bg-base px-3.5 py-2.5 font-mono text-sm leading-relaxed text-content placeholder:text-content-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40 resize-y"
              placeholder="SÉQUENCE 1&#10;SCÈNE 1 — Découverte de la cité&#10;EXT. RUE ANCIENNE - NUIT&#10;Une silhouette avance sous une pluie fine..."
            />
          </div>
        </div>

        <div class="flex items-center justify-between pt-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!script.trim() || saving"
            @click="submitImport"
          >
            <ArrowPathIcon v-if="saving" class="w-4 h-4 animate-spin" />
            <SparklesIcon v-else class="w-4 h-4" />
            <span>{{ saving ? 'Traitement du script…' : 'Générer la direction' }}</span>
          </button>

          <button
            v-if="direction?.scenes?.length && showImportSection"
            type="button"
            class="text-xs text-content-muted hover:text-content"
            @click="showImportSection = false"
          >
            Annuler
          </button>
        </div>
      </section>

      <!-- Filter & Search Toolbar (when scenes exist) -->
      <div v-if="direction?.scenes?.length" class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <!-- Search bar -->
        <div class="relative flex-1 max-w-md">
          <MagnifyingGlassIcon class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
          <input
            v-model="searchFilter"
            type="search"
            placeholder="Filtrer les scènes par titre, description ou prompt..."
            class="w-full rounded-lg border border-edge bg-surface pl-9 pr-3.5 py-2 text-xs text-content placeholder:text-content-muted focus:border-accent focus:outline-none"
          />
        </div>

        <!-- Filter chips -->
        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <button
            type="button"
            class="rounded-lg px-2.5 py-1.5 transition-colors font-medium"
            :class="statusFilter === 'all'
              ? 'bg-accent/15 text-accent border border-accent/30'
              : 'bg-surface text-content-muted hover:text-content border border-edge'"
            @click="statusFilter = 'all'"
          >
            Toutes ({{ direction.scenes.length }})
          </button>
          <button
            type="button"
            class="rounded-lg px-2.5 py-1.5 transition-colors font-medium"
            :class="statusFilter === 'in_progress'
              ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
              : 'bg-surface text-content-muted hover:text-content border border-edge'"
            @click="statusFilter = 'in_progress'"
          >
            En cours
          </button>
          <button
            type="button"
            class="rounded-lg px-2.5 py-1.5 transition-colors font-medium"
            :class="statusFilter === 'ready_for_review'
              ? 'bg-purple-500/15 text-purple-400 border border-purple-500/30'
              : 'bg-surface text-content-muted hover:text-content border border-edge'"
            @click="statusFilter = 'ready_for_review'"
          >
            À valider
          </button>
          <button
            type="button"
            class="rounded-lg px-2.5 py-1.5 transition-colors font-medium"
            :class="statusFilter === 'complete'
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
              : 'bg-surface text-content-muted hover:text-content border border-edge'"
            @click="statusFilter = 'complete'"
          >
            Terminées
          </button>
          <button
            type="button"
            class="rounded-lg px-2.5 py-1.5 transition-colors font-medium"
            :class="statusFilter === 'blocked'
              ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
              : 'bg-surface text-content-muted hover:text-content border border-edge'"
            @click="statusFilter = 'blocked'"
          >
            Bloquées ({{ direction.progress.blocked }})
          </button>
        </div>
      </div>

      <!-- Scene Cards List -->
      <section v-if="direction?.scenes?.length" class="space-y-4">
        <div v-if="filteredScenes.length === 0" class="rounded-xl border border-edge bg-surface p-8 text-center text-content-muted">
          <p class="text-sm">Aucune scène ne correspond aux critères de recherche.</p>
        </div>

        <article
          v-for="scene in filteredScenes"
          :key="scene.id"
          class="rounded-xl border border-edge bg-surface p-5 shadow-sm hover:border-edge-strong transition-all space-y-4"
        >
          <!-- Scene Card Header -->
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="space-y-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center rounded-md bg-overlay-subtle px-2 py-0.5 font-mono text-[11px] font-semibold text-content-secondary uppercase">
                  S{{ scene.sequence_number }} · Scène {{ scene.scene_number }}
                </span>

                <!-- Status Badge -->
                <span
                  class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border"
                  :class="statusBadgeClass(scene.status)"
                >
                  <span class="w-1.5 h-1.5 rounded-full" :class="statusDotClass(scene.status)" />
                  {{ statusLabel(scene.status) }}
                </span>

                <!-- Validation Badge -->
                <span
                  class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border"
                  :class="validationBadgeClass(scene.validation_status)"
                >
                  {{ validationLabel(scene.validation_status) }}
                </span>
              </div>

              <h2 class="text-base font-semibold text-content pt-0.5">
                {{ scene.title }}
              </h2>
            </div>

            <!-- Card Actions -->
            <div class="flex items-center gap-2 flex-shrink-0">
              <a
                v-if="scene.board_id"
                :href="`#/boards/${scene.board_id}`"
                class="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-surface-raised px-3 py-1.5 text-xs font-medium text-content-secondary hover:text-content hover:bg-overlay-light transition-colors"
                title="Accéder au board de la scène"
              >
                <ViewColumnsIcon class="w-3.5 h-3.5" />
                Board
              </a>

              <button
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors disabled:opacity-50"
                :disabled="openingChatId === scene.id"
                @click="openChat(scene)"
              >
                <ChatBubbleLeftRightIcon class="w-3.5 h-3.5" />
                {{ openingChatId === scene.id ? 'Ouverture…' : 'Ouvrir le chat' }}
              </button>
            </div>
          </div>

          <!-- Scene Description / Screenplay excerpt -->
          <div v-if="scene.description" class="rounded-lg border-l-2 border-accent/40 bg-surface-raised/40 p-3 text-xs leading-relaxed text-content-secondary">
            <p class="whitespace-pre-wrap font-sans">{{ scene.description }}</p>
          </div>

          <div v-if="scene.shots?.length" class="rounded-lg border border-edge-subtle bg-base/40 p-3">
            <div class="mb-2 flex items-center justify-between">
              <div>
                <h3 class="text-xs font-semibold text-content">Plans individuels</h3>
                <p class="mt-0.5 text-[11px] text-content-muted">{{ scene.shots.length }} plan(s) canoniques dans cette séquence</p>
              </div>
              <button
                type="button"
                class="text-[11px] font-semibold text-accent hover:underline"
                @click="openProduction(scene)"
              >
                Ouvrir Production
              </button>
            </div>
            <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <button
                v-for="shot in scene.shots"
                :key="shot.id"
                type="button"
                class="flex min-w-0 items-start gap-2 rounded-md border border-edge bg-surface px-2.5 py-2 text-left transition-colors hover:border-accent/50 hover:bg-accent/[0.04]"
                @click="openProductionShot(shot)"
              >
                <span class="shrink-0 font-mono text-[10px] text-accent">P{{ String(shot.shot_number).padStart(2, '0') }}</span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-[11px] font-medium text-content">{{ shot.title }}</span>
                  <span class="mt-0.5 block text-[10px] text-content-muted">{{ shot.duration }} s · {{ shot.validation_status === 'approved' ? 'approuvé' : 'à produire' }}</span>
                </span>
              </button>
            </div>
          </div>

          <!-- Prompt Directeur Editor -->
          <div class="rounded-lg border border-edge-subtle bg-base/60 p-3 space-y-2">
            <div class="flex items-center justify-between">
              <label class="flex items-center gap-1.5 text-xs font-medium text-content">
                <SparklesIcon class="w-3.5 h-3.5 text-accent" />
                Notes de séquence (optionnelles)
              </label>
              <span class="text-[10px] text-content-muted">
                {{ savingSceneId === scene.id ? 'Enregistrement…' : 'Modifications enregistrées automatiquement' }}
              </span>
            </div>
            <textarea
              v-model="scene.prompt"
              rows="2"
              class="w-full rounded-md border border-edge bg-surface px-3 py-1.5 text-xs text-content placeholder:text-content-muted focus:border-accent focus:outline-none transition-colors"
              placeholder="Ajouter une note commune à la séquence (les prompts des plans sont gérés individuellement dans Production)..."
              @blur="saveScene(scene)"
            />
          </div>

          <!-- Metadata & Status Controls -->
          <div class="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-4 border-t border-edge-subtle text-xs">
            <div>
              <label class="block text-[11px] font-medium text-content-muted mb-1">Statut d'avancement</label>
              <select
                v-model="scene.status"
                class="w-full rounded-lg border border-edge bg-base px-2.5 py-1.5 text-xs text-content focus:border-accent focus:outline-none"
                @change="saveScene(scene)"
              >
                <option value="planned">Planifiée</option>
                <option value="in_progress">En cours</option>
                <option value="ready_for_review">À valider</option>
                <option value="complete">Terminée</option>
              </select>
            </div>

            <div>
              <label class="block text-[11px] font-medium text-content-muted mb-1">Validation créative</label>
              <select
                v-model="scene.validation_status"
                class="w-full rounded-lg border border-edge bg-base px-2.5 py-1.5 text-xs text-content focus:border-accent focus:outline-none"
                @change="saveScene(scene)"
              >
                <option value="pending">En attente</option>
                <option value="approved">Approuvée</option>
                <option value="changes_requested">Modifications demandées</option>
              </select>
            </div>

            <div>
              <div class="text-[11px] font-medium text-content-muted mb-1">Variantes / Générations</div>
              <div class="inline-flex items-center gap-1.5 rounded-lg border border-edge-subtle bg-base px-2.5 py-1.5 text-xs font-medium text-content-secondary">
                <span>{{ scene.generation_count || 0 }} génération(s)</span>
              </div>
            </div>

            <div>
              <div class="text-[11px] font-medium text-content-muted mb-1">Blocages</div>
              <div
                class="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium"
                :class="scene.blockers?.length
                  ? 'border border-amber-500/30 bg-amber-500/10 text-amber-500'
                  : 'border border-edge-subtle bg-base text-content-muted'"
              >
                <ExclamationTriangleIcon v-if="scene.blockers?.length" class="w-3.5 h-3.5 flex-shrink-0" />
                <span class="truncate">{{ scene.blockers?.length ? scene.blockers.join(' · ') : 'Aucun blocage' }}</span>
              </div>
            </div>
          </div>
        </article>
      </section>

      <!-- Error message -->
      <div v-if="error" class="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-400">
        {{ error }}
      </div>
    </main>

    <!-- Script Full Viewer & Editor Modal -->
    <Teleport to="body">
      <div v-if="scriptModalOpen" class="fixed inset-0 z-modal flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" @click.self="scriptModalOpen = false">
        <div class="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-edge bg-surface shadow-2xl overflow-hidden">
          <div class="flex items-center justify-between border-b border-edge px-6 py-4">
            <div class="flex items-center gap-2">
              <DocumentTextIcon class="w-5 h-5 text-accent" />
              <h2 class="text-base font-semibold text-content">Script source de la direction</h2>
            </div>
            <button
              type="button"
              class="rounded-lg p-1.5 text-content-muted hover:bg-overlay-subtle hover:text-content transition-colors"
              @click="scriptModalOpen = false"
            >
              <XMarkIcon class="w-5 h-5" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto p-6 space-y-4">
            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-content-secondary">Titre du script</label>
              <input
                v-model="editScriptName"
                type="text"
                class="w-full rounded-lg border border-edge bg-base px-3.5 py-2 text-sm text-content focus:border-accent focus:outline-none"
                placeholder="Nom du script"
              />
            </div>

            <div class="space-y-1.5">
              <label class="block text-xs font-medium text-content-secondary">Texte intégral du scénario</label>
              <textarea
                v-model="editScriptText"
                rows="14"
                class="w-full rounded-lg border border-edge bg-base p-3.5 font-mono text-xs leading-relaxed text-content focus:border-accent focus:outline-none resize-y"
              />
            </div>
          </div>

          <div class="flex items-center justify-between border-t border-edge bg-base/50 px-6 py-3.5">
            <span class="text-xs text-content-muted">
              Modifier le script resynchronise les scènes existantes sans perdre l'historique des boards.
            </span>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="rounded-lg border border-edge bg-surface px-3.5 py-2 text-xs font-medium text-content-secondary hover:text-content transition-colors"
                @click="scriptModalOpen = false"
              >
                Fermer
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-accent-contrast hover:bg-accent-hover transition-colors disabled:opacity-50"
                :disabled="savingScript || !editScriptText.trim()"
                @click="saveFullScript"
              >
                <ArrowPathIcon v-if="savingScript" class="w-3.5 h-3.5 animate-spin" />
                <span>{{ savingScript ? 'Enregistrement…' : 'Mettre à jour le script' }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  FilmIcon,
  DocumentTextIcon,
  SparklesIcon,
  ChatBubbleLeftRightIcon,
  ViewColumnsIcon,
  ArrowPathIcon,
  MagnifyingGlassIcon,
  ExclamationTriangleIcon,
  XMarkIcon
} from '@heroicons/vue/24/outline'
import { useProjectDirectionApi } from '../composables/useProjectDirectionApi'
import { useWebSocket } from '../composables/useWebSocket'
import { addToast } from '../composables/useToasts'

const props = defineProps({
  project: { type: Object, required: true }
})

const router = useRouter()
const {
  getDirection,
  importScript,
  updateScript,
  updateScene,
  createSceneChat
} = useProjectDirectionApi()
const { on: onWsEvent } = useWebSocket()

const direction = ref(null)
const script = ref('')
const scriptName = ref('')
const saving = ref(false)
const loading = ref(false)
const error = ref('')
const showImportSection = ref(false)
const openingChatId = ref(null)
const savingSceneId = ref(null)

// Filtering & Search
const searchFilter = ref('')
const statusFilter = ref('all')

// Script Modal state
const scriptModalOpen = ref(false)
const editScriptName = ref('')
const editScriptText = ref('')
const savingScript = ref(false)

const validatedPercent = computed(() => {
  if (!direction.value?.progress?.total) return 0
  return Math.round((direction.value.progress.validated / direction.value.progress.total) * 100)
})

const filteredScenes = computed(() => {
  if (!direction.value?.scenes) return []
  return direction.value.scenes.filter((scene) => {
    // Search text match
    if (searchFilter.value.trim()) {
      const q = searchFilter.value.toLowerCase()
      const matchTitle = scene.title?.toLowerCase().includes(q)
      const matchDesc = scene.description?.toLowerCase().includes(q)
      const matchPrompt = scene.prompt?.toLowerCase().includes(q)
      if (!matchTitle && !matchDesc && !matchPrompt) return false
    }

    // Status filter
    if (statusFilter.value === 'blocked') {
      return Boolean(scene.blockers && scene.blockers.length > 0)
    }
    if (statusFilter.value !== 'all' && scene.status !== statusFilter.value) {
      return false
    }

    return true
  })
})

function statusLabel(status) {
  switch (status) {
    case 'in_progress': return 'En cours'
    case 'ready_for_review': return 'À valider'
    case 'complete': return 'Terminée'
    default: return 'Planifiée'
  }
}

function statusBadgeClass(status) {
  switch (status) {
    case 'in_progress': return 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    case 'ready_for_review': return 'bg-purple-500/10 text-purple-400 border-purple-500/20'
    case 'complete': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    default: return 'bg-overlay-subtle text-content-muted border-edge-subtle'
  }
}

function statusDotClass(status) {
  switch (status) {
    case 'in_progress': return 'bg-blue-400'
    case 'ready_for_review': return 'bg-purple-400'
    case 'complete': return 'bg-emerald-400'
    default: return 'bg-content-muted'
  }
}

function validationLabel(validation) {
  switch (validation) {
    case 'approved': return 'Approuvée'
    case 'changes_requested': return 'Modifications'
    default: return 'En attente'
  }
}

function validationBadgeClass(validation) {
  switch (validation) {
    case 'approved': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    case 'changes_requested': return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    default: return 'bg-overlay-subtle text-content-muted border-edge-subtle'
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    direction.value = await getDirection(props.project.id)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Impossible de charger la direction.'
  } finally {
    loading.value = false
  }
}

function loadSampleScript() {
  scriptName.value = 'Court-métrage — L\'Aube Cyber'
  script.value = `SÉQUENCE 1 — L'Arrivée
SCÈNE 1 — Découverte du laboratoire
EXT. RUE PLUVIEUSE - NUIT
Une silhouette drapée de néons approche d'un hangar discret. Les reflets holographiques dansent sur les flaques d'eau.

SCÈNE 2 — Activation du terminal
INT. LABORATOIRE - NUIT
L'opérateur pose ses mains sur la console. Des faisceaux de données bleutés illuminent la pièce.

SÉQUENCE 2 — La confrontation
SCÈNE 3 — Présentation de l'artefact
INT. SALLE DES MARCHÉS - JOUR
L'équipe découvre le fragment d'énergie pure posé au centre de la table.`
}

async function submitImport() {
  saving.value = true
  error.value = ''
  try {
    direction.value = await importScript(props.project.id, {
      script: script.value,
      script_name: scriptName.value || null
    })
    showImportSection.value = false
    script.value = ''
    addToast('Direction et scènes créées avec succès !', 'success')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Import impossible.'
    addToast(error.value, 'error')
  } finally {
    saving.value = false
  }
}

async function saveScene(scene) {
  savingSceneId.value = scene.id
  try {
    const updated = await updateScene(props.project.id, scene.id, {
      status: scene.status,
      validation_status: scene.validation_status,
      prompt: scene.prompt
    })
    Object.assign(scene, updated)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Enregistrement impossible.'
  } finally {
    savingSceneId.value = null
  }
}

async function openChat(scene) {
  openingChatId.value = scene.id
  try {
    const result = await createSceneChat(props.project.id, scene.id)
    router.push({ name: 'chat', params: { id: result.chat_id } })
  } catch (e) {
    addToast('Impossible d’ouvrir le chat de la scène.', 'error')
  } finally {
    openingChatId.value = null
  }
}

function openProduction(scene) {
  router.push({ name: 'project-production', params: { id: props.project.id } })
}

function openProductionShot(shot) {
  router.push({
    name: 'project-production',
    params: { id: props.project.id },
    query: { shot: String(shot.id) }
  })
}

function openScriptModal() {
  editScriptName.value = direction.value?.script_name || ''
  editScriptText.value = direction.value?.script_text || ''
  scriptModalOpen.value = true
}

async function saveFullScript() {
  savingScript.value = true
  try {
    direction.value = await updateScript(props.project.id, {
      script: editScriptText.value,
      script_name: editScriptName.value || null
    })
    scriptModalOpen.value = false
    addToast('Script mis à jour avec succès.', 'success')
  } catch (e) {
    addToast(e.response?.data?.detail || 'Impossible de mettre à jour le script.', 'error')
  } finally {
    savingScript.value = false
  }
}

const unsubscribeDirection = onWsEvent('project_direction_updated', (data) => {
  if (Number(data?.project_id) !== Number(props.project.id)) return
  load()
})

onMounted(load)
onUnmounted(unsubscribeDirection)
</script>
