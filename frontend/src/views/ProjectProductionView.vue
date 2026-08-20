<template>
  <div class="h-full overflow-y-auto bg-base custom-scrollbar">
    <main class="mx-auto max-w-[1440px] px-6 py-6 lg:px-8">
      <header class="mb-6 flex flex-col gap-4 border-b border-edge-subtle pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div class="mb-2 flex items-center gap-2 text-[11px] font-semibold text-accent">
            <FilmIcon class="h-4 w-4" />
            Production
          </div>
          <h1 class="text-2xl font-semibold tracking-tight text-content">Séquences, plans et générations</h1>
          <p class="mt-1 max-w-2xl text-sm leading-relaxed text-content-secondary">
            Le script organise les séquences. Chaque plan possède son contrat, ses tentatives et une validation indépendante.
          </p>
        </div>
        <div class="flex items-center gap-2 text-xs text-content-muted" aria-live="polite">
          <template v-if="activeTab === 'shots'">
            <span>{{ stats.sequence_count || 0 }} séquence(s)</span>
            <span class="text-content-faint">·</span>
            <span>{{ stats.shot_count || 0 }} plan(s)</span>
            <span class="text-content-faint">·</span>
            <span class="text-emerald-400">{{ stats.accepted_count || 0 }} approuvé(s)</span>
          </template>
          <template v-else>
            <span>{{ stats.blocking_count || 0 }} vue(s) générée(s)</span>
            <span class="text-content-faint">·</span>
            <span class="text-emerald-400">{{ stats.blocking_reviewed_count || 0 }} blocking(s) validé(s)</span>
          </template>
        </div>
      </header>

      <nav class="mb-5 flex w-fit rounded-md bg-overlay-faint p-1" role="tablist" aria-label="Vues de production">
        <button
          type="button"
          role="tab"
          class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="activeTab === 'shots' ? 'bg-accent/15 text-accent' : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          :aria-selected="activeTab === 'shots'"
          @click="setActiveTab('shots')"
        >
          Plans et générations
        </button>
        <button
          type="button"
          role="tab"
          class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :class="activeTab === 'blocking' ? 'bg-accent/15 text-accent' : 'text-content-secondary hover:bg-overlay-subtle hover:text-content'"
          :aria-selected="activeTab === 'blocking'"
          @click="setActiveTab('blocking')"
        >
          Blocking spatial
          <span class="ml-1 font-mono text-[10px]">{{ stats.blocking_count || stats.shot_count || 0 }}</span>
        </button>
      </nav>

      <details v-if="scriptDirectives" class="rounded-lg border border-amber-500/25 bg-amber-500/[0.04]">
        <summary class="cursor-pointer list-none px-5 py-4 text-sm font-medium text-content marker:hidden">
          <span class="mr-2 text-amber-400">▸</span>
          Instructions globales du script
          <span class="ml-2 text-xs font-normal text-content-muted">hors séquences et plans</span>
        </summary>
        <div class="border-t border-amber-500/15 px-5 py-4">
          <p class="mb-2 text-[11px] font-semibold text-amber-400">Cadre d’exécution / tournage</p>
          <pre class="max-h-72 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-content-secondary">{{ scriptDirectives }}</pre>
        </div>
      </details>

      <div v-if="loading" class="grid gap-4 lg:grid-cols-[270px_1fr]" aria-busy="true" aria-label="Chargement de la production">
        <div class="h-96 animate-pulse rounded-lg bg-overlay-faint" />
        <div class="h-96 animate-pulse rounded-lg bg-overlay-faint" />
      </div>

      <div v-else-if="error" class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300" role="alert">
        {{ error }}
        <button class="ml-3 underline" type="button" @click="load">Réessayer</button>
      </div>

      <div v-else-if="!sequences.length" class="rounded-lg border border-edge bg-surface p-10 text-center">
        <DocumentTextIcon class="mx-auto h-8 w-8 text-content-muted" />
        <h2 class="mt-3 text-sm font-semibold text-content">Aucune séquence importée</h2>
        <p class="mx-auto mt-1 max-w-md text-xs leading-relaxed text-content-secondary">Commence par importer ton script dans Direction pour créer la structure de production.</p>
        <button type="button" class="mt-4 rounded-md bg-accent px-3 py-2 text-xs font-semibold text-accent-contrast" @click="router.push({ name: 'project-direction', params: { id: project.id } })">Ouvrir Direction</button>
      </div>

      <div v-else class="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside class="self-start rounded-lg border border-edge bg-surface" aria-label="Séquences et plans">
          <div class="border-b border-edge-subtle px-4 py-3">
            <h2 class="text-xs font-semibold text-content-secondary">Feuille de plans</h2>
            <p class="mt-1 text-[11px] text-content-muted">{{ activeTab === 'blocking' ? 'Choisis un plan pour revoir son espace.' : 'Choisis un plan pour gérer ses candidats.' }}</p>
          </div>
          <div class="max-h-[calc(100vh-260px)] overflow-y-auto p-2">
            <section v-for="sequence in sequences" :key="sequence.id" class="mb-2 last:mb-0">
              <button type="button" class="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left hover:bg-overlay-faint" @click="selectSequence(sequence)">
                <span class="mt-0.5 font-mono text-[11px] text-accent">S{{ String(sequence.sequence_number).padStart(2, '0') }}</span>
                <span class="min-w-0 flex-1 truncate text-xs font-medium text-content">{{ sequence.title }}</span>
                <span class="text-[10px] text-content-muted">{{ sequence.shots.length }}</span>
              </button>
              <div v-if="selectedSequenceId === sequence.id" class="ml-3 border-l border-edge-subtle pl-2">
                <button
                  v-for="shot in sequence.shots"
                  :key="shot.id"
                  type="button"
                  class="mb-1 flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left transition-colors last:mb-0"
                  :class="selectedShot?.id === shot.id ? 'bg-accent/15 text-content ring-1 ring-accent/30' : 'text-content-secondary hover:bg-overlay-faint'"
                  @click="selectShot(shot, true)"
                >
                  <span class="font-mono text-[10px] text-content-muted">P{{ String(shot.shot_number).padStart(2, '0') }}</span>
                  <span class="min-w-0 flex-1 truncate text-xs">{{ shot.title }}</span>
                  <span class="h-1.5 w-1.5 rounded-full" :class="statusDot(shot)" :aria-label="statusLabel(shot)" />
                </button>
              </div>
            </section>
          </div>
        </aside>

        <section v-if="selectedShot" class="min-w-0 space-y-5">
          <ShotBlockingReview
            v-if="activeTab === 'blocking'"
            :shot="selectedShot"
            :sequence="selectedSequence"
            :previous-shot="previousShotEntry?.shot"
            :next-shot="nextShotEntry?.shot"
            :index="selectedShotIndex"
            :total="allShots.length"
            :saving="savingBlocking"
            @previous="navigateToShot(previousShotEntry)"
            @next="navigateToShot(nextShotEntry)"
            @toggle-review="toggleBlockingReview"
            @open-reference="openBlockingReference"
          />

          <template v-else>
          <div class="rounded-lg border border-edge bg-surface p-5">
            <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                  <span class="font-mono text-accent">S{{ String(selectedSequence?.sequence_number).padStart(2, '0') }} / P{{ String(selectedShot.shot_number).padStart(2, '0') }}</span>
                  <span>·</span>
                  <span>{{ statusLabel(selectedShot) }}</span>
                  <span v-if="selectedShot.generation_count">· {{ selectedShot.generation_count }} génération(s)</span>
                </div>
                <h2 class="mt-2 text-lg font-semibold text-content">{{ selectedShot.title }}</h2>
                <p class="mt-1 max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-content-secondary">{{ selectedShot.description || 'Aucune description de plan.' }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <button type="button" class="rounded-md border border-edge px-3 py-2 text-xs text-content-secondary hover:bg-overlay-faint hover:text-content" @click="openDirection">Script / Direction</button>
                <button type="button" class="rounded-md border border-edge px-3 py-2 text-xs text-content-secondary hover:bg-overlay-faint hover:text-content" :disabled="saving" @click="saveShot">Enregistrer</button>
              </div>
            </div>

            <div class="mt-5 grid gap-3 border-t border-edge-subtle pt-4 sm:grid-cols-4">
              <label class="space-y-1 text-[11px] text-content-muted">Durée (s)<input v-model.number="draft.duration" type="number" min="0.5" max="60" step="0.1" class="field" /></label>
              <label class="space-y-1 text-[11px] text-content-muted">Largeur<input v-model.number="draft.width" type="number" min="1" class="field" /></label>
              <label class="space-y-1 text-[11px] text-content-muted">Hauteur<input v-model.number="draft.height" type="number" min="1" class="field" /></label>
              <label class="space-y-1 text-[11px] text-content-muted">Entrée<input v-model="draft.transition_policy" type="text" class="field" placeholder="continuity / independent" /></label>
            </div>
          </div>

          <div class="rounded-lg border border-edge bg-surface">
            <div class="flex items-center justify-between border-b border-edge-subtle px-5 py-4">
              <div><h2 class="text-sm font-semibold text-content">Candidats de génération</h2><p class="mt-1 text-xs text-content-muted">Seuls les candidats portant le contrat exact peuvent être approuvés.</p></div>
              <button type="button" class="text-xs text-accent hover:underline" :disabled="loadingCandidates" @click="loadCandidates">{{ loadingCandidates ? 'Chargement…' : 'Actualiser' }}</button>
            </div>
            <div v-if="loadingCandidates" class="p-6 text-xs text-content-muted">Recherche des sorties du plan…</div>
            <div v-else-if="!candidates.length" class="p-8 text-center text-xs text-content-muted">Aucun candidat attaché à ce plan pour le moment. Lance une génération depuis le chat de la séquence, avec le contrat actif.</div>
            <div v-else class="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
              <article v-for="candidate in candidates" :key="`${candidate.job_id}-${candidate.media_id}`" class="overflow-hidden rounded-md border" :class="candidate.is_accepted ? 'border-emerald-500/50' : 'border-edge-subtle'">
                <div class="relative aspect-video bg-matte">
                  <MediaImage :media-id="candidate.media_id" :is-video="isVideo(candidate)" :contain="true" :enable-context-menu="false" container-class="h-full w-full" img-class="h-full w-full object-contain" />
                  <span class="absolute left-2 top-2 rounded bg-black/70 px-1.5 py-1 text-[10px] text-white">{{ candidate.match_confidence === 'exact_shot' ? 'Contrat exact' : 'Suggestion scène' }}</span>
                </div>
                <div class="space-y-3 p-3">
                  <div class="flex items-center justify-between text-[11px] text-content-muted"><span>Job #{{ candidate.job_id }}</span><span>{{ formatDate(candidate.completed_at) }}</span></div>
                  <div v-if="candidate.approval_eligible && !candidate.is_accepted" class="flex gap-2"><button type="button" class="flex-1 rounded-md bg-accent px-2 py-1.5 text-xs font-semibold text-accent-contrast disabled:opacity-50" :disabled="acting" @click="approve(candidate)">Approuver</button><button type="button" class="rounded-md border border-edge px-2 py-1.5 text-xs text-content-secondary hover:text-content" :disabled="acting" @click="reject(candidate)">Rejeter</button></div>
                  <div v-else-if="candidate.is_accepted" class="text-xs font-medium text-emerald-400">Plan approuvé · continuité active</div>
                  <div v-else class="text-[11px] text-amber-400">Suggestion uniquement · régénérer avec le contrat exact</div>
                </div>
              </article>
            </div>
          </div>
          </template>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onActivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FilmIcon, DocumentTextIcon } from '@heroicons/vue/24/outline'
