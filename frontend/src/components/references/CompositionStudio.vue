<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  CheckIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import { MediaImage } from '../media'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import ReferenceStatusBadge from './ReferenceStatusBadge.vue'
import type {
  ProjectComposition,
  ReferencePack,
  ReferenceView,
} from '../../composables/useProjectReferencesApi'

interface DraftItem {
  key: number
  pack_id: number | null
  view_id: number | null
  state_id: number | null
  x: number
  y: number
  scale: number
}

const props = defineProps<{
  locationPack: ReferencePack
  sourcePacks: ReferencePack[]
  busyAction?: string
}>()

const emit = defineEmits<{
  create: [Record<string, any>]
  generate: [ProjectComposition]
  approve: [ProjectComposition]
  reject: [ProjectComposition]
  delete: [ProjectComposition]
}>()

let nextKey = 1
const locationViewId = ref<number | null>(null)
const compositionName = ref('')
const promptDelta = ref('')
const guideMediaId = ref<number | null>(null)
const items = reactive<DraftItem[]>([])

const approvedLocations = computed(() => props.locationPack.views.filter((view) => view.approved_revision_id))
const eligiblePacks = computed(() => props.sourcePacks.filter((pack) => (
  ['prop', 'character'].includes(pack.pack_type) && pack.views.some((view) => view.approved_revision_id)
)))

watch(() => props.locationPack.id, () => {
  locationViewId.value = approvedLocations.value[0]?.id || null
  compositionName.value = ''
  promptDelta.value = ''
  items.splice(0)
  addItem()
}, { immediate: true })

function packFor(item: DraftItem) {
  return eligiblePacks.value.find((pack) => pack.id === item.pack_id)
}

function approvedViews(item: DraftItem): ReferenceView[] {
  return packFor(item)?.views.filter((view) => view.approved_revision_id) || []
}

function addItem() {
  const pack = eligiblePacks.value[0]
  items.push({
    key: nextKey++,
    pack_id: pack?.id || null,
    view_id: pack?.views.find((view) => view.approved_revision_id)?.id || null,
    state_id: pack?.states.find((state) => state.is_default)?.id || null,
    x: 0.5,
    y: 0.65,
    scale: 0.2,
  })
}

function onPackChange(item: DraftItem) {
  const pack = packFor(item)
  item.view_id = pack?.views.find((view) => view.approved_revision_id)?.id || null
  item.state_id = pack?.states.find((state) => state.is_default)?.id || null
}

const canCreate = computed(() => Boolean(
  locationViewId.value
  && items.length
  && items.every((item) => item.pack_id && item.view_id),
))

function submit() {
  if (!canCreate.value) return
  emit('create', {
    location_view_id: locationViewId.value,
    name: compositionName.value.trim() || null,
    prompt_delta: promptDelta.value.trim() || null,
    placement_guide_media_id: guideMediaId.value || null,
    items: items.map((item) => {
      const pack = packFor(item)
      return {
        project_element_id: pack!.project_element_id,
        reference_view_id: item.view_id,
        state_id: item.state_id || null,
        role: pack!.pack_type === 'character' ? 'character' : 'prop',
        placement: { x: item.x, y: item.y, scale: item.scale },
      }
    }),
  })
}

function score(composition: ProjectComposition): string | null {
  const value = composition.validation?.background_similarity
  return typeof value === 'number' ? `${Math.round(value * 100)} %` : null
}
</script>

