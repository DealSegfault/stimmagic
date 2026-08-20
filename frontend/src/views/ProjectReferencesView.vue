<script setup lang="ts">
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CubeTransparentIcon, MapIcon } from '@heroicons/vue/24/outline'
import CompositionStudio from '../components/references/CompositionStudio.vue'
import ReferencePackEditor from '../components/references/ReferencePackEditor.vue'
import ReferenceSidebar from '../components/references/ReferenceSidebar.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import Button from '../components/ui/Button.vue'
import { useProjectElementsApi } from '../composables/useProjectElementsApi'
import {
  useProjectReferencesApi,
  type ProjectComposition,
  type ReferencePack,
  type ReferenceView,
  type ReferenceWorkspace,
} from '../composables/useProjectReferencesApi'
import { useToasts } from '../composables/useToasts'

const props = defineProps<{ project: { id: number; name?: string } }>()
const route = useRoute()
const router = useRouter()
const referencesApi = useProjectReferencesApi()
const elementsApi = useProjectElementsApi()
const { addToast } = useToasts()

const workspace = ref<ReferenceWorkspace | null>(null)
const selectedId = ref<number | null>(null)
const activeMode = ref<'views' | 'compositions'>('views')
const loading = ref(true)
const creating = ref(false)
const busyAction = ref('')
const error = ref('')
const deleteTarget = ref<{ kind: 'pack'; value: ReferencePack } | { kind: 'composition'; value: ProjectComposition } | null>(null)

const packs = computed(() => workspace.value?.packs || [])
const selectedPack = computed(() => packs.value.find((pack) => pack.id === selectedId.value) || null)
const sourcePacks = computed(() => packs.value.filter((pack) => ['prop', 'character'].includes(pack.pack_type)))
const stats = computed(() => workspace.value?.stats || {})

function errorMessage(reason: any): string {
  return reason?.response?.data?.detail || reason?.message || 'Une erreur inattendue est survenue.'
}

async function load(preferredElementId?: number) {
  loading.value = !workspace.value
  error.value = ''
  try {
    workspace.value = await referencesApi.getWorkspace(props.project.id)
    const queryPackId = Number(route.query.pack)
    const preferred = preferredElementId
      ? packs.value.find((pack) => pack.project_element_id === preferredElementId)
      : packs.value.find((pack) => pack.id === queryPackId)
    if (preferred) selectedId.value = preferred.id
    else if (!selectedPack.value) selectedId.value = packs.value[0]?.id || null
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    loading.value = false
  }
}

function selectPack(id: number) {
  selectedId.value = id
  activeMode.value = 'views'
  router.replace({ query: { ...route.query, pack: String(id) } })
}

async function run(action: string, operation: () => Promise<any>, success?: string) {
  busyAction.value = action
  try {
    const result = await operation()
    await load()
    if (success) addToast(success, 'success', 3000)
    return result
  } catch (reason) {
    addToast(errorMessage(reason), 'error', 6000)
    return null
  } finally {
    busyAction.value = ''
  }
}

async function createReference(type: 'location' | 'prop') {
  creating.value = true
  try {
    const element = await elementsApi.createElement(props.project.id, { element_type: type })
    await load(element.id)
    addToast(type === 'location' ? 'Lieu créé' : 'Prop créé', 'success', 2500)
  } catch (reason) {
    addToast(errorMessage(reason), 'error', 5000)
  } finally {
    creating.value = false
  }
}

function renamePack(input: { name: string; description: string }) {
  if (!selectedPack.value) return
  run('identity', () => elementsApi.updateElement(
    props.project.id,
    selectedPack.value!.project_element_id,
    input,
  ), 'Identité enregistrée')
}

function saveContract(input: { identity_prompt: string; negative_prompt: string }) {
  if (!selectedPack.value) return
  run('contract', () => referencesApi.updatePack(props.project.id, selectedPack.value!.id, input), 'Contrat mis à jour')
}