import { MediaImage } from '../components/media'
import ShotBlockingReview from '../components/production/ShotBlockingReview.vue'
import { useProjectProductionApi } from '../composables/useProjectProductionApi'

const props = defineProps({ project: { type: Object, required: true } })
const router = useRouter()
const route = useRoute()
const { getProduction, findCandidateShot, getCandidates, updateShot, approveShot, rejectShot } = useProjectProductionApi()
const sequences = ref([])
const stats = ref({})
const scriptDirectives = ref('')
const activeTab = ref(route.query.tab === 'blocking' ? 'blocking' : 'shots')
const selectedSequenceId = ref(null)
const selectedShotId = ref(null)
const candidates = ref([])
const loading = ref(true)
const loadingCandidates = ref(false)
const saving = ref(false)
const savingBlocking = ref(false)
const acting = ref(false)
const error = ref('')
const draft = reactive({ duration: 4, width: 1344, height: 768, transition_policy: 'continuity' })

const selectedSequence = computed(() => sequences.value.find((sequence) => sequence.id === selectedSequenceId.value) || sequences.value[0] || null)
const selectedShot = computed(() => selectedSequence.value?.shots.find((shot) => shot.id === selectedShotId.value) || selectedSequence.value?.shots[0] || null)
const allShots = computed(() => sequences.value.flatMap((sequence) => sequence.shots.map((shot) => ({ sequence, shot }))))
const selectedShotIndex = computed(() => Math.max(0, allShots.value.findIndex((entry) => entry.shot.id === selectedShot.value?.id)))
const previousShotEntry = computed(() => selectedShotIndex.value > 0 ? allShots.value[selectedShotIndex.value - 1] : null)
const nextShotEntry = computed(() => selectedShotIndex.value < allShots.value.length - 1 ? allShots.value[selectedShotIndex.value + 1] : null)