<template>
  <section class="space-y-5">
    <div class="rounded-lg border border-edge bg-surface">
      <div class="border-b border-edge-subtle px-5 py-4">
        <div class="flex items-center gap-2"><SparklesIcon class="h-4 w-4 text-accent" /><h2 class="text-sm font-semibold text-content">Location view studio</h2></div>
        <p class="mt-1 text-xs text-content-muted">AGY reçoit d’abord le clean plate exact, puis les identités approuvées et leur placement. Le décor hors zone est contrôlé après génération.</p>
      </div>

      <form class="space-y-5 p-5" @submit.prevent="submit">
        <div v-if="!approvedLocations.length" class="rounded-md border border-amber-500/25 bg-amber-500/[0.06] p-4 text-xs text-amber-300">
          Approuve d’abord une vue du lieu. Elle deviendra le clean plate verrouillé de Picture 1.
        </div>
        <div v-else-if="!eligiblePacks.length" class="rounded-md border border-amber-500/25 bg-amber-500/[0.06] p-4 text-xs text-amber-300">
          Approuve au moins une vue de prop ou de personnage pour créer une composition.
        </div>

        <div class="grid gap-4 lg:grid-cols-3">
          <label class="space-y-1 text-[11px] font-medium text-content-muted">Clean plate
            <select v-model.number="locationViewId" class="w-full rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent">
              <option v-for="view in approvedLocations" :key="view.id" :value="view.id">{{ view.label }} · rev {{ view.approved_revision_id }}</option>
            </select>
          </label>
          <label class="space-y-1 text-[11px] font-medium text-content-muted">Nom de la composition
            <input v-model="compositionName" class="w-full rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent" placeholder="Salon · lampe allumée" />
          </label>
          <label class="space-y-1 text-[11px] font-medium text-content-muted">Guide blocking (media ID)
            <input v-model.number="guideMediaId" type="number" min="1" class="w-full rounded-md border border-edge bg-base px-3 py-2 font-mono text-xs text-content outline-none focus:border-accent" placeholder="Optionnel" />
          </label>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between"><h3 class="text-xs font-semibold text-content-secondary">Éléments à intégrer</h3><Button size="sm" variant="ghost" type="button" :disabled="items.length >= 7 || !eligiblePacks.length" @click="addItem"><PlusIcon class="h-4 w-4" /> Ajouter</Button></div>
          <div v-for="(item, index) in items" :key="item.key" class="grid gap-3 rounded-md bg-overlay-faint p-3 lg:grid-cols-[1fr_1fr_0.8fr_70px_70px_70px_32px]">
            <label class="space-y-1 text-[10px] text-content-muted">Identité
              <select v-model.number="item.pack_id" class="w-full rounded-md border border-edge bg-base px-2 py-2 text-xs text-content outline-none focus:border-accent" @change="onPackChange(item)">
                <option v-for="pack in eligiblePacks" :key="pack.id" :value="pack.id">{{ pack.element.name }}</option>
              </select>
            </label>
            <label class="space-y-1 text-[10px] text-content-muted">Vue approuvée
              <select v-model.number="item.view_id" class="w-full rounded-md border border-edge bg-base px-2 py-2 text-xs text-content outline-none focus:border-accent">
                <option v-for="view in approvedViews(item)" :key="view.id" :value="view.id">{{ view.label }} · rev {{ view.approved_revision_id }}</option>
              </select>
            </label>
            <label class="space-y-1 text-[10px] text-content-muted">État
              <select v-model.number="item.state_id" class="w-full rounded-md border border-edge bg-base px-2 py-2 text-xs text-content outline-none focus:border-accent">
                <option v-for="state in packFor(item)?.states || []" :key="state.id" :value="state.id">{{ state.label }}</option>
              </select>
            </label>
            <label class="space-y-1 text-[10px] text-content-muted">X<input v-model.number="item.x" type="number" min="0" max="1" step="0.05" class="w-full rounded-md border border-edge bg-base px-2 py-2 font-mono text-xs text-content outline-none focus:border-accent" /></label>
            <label class="space-y-1 text-[10px] text-content-muted">Y<input v-model.number="item.y" type="number" min="0" max="1" step="0.05" class="w-full rounded-md border border-edge bg-base px-2 py-2 font-mono text-xs text-content outline-none focus:border-accent" /></label>
            <label class="space-y-1 text-[10px] text-content-muted">Échelle<input v-model.number="item.scale" type="number" min="0.02" max="1" step="0.05" class="w-full rounded-md border border-edge bg-base px-2 py-2 font-mono text-xs text-content outline-none focus:border-accent" /></label>
            <div class="flex items-end"><Tooltip text="Retirer cet élément"><IconButton type="button" variant="danger" aria-label="Retirer cet élément" :disabled="items.length === 1" @click="items.splice(index, 1)"><TrashIcon class="h-4 w-4" /></IconButton></Tooltip></div>
          </div>
        </div>

        <label class="block space-y-1 text-[11px] font-medium text-content-muted">Instruction de composition
          <textarea v-model="promptDelta" rows="2" class="w-full resize-y rounded-md border border-edge bg-base px-3 py-2 text-xs text-content outline-none focus:border-accent" placeholder="Contraintes propres à cette insertion, sans redécrire le décor…" />
        </label>
        <div class="flex justify-end"><Button type="submit" :disabled="!canCreate || Boolean(busyAction)" :loading="busyAction === 'create-composition'"><PlusIcon class="h-4 w-4" /> Créer la composition verrouillée</Button></div>
      </form>
    </div>

    <section>
      <div class="mb-3"><h2 class="text-sm font-semibold text-content">Variantes composées</h2><p class="mt-1 text-xs text-content-muted">Le clean plate reste disponible sans prop ; chaque variante épingle ses révisions sources.</p></div>
      <div v-if="!locationPack.compositions.length" class="rounded-lg border border-dashed border-edge p-8 text-center text-xs text-content-muted">Aucune variante pour les vues de ce lieu.</div>
      <div v-else class="grid gap-4 xl:grid-cols-2">
        <article v-for="composition in locationPack.compositions" :key="composition.id" class="overflow-hidden rounded-lg border border-edge bg-surface">
          <div class="grid grid-cols-2 gap-px bg-edge-subtle">
            <div class="relative aspect-video bg-matte"><MediaImage :media-id="composition.base_location_media_id" :thumbnail="false" :contain="true" :enable-context-menu="false" alt="Clean plate sans prop" container-class="h-full w-full" img-class="h-full w-full object-contain" /><span class="absolute bottom-2 left-2 rounded bg-black/70 px-2 py-1 text-[9px] text-white">Sans prop · rev {{ composition.base_location_revision_id }}</span></div>
            <div class="relative aspect-video bg-matte"><MediaImage v-if="composition.candidate_media_id || composition.approved_media_id" :media-id="composition.candidate_media_id || composition.approved_media_id || undefined" :thumbnail="false" :contain="true" :enable-context-menu="false" alt="Composition avec prop" container-class="h-full w-full" img-class="h-full w-full object-contain" /><div v-else class="flex h-full items-center justify-center px-5 text-center text-[10px] text-content-muted">Prête à générer avec AGY</div><span class="absolute bottom-2 left-2 rounded bg-black/70 px-2 py-1 text-[9px] text-white">Avec prop{{ composition.approved_revision_id ? ` · rev ${composition.approved_revision_id}` : '' }}</span></div>
          </div>
          <div class="space-y-3 p-4">
            <div class="flex items-start justify-between gap-3"><div class="min-w-0"><h3 class="truncate text-xs font-semibold text-content">{{ composition.name }}</h3><p class="mt-1 truncate font-mono text-[9px] text-content-muted">{{ composition.items.map((item) => `@${item.reference_id}:${item.state_key}`).join(' · ') }}</p></div><ReferenceStatusBadge :status="composition.status" /></div>
            <div v-if="score(composition)" class="flex items-center justify-between rounded-md bg-overlay-faint px-3 py-2 text-[10px]"><span class="text-content-muted">Décor inchangé hors zone</span><span class="font-mono font-semibold" :class="composition.status === 'inconsistent' ? 'text-amber-400' : 'text-emerald-400'">{{ score(composition) }}</span></div>
            <div class="flex flex-wrap items-center gap-2">
              <Button v-if="!composition.candidate_media_id" size="sm" variant="secondary" :loading="busyAction === `composition:${composition.id}`" @click="$emit('generate', composition)"><ArrowPathIcon class="h-4 w-4" /> Générer avec AGY</Button>
              <template v-else><Button size="sm" :disabled="Boolean(busyAction) || composition.status === 'inconsistent'" @click="$emit('approve', composition)"><CheckIcon class="h-4 w-4" /> Approuver</Button><Button size="sm" variant="secondary" :disabled="Boolean(busyAction)" @click="$emit('reject', composition)"><XMarkIcon class="h-4 w-4" /> Rejeter</Button></template>
              <Tooltip text="Supprimer cette variante"><IconButton variant="danger" aria-label="Supprimer cette variante" :disabled="Boolean(busyAction)" @click="$emit('delete', composition)"><TrashIcon class="h-4 w-4" /></IconButton></Tooltip>
            </div>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>
