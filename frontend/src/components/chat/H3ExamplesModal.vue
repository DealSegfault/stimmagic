<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowLeftIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import Modal from '../ui/Modal.vue'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import SettingsDropdown from '../ui/SettingsDropdown.vue'
import Spinner from '../ui/Spinner.vue'
import H3ExamplePreview from './H3ExamplePreview.vue'
import { getH3Example, searchH3Examples } from '../../composables/useH3Examples'
import type { H3Example, H3ExampleReference } from '../../utils/h3Examples'

const props = defineProps<{ show: boolean; exampleId?: string | null }>()
const emit = defineEmits<{ close: []; select: [reference: H3ExampleReference] }>()
type View = { id: string; similar: string; q: string; style: string; topic: string }
const view = ref<View>({ id: '', similar: '', q: '', style: '', topic: '' })
const history = ref<View[]>([])
const detail = ref<H3Example | null>(null)
const items = ref<H3Example[]>([])
const total = ref(0)
const styles = ref<Record<string, string>>({})
const topics = ref<Record<string, string>>({})
const loading = ref(false)
const error = ref('')
const copied = ref(false)
const hoveredId = ref('')
const titleId = 'h3-examples-title'
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
let requestNumber = 0
let searchTimer: ReturnType<typeof setTimeout> | null = null
let hoverTimer: ReturnType<typeof setTimeout> | null = null
let copyTimer: ReturnType<typeof setTimeout> | null = null

const styleOptions = computed(() => [{ value: '', label: 'Tous les styles' }, ...Object.entries(styles.value).map(([value, label]) => ({ value, label }))])
const topicOptions = computed(() => [{ value: '', label: 'Tous les sujets' }, ...Object.entries(topics.value).map(([value, label]) => ({ value, label }))])

async function load(more = false) {
  const request = ++requestNumber
  loading.value = true
  error.value = ''
  const current = { ...view.value }
  if (!more) { items.value = []; detail.value = null; total.value = 0 }
  try {
    if (current.id) {
      const result = await getH3Example(current.id)
      if (request === requestNumber) detail.value = result
    } else {
      const result = await searchH3Examples({ q: current.q, style: current.style, topic: current.topic, similar_to: current.similar, offset: more ? items.value.length : 0, limit: 24 })
      if (request !== requestNumber) return
      items.value = more ? [...items.value, ...result.items] : result.items
      total.value = result.total
      styles.value = result.styles
      topics.value = result.topics
    }
  } catch {
    if (request === requestNumber) error.value = current.id ? 'Impossible de charger cet exemple.' : 'Impossible de charger les exemples.'
  } finally {
    if (request === requestNumber) loading.value = false
  }
}

function navigate(next: View) {
  history.value.push({ ...view.value })
  view.value = next
  copied.value = false
  stopHover()
  void load()
}

function openExample(id: string) { navigate({ ...view.value, id }) }
function back() {
  view.value = history.value.pop() || { id: '', similar: '', q: '', style: '', topic: '' }
  stopHover()
  void load()
}
function similar() {
  if (!detail.value) return
  navigate({ id: '', similar: detail.value.id, q: '', style: '', topic: '' })
}
function select() {
  if (!detail.value) return
  emit('select', { id: detail.value.id, label: `${detail.value.style_label} · ${detail.value.id}` })
  emit('close')
}
async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(detail.value?.prompt || '')
    copied.value = true
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copied.value = false }, 2000)
  } catch { error.value = 'Impossible de copier le prompt. Vous pouvez le sélectionner ci-dessous.' }
}
function stopHover() {
  if (hoverTimer) clearTimeout(hoverTimer)
  hoveredId.value = ''
}
function hover(id: string) {
  stopHover()
  if (!reducedMotion) hoverTimer = setTimeout(() => { hoveredId.value = id }, 400)
}
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const container = event.currentTarget as HTMLElement
  const controls = [...container.querySelectorAll<HTMLElement>('button:not(:disabled), input, a[href], summary, video[controls]')].filter((element) => element.getClientRects().length > 0)
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}

watch(() => [props.show, props.exampleId], () => {
  requestNumber++
  if (searchTimer) clearTimeout(searchTimer)
  stopHover()
  if (!props.show) return
  view.value = { id: props.exampleId || '', similar: '', q: '', style: '', topic: '' }
  history.value = []
  copied.value = false
  void load()
}, { immediate: true })

watch(() => [view.value.q, view.value.style, view.value.topic], () => {
  if (!props.show || view.value.id) return
  // Invalidate old searches immediately, before the debounce completes.
  requestNumber++
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void load() }, 250)
})

onBeforeUnmount(() => {
  requestNumber++
  if (searchTimer) clearTimeout(searchTimer)
  if (copyTimer) clearTimeout(copyTimer)
  stopHover()
})
</script>