function selectShot(shot, updateRoute = false) {
  selectedShotId.value = shot.id
  Object.assign(draft, { duration: shot.duration, width: shot.width, height: shot.height, transition_policy: shot.transition_policy })
  if (updateRoute) router.replace({ query: { ...route.query, shot: shot.id } })
}

function selectSequence(sequence) {
  selectedSequenceId.value = sequence.id
  const shot = sequence.shots.find((item) => item.id === selectedShotId.value) || sequence.shots[0]
  if (shot) selectShot(shot, true)
}

function navigateToShot(entry) {
  if (!entry) return
  selectedSequenceId.value = entry.sequence.id
  selectShot(entry.shot, true)
}

function setActiveTab(tab) {
  activeTab.value = tab
  const query = { ...route.query }
  if (tab === 'blocking') query.tab = 'blocking'
  else delete query.tab
  router.replace({ query })
}

function handleShotNavigationKeydown(event) {
  if (activeTab.value !== 'blocking' || !selectedShot.value) return
  if (event.altKey || event.ctrlKey || event.metaKey) return

  const target = event.target
  if (target instanceof HTMLElement && (target.isContentEditable || target.closest('input, textarea, select, [contenteditable="true"]'))) return

  if (event.key === 'ArrowLeft' && previousShotEntry.value) {
    event.preventDefault()
    navigateToShot(previousShotEntry.value)
  } else if (event.key === 'ArrowRight' && nextShotEntry.value) {
    event.preventDefault()
    navigateToShot(nextShotEntry.value)
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const payload = await getProduction(props.project.id)
    sequences.value = payload.sequences || []
    stats.value = payload.stats || {}
    scriptDirectives.value = payload.script_directives || ''
    if (!selectedSequenceId.value && sequences.value[0]) selectedSequenceId.value = sequences.value[0].id
    const requestedShotId = Number(route.query.shot)
    if (Number.isInteger(requestedShotId) && requestedShotId > 0) {
      const sequence = sequences.value.find((item) => item.shots.some((shot) => shot.id === requestedShotId))
      if (sequence) {
        selectedSequenceId.value = sequence.id
        selectedShotId.value = requestedShotId
      }
    }
    const candidateMediaId = Number(route.query.candidate)
    if (!selectedShotId.value && Number.isInteger(candidateMediaId) && candidateMediaId > 0) {
      const target = await findCandidateShot(props.project.id, candidateMediaId).catch(() => null)
      const sequence = sequences.value.find((item) => item.id === target?.scene_id)
      if (sequence) {
        selectedSequenceId.value = sequence.id
        selectedShotId.value = target.shot_id
      }
    }
    const shot = selectedShot.value || sequences.value[0]?.shots?.[0]
    if (shot) selectShot(shot)
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Impossible de charger la production.'
  } finally { loading.value = false }
}

