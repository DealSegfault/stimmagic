<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  DocumentDuplicateIcon,
  PlusIcon,
  Squares2X2Icon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import { MediaImage } from '../media'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import ReferenceStatusBadge from './ReferenceStatusBadge.vue'
import ReferenceViewCard from './ReferenceViewCard.vue'
import type { ReferencePack, ReferenceView } from '../../composables/useProjectReferencesApi'

const props = defineProps<{
  pack: ReferencePack
  busyAction?: string
}>()

const emit = defineEmits<{
  rename: [{ name: string; description: string }]
  saveContract: [{ identity_prompt: string; negative_prompt: string }]
  generateMissing: []
  syncBlocking: []
  renderSheet: []
  generateView: [ReferenceView]
  approveView: [ReferenceView]
  rejectView: [ReferenceView]
  createState: [{ state_key: string; label: string; prompt_delta: string }]
  deletePack: []
}>()

const identityPrompt = ref('')
const negativePrompt = ref('')
const name = ref('')
const description = ref('')
const stateOpen = ref(false)
const stateDraft = reactive({ state_key: '', label: '', prompt_delta: '' })

watch(() => props.pack.id, hydrate, { immediate: true })
watch(() => props.pack.prompt_version, hydrate)

function hydrate() {
  identityPrompt.value = props.pack.identity_prompt
  negativePrompt.value = props.pack.negative_prompt
  name.value = props.pack.element.name
  description.value = props.pack.element.description || ''
}

const approvedCount = computed(() => props.pack.views.filter((view) => view.status === 'approved').length)
const contractDirty = computed(() => (
  identityPrompt.value.trim() !== props.pack.identity_prompt
  || negativePrompt.value.trim() !== props.pack.negative_prompt
))
const identityDirty = computed(() => (
  name.value.trim() !== props.pack.element.name
  || description.value.trim() !== (props.pack.element.description || '')
))
const isBusy = (name: string) => props.busyAction === name
const viewBusy = (view: ReferenceView) => props.busyAction === `view:${view.id}`

function submitState() {
  if (!stateDraft.label.trim()) return
  emit('createState', { ...stateDraft })
  Object.assign(stateDraft, { state_key: '', label: '', prompt_delta: '' })
  stateOpen.value = false
}
</script>