function actOnView(action: 'generate' | 'approve' | 'reject', view: ReferenceView) {
  const calls = {
    generate: () => referencesApi.generateView(props.project.id, view.id),
    approve: () => referencesApi.approveView(props.project.id, view.id),
    reject: () => referencesApi.rejectView(props.project.id, view.id),
  }
  const labels = { generate: 'Candidate AGY prête à revoir', approve: 'Vue approuvée', reject: 'Candidate rejetée' }
  run(`view:${view.id}`, calls[action], labels[action])
}

function createState(input: { state_key: string; label: string; prompt_delta: string }) {
  if (!selectedPack.value) return
  run('state', () => referencesApi.createState(props.project.id, selectedPack.value!.id, input), 'État ajouté')
}

function createComposition(input: Record<string, any>) {
  run('create-composition', () => referencesApi.createComposition(props.project.id, input), 'Composition verrouillée créée')
}

function actOnComposition(action: 'generate' | 'approve' | 'reject', composition: ProjectComposition) {
  const calls = {
    generate: () => referencesApi.generateComposition(props.project.id, composition.id),
    approve: () => referencesApi.approveComposition(props.project.id, composition.id),
    reject: () => referencesApi.rejectComposition(props.project.id, composition.id),
  }
  const labels = { generate: 'Composition AGY prête à revoir', approve: 'Composition approuvée', reject: 'Composition rejetée' }
  run(`composition:${composition.id}`, calls[action], labels[action])
}

async function confirmDelete() {
  const target = deleteTarget.value
  if (!target) return
  busyAction.value = 'delete'
  try {
    if (target.kind === 'pack') {
      await elementsApi.deleteElement(props.project.id, target.value.project_element_id)
      selectedId.value = null
    } else {
      await referencesApi.deleteComposition(props.project.id, target.value.id)
    }
    deleteTarget.value = null
    await load()
    addToast('Référence placée dans la corbeille', 'info', 3000)
  } catch (reason) {
    addToast(errorMessage(reason), 'error', 6000)
  } finally {
    busyAction.value = ''
  }
}

onMounted(load)
onActivated(() => { if (workspace.value) load() })
watch(() => props.project.id, () => { workspace.value = null; selectedId.value = null; load() })
</script>