<template>
  <Modal :show="show" size="custom" custom-class="w-[960px] max-w-[calc(100vw-2rem)] max-h-[calc(100dvh-2rem)] overflow-hidden" @close="emit('close')">
    <section role="dialog" aria-modal="true" :aria-labelledby="titleId" class="flex max-h-[calc(100dvh-2rem)] flex-col" @keydown="trapFocus">
      <header class="flex shrink-0 items-center justify-between gap-3 px-5 py-4">
        <div class="flex min-w-0 items-center gap-2">
          <IconButton v-if="view.id || history.length" aria-label="Retour aux exemples" @click="back"><ArrowLeftIcon class="h-4 w-4" /></IconButton>
          <h2 :id="titleId" class="truncate text-base font-medium text-content">{{ detail ? detail.style_label : view.similar ? 'Exemples similaires' : 'Styles vidéo' }}</h2>
          <span v-if="detail" class="font-mono text-xs text-content-muted">{{ detail.id }}</span>
        </div>
        <IconButton aria-label="Fermer les exemples" @click="emit('close')"><XMarkIcon class="h-4 w-4" /></IconButton>
      </header>

      <div v-if="!view.id" class="flex shrink-0 flex-wrap items-center gap-3 px-5 pb-4">
        <label class="min-w-0 flex-1 basis-64">
          <span class="sr-only">Rechercher un style ou une scène</span>
          <input v-model="view.q" type="search" maxlength="300" placeholder="Noir, mafieux, cigare…" class="w-full rounded-md border border-transparent bg-overlay-subtle px-3 py-2 text-sm text-content placeholder:text-content-muted focus:border-accent focus-visible:outline-none focus-visible:ring-2 ring-accent/40" />
        </label>
        <SettingsDropdown v-model="view.style" :options="styleOptions" aria-label="Filtrer par style" />
        <SettingsDropdown v-model="view.topic" :options="topicOptions" aria-label="Filtrer par sujet" />
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
        <div v-if="loading && !items.length && !detail" class="flex min-h-64 items-center justify-center" aria-label="Chargement des exemples"><Spinner /></div>
        <div v-else-if="detail" class="grid gap-5 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div class="min-w-0">
            <div class="h-[min(50vh,400px)] min-h-48">
              <H3ExamplePreview :key="detail.id" :example="detail" controls />
            </div>
            <p class="mt-2 font-mono text-xs tabular-nums text-content-muted">{{ detail.seconds }} s · {{ detail.w }} × {{ detail.h }} · {{ detail.shots }} {{ detail.shots === 1 ? 'plan' : 'plans' }} · T2VA</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Button size="sm" @click="select">Utiliser ce style</Button>
              <Button variant="ghost" size="sm" @click="similar">Exemples similaires</Button>
            </div>
            <p class="mt-2 text-xs text-content-muted">Le style sera adapté à votre scène.</p>
          </div>
          <div class="min-w-0 space-y-4 text-sm text-content-secondary">
            <section>
              <h3 class="text-xs font-medium text-content">Traitement visuel</h3>
              <p class="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">{{ detail.visual_treatment }}</p>
            </section>
            <section v-if="detail.camera">
              <h3 class="text-xs font-medium text-content">Caméra</h3>
              <p class="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed">{{ detail.camera }}</p>
            </section>
            <details>
              <summary class="text-xs font-medium text-content">Ambiance sonore et musique</summary>
              <p class="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{{ detail.soundscape }}</p>
              <p class="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{{ detail.music }}</p>
            </details>
            <details>
              <summary class="text-xs font-medium text-content">Prompt original</summary>
              <Button variant="ghost" size="sm" class="mt-2" @click="copyPrompt">{{ copied ? 'Copié' : 'Copier le prompt' }}</Button>
              <pre class="mt-2 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-content-secondary select-text">{{ detail.prompt }}</pre>
            </details>
            <div class="flex flex-wrap gap-3 text-xs text-content-muted">
              <a :href="detail.source_url" target="_blank" rel="noopener noreferrer" class="hover:text-content">Clip source · ostris</a>
              <a :href="detail.atlas_url" target="_blank" rel="noopener noreferrer" class="hover:text-content">Explorer H3 Atlas</a>
            </div>
          </div>
        </div>
        <template v-else-if="!view.id">
          <p v-if="!items.length && !loading && !error" class="py-16 text-center text-sm text-content-secondary">Aucun exemple pour cette recherche.</p>
          <div class="grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 lg:grid-cols-4">
            <button v-for="item in items" :key="item.id" type="button" class="group min-w-0 text-left focus-visible:outline-none focus-visible:ring-2 ring-accent/60" :aria-label="`Voir ${item.style_label}, exemple ${item.id}`" @click="openExample(item.id)" @pointerenter="hover(item.id)" @pointerleave="stopHover" @focus="hover(item.id)" @blur="stopHover">
              <div class="aspect-video"><H3ExamplePreview :example="item" :preview="hoveredId === item.id" /></div>
              <div class="mt-2 flex items-center justify-between gap-2 text-xs text-content-secondary"><span class="truncate">{{ item.style_label }}</span><span class="shrink-0 font-mono text-content-muted">{{ item.id }}</span></div>
              <p class="mt-1 line-clamp-2 text-xs leading-relaxed text-content-muted">{{ item.excerpt }}</p>
            </button>
          </div>
          <div v-if="items.length < total" class="mt-5 flex justify-center"><Button variant="ghost" size="sm" :loading="loading" @click="load(true)">Voir plus</Button></div>
        </template>
        <div v-if="error" role="alert" class="flex flex-wrap items-center gap-2 py-4 text-sm text-content-secondary">{{ error }}<Button variant="ghost" size="sm" @click="load()">Réessayer</Button></div>
      </div>
      <footer v-if="!view.id" class="flex shrink-0 flex-wrap items-center justify-between gap-2 px-5 py-3 text-xs text-content-muted">
        <span aria-live="polite" class="font-mono tabular-nums">{{ total }} exemples</span>
        <span>Clips et prompts · ostris · <a href="https://cohub.live/baize/video-altas/w/h3-atlas" target="_blank" rel="noopener noreferrer" class="hover:text-content">H3 Atlas</a></span>
      </footer>
    </section>
  </Modal>
</template>