<template>
  <section class="min-w-0 space-y-5">
    <header class="rounded-lg border border-edge bg-surface p-5">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">{{ pack.pack_type }}</span>
            <ReferenceStatusBadge :status="pack.status" />
            <span class="text-[10px] text-content-muted">{{ approvedCount }} / {{ pack.views.length }} vues approuvées</span>
          </div>
          <div class="mt-3 grid gap-3 lg:grid-cols-[minmax(220px,0.55fr)_1fr]">
            <label class="space-y-1 text-[10px] font-medium text-content-muted">
              Nom stable
              <input v-model="name" class="w-full rounded-md border border-edge bg-base px-3 py-2 text-sm font-semibold text-content outline-none focus:border-accent" />
            </label>
            <label class="space-y-1 text-[10px] font-medium text-content-muted">
              Description visuelle
              <input v-model="description" class="w-full rounded-md border border-edge bg-base px-3 py-2 text-sm text-content outline-none focus:border-accent" placeholder="Matières, époque, proportions, signes distinctifs…" />
            </label>
          </div>
          <div class="mt-2 flex items-center gap-3">
            <span class="font-mono text-[9px] text-content-muted">{{ pack.element.reference_id }}</span>
            <button v-if="identityDirty" type="button" class="text-[10px] font-medium text-accent hover:underline" @click="$emit('rename', { name: name.trim(), description: description.trim() })">Enregistrer l’identité</button>
          </div>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <Button v-if="pack.pack_type === 'location'" size="sm" variant="secondary" :loading="isBusy('sync')" @click="$emit('syncBlocking')">
            <ArrowPathIcon class="h-4 w-4" /> Synchroniser le blocking
          </Button>
          <Tooltip text="Supprimer la référence et ses vues">
            <IconButton variant="danger" aria-label="Supprimer cette référence" :disabled="Boolean(busyAction)" @click="$emit('deletePack')">
              <TrashIcon class="h-4 w-4" />
            </IconButton>
          </Tooltip>
        </div>
      </div>
    </header>

    <section class="rounded-lg border border-edge bg-surface">
      <div class="flex items-center justify-between border-b border-edge-subtle px-5 py-4">
        <div>
          <h2 class="text-sm font-semibold text-content">{{ pack.pack_type === 'location' ? 'Augmentation AGY du lieu' : 'Contrat d’identité AGY' }}</h2>
          <p class="mt-1 text-xs text-content-muted">
            {{ pack.pack_type === 'location'
              ? 'Le blocking, l’état MNESIS, la géographie et les interdictions sont injectés automatiquement pour chaque angle.'
              : 'Les vues partagent ce socle. Toute modification rend les sorties précédentes obsolètes.' }}
          </p>
        </div>
        <span class="font-mono text-[10px] text-content-muted">prompt v{{ pack.prompt_version }}</span>
      </div>
      <div v-if="pack.pack_type === 'location'" class="mx-5 mt-5 rounded-md border border-accent/25 bg-accent/5 px-4 py-3">
        <p class="text-xs font-medium text-content">Aucun prompt manuel requis</p>
        <p class="mt-1 text-[11px] leading-relaxed text-content-muted">AGY reçoit automatiquement la location state, les ancres visibles, la famille caméra, les plans concernés et les failure locks du skill MNESIS. Les champs ci-dessous ne servent qu’à ajouter une intention artistique.</p>
      </div>
      <div class="grid gap-4 p-5 lg:grid-cols-2">
        <label class="space-y-1.5 text-[11px] font-medium text-content-muted">
          {{ pack.pack_type === 'location' ? 'Direction artistique optionnelle' : 'Identité à préserver' }}
          <textarea v-model="identityPrompt" rows="5" class="w-full resize-y rounded-md border border-edge bg-base px-3 py-2 text-xs leading-relaxed text-content outline-none focus:border-accent" :placeholder="pack.pack_type === 'location' ? 'Optionnel — matières ou intention non définies par le script…' : 'Décris précisément la forme, les matières, les couleurs et l’échelle…'" />
        </label>
        <label class="space-y-1.5 text-[11px] font-medium text-content-muted">
          {{ pack.pack_type === 'location' ? 'Exclusions complémentaires' : 'Exclusions' }}
          <textarea v-model="negativePrompt" rows="5" class="w-full resize-y rounded-md border border-edge bg-base px-3 py-2 text-xs leading-relaxed text-content outline-none focus:border-accent" :placeholder="pack.pack_type === 'location' ? 'Optionnel — les interdictions MNESIS sont déjà ajoutées…' : 'Éléments à ne jamais introduire ou modifier…'" />
        </label>
      </div>
      <div class="flex justify-end border-t border-edge-subtle px-5 py-3">
        <Button size="sm" :disabled="!contractDirty || Boolean(busyAction)" :loading="isBusy('contract')" @click="$emit('saveContract', { identity_prompt: identityPrompt.trim(), negative_prompt: negativePrompt.trim() })">Enregistrer le contrat</Button>
      </div>
    </section>

    <section>
      <div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 class="text-sm font-semibold text-content">Vues canoniques</h2>
          <p class="mt-1 text-xs text-content-muted">Chaque carte est générée et approuvée séparément. La sheet est assemblée ensuite, sans collage IA.</p>
        </div>
        <Button size="sm" variant="secondary" :loading="isBusy('missing')" :disabled="Boolean(busyAction) && !isBusy('missing')" @click="$emit('generateMissing')">
          <Squares2X2Icon class="h-4 w-4" /> Générer les vues manquantes
        </Button>
      </div>
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <ReferenceViewCard
          v-for="view in pack.views"
          :key="view.id"
          :view="view"
          :busy="viewBusy(view)"
          @generate="$emit('generateView', $event)"
          @approve="$emit('approveView', $event)"
          @reject="$emit('rejectView', $event)"
        />
      </div>
    </section>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
      <div class="rounded-lg border border-edge bg-surface p-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-sm font-semibold text-content">États sémantiques</h2>
            <p class="mt-1 text-xs text-content-muted">Un état modifie le contexte sans changer l’identité de la référence.</p>
          </div>
          <Button size="sm" variant="ghost" @click="stateOpen = !stateOpen"><PlusIcon class="h-4 w-4" /> Ajouter</Button>
        </div>
        <form v-if="stateOpen" class="mt-4 grid gap-3 rounded-md bg-overlay-faint p-3 sm:grid-cols-2" @submit.prevent="submitState">
          <input v-model="stateDraft.label" required class="rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent" placeholder="Ex. Usé après combat" />
          <input v-model="stateDraft.state_key" class="rounded-md border border-edge bg-base px-3 py-2 font-mono text-xs text-content outline-none focus:border-accent" placeholder="clé optionnelle" />
          <textarea v-model="stateDraft.prompt_delta" rows="2" class="rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent sm:col-span-2" placeholder="Ce qui change visuellement dans cet état…" />
          <div class="flex justify-end gap-2 sm:col-span-2"><Button size="sm" variant="ghost" type="button" @click="stateOpen = false">Annuler</Button><Button size="sm" type="submit">Créer l’état</Button></div>
        </form>
        <div class="mt-4 divide-y divide-edge-subtle">
          <div v-for="state in pack.states" :key="state.id" class="py-3 first:pt-0 last:pb-0">
            <div class="flex items-center gap-2"><span class="text-xs font-medium text-content">{{ state.label }}</span><span v-if="state.is_default" class="rounded bg-overlay-subtle px-1.5 py-0.5 text-[9px] text-content-muted">Défaut</span></div>
            <p class="mt-1 text-[11px] text-content-muted">{{ state.prompt_delta || 'Aucune variation visuelle.' }}</p>
          </div>
        </div>
      </div>

      <div class="overflow-hidden rounded-lg border border-edge bg-surface">
        <div class="aspect-[4/3] bg-matte">
          <MediaImage v-if="pack.sheet_media_id" :media-id="pack.sheet_media_id" :thumbnail="false" :contain="true" :enable-context-menu="false" alt="Sheet de références approuvées" container-class="h-full w-full" img-class="h-full w-full object-contain" />
          <div v-else class="flex h-full flex-col items-center justify-center px-6 text-center"><DocumentDuplicateIcon class="h-7 w-7 text-content-muted" /><p class="mt-2 text-xs text-content-secondary">La sheet sera assemblée à partir des vues approuvées.</p></div>
        </div>
        <div class="flex items-center justify-between gap-4 border-t border-edge-subtle p-4">
          <div><h2 class="text-xs font-semibold text-content">Location / reference view sheet</h2><p class="mt-1 text-[10px] text-content-muted">Révision déterministe, prête pour AGY.</p></div>
          <Button size="sm" variant="secondary" :loading="isBusy('sheet')" :disabled="approvedCount === 0" @click="$emit('renderSheet')">Assembler</Button>
        </div>
      </div>
    </section>
  </section>
</template>