async function loadCandidates() {
  if (!selectedShot.value) return
  loadingCandidates.value = true
  try { candidates.value = (await getCandidates(props.project.id, selectedShot.value.id)).candidates || [] } catch { candidates.value = [] } finally { loadingCandidates.value = false }
}

async function saveShot() {
  if (!selectedShot.value) return
  saving.value = true
  try {
    const updated = await updateShot(props.project.id, selectedShot.value.id, { ...draft, revision: selectedShot.value.revision })
    Object.assign(selectedShot.value, updated)
  } catch (err) { error.value = err?.response?.data?.detail || 'Impossible d’enregistrer le plan.' } finally { saving.value = false }
}

async function toggleBlockingReview() {
  if (!selectedShot.value?.blocking) return
  savingBlocking.value = true
  error.value = ''
  try {
    const approved = selectedShot.value.blocking.status === 'approved'
    const blocking = {
      ...selectedShot.value.blocking,
      status: approved ? 'draft' : 'approved',
      reviewed_at: approved ? null : new Date().toISOString(),
    }
    await updateShot(props.project.id, selectedShot.value.id, {
      settings: { ...(selectedShot.value.settings || {}), blocking },
      revision: selectedShot.value.revision,
    })
    await load()
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Impossible d’enregistrer la revue du blocking.'
  } finally { savingBlocking.value = false }
}