<template>
  <div class="h-full overflow-y-auto bg-base custom-scrollbar">
    <main class="mx-auto max-w-[1600px] px-5 py-6 lg:px-8">
      <header class="mb-6 flex flex-col gap-4 border-b border-edge-subtle pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div class="mb-2 flex items-center gap-2 text-[11px] font-semibold text-accent"><CubeTransparentIcon class="h-4 w-4" /> Références</div>
          <h1 class="text-2xl font-semibold tracking-tight text-content">Blocking, identités et location views</h1>
          <p class="mt-1 max-w-3xl text-sm leading-relaxed text-content-secondary">Construis des vues approuvées et réutilisables avant de générer les plans. Chaque composition conserve ses révisions sources pour garantir la continuité.</p>
        </div>
        <div class="flex flex-wrap items-center gap-2 font-mono text-[10px] text-content-muted" aria-live="polite">
          <span>{{ stats.location_count || 0 }} lieux</span><span>·</span><span>{{ stats.prop_count || 0 }} props</span><span>·</span><span class="text-emerald-400">{{ stats.approved_view_count || 0 }} vues approuvées</span><span>·</span><span>{{ stats.composition_count || 0 }} compositions</span>
        </div>
      </header>

      <div v-if="loading" class="grid gap-5 lg:grid-cols-[300px_1fr]" aria-busy="true" aria-label="Chargement des références"><div class="h-[520px] rounded-lg bg-overlay-faint" /><div class="h-[520px] rounded-lg bg-overlay-faint" /></div>
      <div v-else-if="error" class="rounded-lg border border-red-500/30 bg-red-500/10 p-5 text-sm text-red-300" role="alert">{{ error }}<Button size="sm" variant="ghost" class="ml-3" @click="load()">Réessayer</Button></div>
      <div v-else-if="!packs.length" class="rounded-lg border border-edge bg-surface p-12 text-center"><MapIcon class="mx-auto h-8 w-8 text-content-muted" /><h2 class="mt-3 text-sm font-semibold text-content">Aucune référence de production</h2><p class="mx-auto mt-1 max-w-lg text-xs leading-relaxed text-content-secondary">Crée un lieu pour dériver ses angles depuis le blocking, ou un prop pour générer ses vues canoniques.</p><div class="mt-5 flex justify-center gap-2"><Button variant="secondary" @click="createReference('location')">Créer un lieu</Button><Button @click="createReference('prop')">Créer un prop</Button></div></div>

      <div v-else class="grid min-h-[620px] gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <ReferenceSidebar :packs="packs" :selected-id="selectedId" :creating="creating" class="self-start lg:sticky lg:top-4 lg:max-h-[calc(100vh-120px)]" @select="selectPack" @create="createReference" />
        <div v-if="selectedPack" class="min-w-0">
          <nav v-if="selectedPack.pack_type === 'location'" class="mb-5 flex w-fit rounded-md bg-overlay-faint p-1" role="tablist" aria-label="Mode de référence">
            <button type="button" role="tab" class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors" :class="activeMode === 'views' ? 'bg-accent/15 text-accent' : 'text-content-muted hover:text-content'" :aria-selected="activeMode === 'views'" @click="activeMode = 'views'">Vues du lieu</button>
            <button type="button" role="tab" class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors" :class="activeMode === 'compositions' ? 'bg-accent/15 text-accent' : 'text-content-muted hover:text-content'" :aria-selected="activeMode === 'compositions'" @click="activeMode = 'compositions'">Location view studio <span class="ml-1 font-mono text-[9px]">{{ selectedPack.compositions.length }}</span></button>
          </nav>

          <ReferencePackEditor
            v-if="activeMode === 'views' || selectedPack.pack_type !== 'location'"
            :pack="selectedPack"
            :busy-action="busyAction"
            @rename="renamePack"
            @save-contract="saveContract"
            @generate-missing="run('missing', () => referencesApi.generateMissing(project.id, selectedPack!.id), 'Lot de vues terminé')"
            @sync-blocking="run('sync', () => referencesApi.syncBlocking(project.id), 'Angles de blocking synchronisés')"
            @render-sheet="run('sheet', () => referencesApi.renderSheet(project.id, selectedPack!.id), 'Sheet assemblée')"
            @generate-view="actOnView('generate', $event)"
            @approve-view="actOnView('approve', $event)"
            @reject-view="actOnView('reject', $event)"
            @create-state="createState"
            @delete-pack="deleteTarget = { kind: 'pack', value: selectedPack! }"
          />
          <CompositionStudio
            v-else
            :location-pack="selectedPack"
            :source-packs="sourcePacks"
            :busy-action="busyAction"
            @create="createComposition"
            @generate="actOnComposition('generate', $event)"
            @approve="actOnComposition('approve', $event)"
            @reject="actOnComposition('reject', $event)"
            @delete="deleteTarget = { kind: 'composition', value: $event }"
          />
        </div>
      </div>
    </main>

    <ConfirmDialog
      :show="Boolean(deleteTarget)"
      danger
      :busy="busyAction === 'delete'"
      title="Placer cette référence dans la corbeille ?"
      :message="deleteTarget?.kind === 'pack' ? 'Ses vues, états et compositions seront retirés du projet.' : 'La composition et ses épingles de révision seront retirées.'"
      confirm-label="Mettre dans la corbeille"
      cancel-label="Conserver"
      @cancel="deleteTarget = null"
      @confirm="confirmDelete"
    />
  </div>
</template>