async function approve(candidate) {
  acting.value = true
  try { await approveShot(props.project.id, selectedShot.value.id, { media_id: candidate.media_id, revision: selectedShot.value.revision }); await load() } catch (err) { error.value = err?.response?.data?.detail || 'Impossible d’approuver ce candidat.' } finally { acting.value = false }
}

async function reject(candidate) {
  const reason = window.prompt('Pourquoi rejeter ce candidat ?', 'Mouvement ou continuité à corriger')
  if (!reason) return
  acting.value = true
  try { await rejectShot(props.project.id, selectedShot.value.id, { reason }); await load() } catch (err) { error.value = err?.response?.data?.detail || 'Impossible de rejeter ce candidat.' } finally { acting.value = false }
}

function openDirection() { router.push({ name: 'project-direction', params: { id: props.project.id } }) }
function openBlockingReference(reference) {
  router.push({
    name: 'project-references',
    params: { id: props.project.id },
    query: reference?.pack_id ? { pack: String(reference.pack_id) } : {},
  })
}
function isVideo(candidate) { return ['mp4', 'webm', 'mov', 'avi', 'mkv', 'm4v'].includes(String(candidate.file_format || '').toLowerCase()) }
function formatDate(value) { return value ? new Date(value).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—' }
function statusLabel(shot) { return shot.validation_status === 'approved' ? 'Approuvé' : shot.validation_status === 'changes_requested' ? 'À corriger' : shot.generation_count ? 'Candidats disponibles' : 'À générer' }
function statusDot(shot) { return shot.validation_status === 'approved' ? 'bg-emerald-400' : shot.validation_status === 'changes_requested' ? 'bg-amber-400' : shot.generation_count ? 'bg-accent' : 'bg-content-muted' }

watch([selectedShot, activeTab], ([shot, tab]) => {
  if (!shot) return
  Object.assign(draft, { duration: shot.duration, width: shot.width, height: shot.height, transition_policy: shot.transition_policy })
  if (tab === 'shots') loadCandidates()
})
onMounted(() => {
  load()
  window.addEventListener('keydown', handleShotNavigationKeydown)
})
onActivated(() => { if (sequences.value.length) load() })
onUnmounted(() => window.removeEventListener('keydown', handleShotNavigationKeydown))
</script>

<style scoped>
.field { @apply w-full rounded-md border border-edge bg-base px-2.5 py-2 text-xs text-content outline-none focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/40; }
</style>
