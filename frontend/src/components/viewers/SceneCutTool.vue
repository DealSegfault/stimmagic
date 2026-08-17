<template>
  <div class="relative">
    <button
      type="button"
      class="relative flex h-8 w-8 items-center justify-center rounded-full text-white/60 transition-colors hover:bg-white/10 hover:text-white"
      :class="open ? 'bg-white/10 text-white' : ''"
      title="Couper ici"
      aria-label="Couper ici"
      @click.stop="cutAtPlayhead"
    >
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" class="h-5 w-5">
        <path stroke-linecap="round" stroke-linejoin="round" d="m7.5 4.5 9 15m0-15-9 15M5.25 6.75h.008v.008H5.25V6.75Zm13.5 0h.008v.008h-.008V6.75ZM5.25 17.25h.008v.008H5.25v-.008Zm13.5 0h.008v.008h-.008v-.008Z" />
      </svg>
      <span
        v-if="cutPoints.length > 0"
        class="absolute -right-1 -top-1 min-w-[14px] rounded-full bg-amber-300 px-1 text-[9px] font-semibold leading-[14px] text-black"
      >
        {{ cutPoints.length }}
      </span>
    </button>

    <section
      v-if="open"
      class="absolute bottom-full left-0 z-menu mb-2 w-[min(340px,calc(100vw-24px))] overflow-hidden rounded-lg border border-white/10 bg-[#15171d]/95 p-3 text-white shadow-2xl backdrop-blur-xl"
      aria-label="Prévisualisation des découpes"
      @click.stop
    >
      <header class="mb-2 flex items-center justify-between gap-3">
        <div>
          <div class="text-xs font-semibold">Découper la scène</div>
          <div class="mt-0.5 truncate text-[10px] text-white/50">{{ sourceName || 'Vidéo en cours' }}</div>
        </div>
        <button
          type="button"
          class="rounded p-1 text-white/50 hover:bg-white/10 hover:text-white"
          title="Fermer"
          aria-label="Fermer"
          @click="open = false"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" class="h-4 w-4">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </header>

      <div class="relative mb-3 h-12 overflow-hidden rounded border border-white/10 bg-black">
        <img v-if="filmstripUrl" :src="filmstripUrl" alt="Prévisualisation de la scène" class="h-full w-full object-fill" draggable="false" />
        <div v-else class="flex h-full items-center justify-center text-[10px] text-white/40">Prévisualisation indisponible</div>
        <div class="absolute inset-0 bg-black/20" />
        <div
          v-for="point in cutPoints"
          :key="`preview-cut-${point}`"
          class="absolute inset-y-0 w-0.5 bg-amber-300"
          style="box-shadow: 0 0 6px rgba(252,211,77,.9)"
          :style="{ left: `${duration > 0 ? (point / duration) * 100 : 0}%` }"
        />
      </div>

      <div v-if="cutPoints.length === 0" class="rounded border border-dashed border-white/10 px-3 py-2 text-[10px] text-white/50">
        Place la tête de lecture, puis clique à nouveau sur le bouton cut.
      </div>

      <div v-else class="space-y-1.5">
        <div class="text-[10px] font-medium text-white/60">{{ segments.length }} plans seront créés</div>
        <div v-for="segment in segments" :key="segment.index" class="flex items-center justify-between rounded bg-white/[0.05] px-2 py-1.5 text-[10px]">
          <span class="text-white/70">Plan {{ segment.index }}</span>
          <span class="font-mono tabular-nums text-white/50">{{ formatDuration(segment.start) }} → {{ formatDuration(segment.end) }}</span>
        </div>
        <div class="flex flex-wrap gap-1 pt-1">
          <button
            v-for="point in cutPoints"
            :key="`remove-cut-${point}`"
            type="button"
            class="rounded-full bg-amber-300/15 px-2 py-1 font-mono text-[10px] text-amber-200 hover:bg-amber-300/25"
            :title="`Supprimer la coupe à ${formatDuration(point)}`"
            @click="removeCut(point)"
          >
            {{ formatDuration(point) }} ×
          </button>
        </div>
      </div>

      <p v-if="message" class="mt-2 text-[10px]" :class="error ? 'text-red-300' : 'text-emerald-300'">{{ message }}</p>

      <button
        v-if="cutPoints.length > 0"
        type="button"
        class="mt-3 w-full rounded-md bg-amber-300 px-3 py-2 text-[11px] font-semibold text-black transition-colors hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="splitting"
        @click="splitScene"
      >
        {{ splitting ? 'Création des assets…' : `Valider · créer ${segments.length} assets` }}
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'

const props = withDefaults(defineProps<{
  mediaId?: number | null
  sourceName?: string | null
  currentTime?: number
  videoDuration?: number
  filmstripUrl?: string
}>(), {
  mediaId: null,
  sourceName: null,
  currentTime: 0,
  videoDuration: 0,
  filmstripUrl: '',
})

const emit = defineEmits<{
  (event: 'cuts-updated', payload: number[]): void
  (event: 'clips-created', payload: { clips: Array<{ media_id: number; asset_id?: number | null }> }): void
}>()

const open = ref(false)
const cutPoints = ref<number[]>([])
const splitting = ref(false)
const message = ref('')
const error = ref(false)

const duration = computed(() => Math.max(0, Number(props.videoDuration) || 0))
const segments = computed(() => {
  const boundaries = [0, ...cutPoints.value, duration.value]
  return boundaries.slice(0, -1).map((start, index) => ({
    index: index + 1,
    start,
    end: boundaries[index + 1],
  }))
})

const canCut = computed(() => {
  const time = Number(props.currentTime) || 0
  return Boolean(
    Number(props.mediaId) > 0
    && duration.value > 0.5
    && time > 0.2
    && time < duration.value - 0.2
    && !cutPoints.value.some(point => Math.abs(point - time) < 0.1),
  )
})

function formatDuration(value: number) {
  const seconds = Math.max(0, Number(value) || 0)
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  return `${minutes}:${(seconds % 60).toFixed(2).padStart(5, '0')}`
}

function cutAtPlayhead() {
  error.value = false
  message.value = ''
  if (canCut.value) {
    const time = Math.round((Number(props.currentTime) || 0) * 100) / 100
    cutPoints.value = [...cutPoints.value, time].sort((a, b) => a - b)
    emit('cuts-updated', cutPoints.value)
  } else if (cutPoints.value.length === 0) {
    message.value = 'Place la tête de lecture sur une coupe valide.'
  }
  open.value = true
}

function removeCut(point: number) {
  cutPoints.value = cutPoints.value.filter(value => value !== point)
  message.value = ''
  emit('cuts-updated', cutPoints.value)
}

async function splitScene() {
  if (!props.mediaId || cutPoints.value.length === 0 || splitting.value) return
  splitting.value = true
  error.value = false
  message.value = ''
  try {
    const { data } = await axios.post('/api/generate/split-video', {
      media_id: props.mediaId,
      cut_points: cutPoints.value,
      project_id: null,
    })
    const count = data.clips?.length || 0
    message.value = `${count} asset${count > 1 ? 's' : ''} créé${count > 1 ? 's' : ''}.`
    emit('clips-created', { clips: data.clips || [] })
    cutPoints.value = []
    emit('cuts-updated', [])
  } catch (requestError: any) {
    error.value = true
    message.value = requestError?.response?.data?.detail || 'Impossible de créer les assets.'
  } finally {
    splitting.value = false
  }
}

watch(() => props.mediaId, () => {
  cutPoints.value = []
  open.value = false
  message.value = ''
  error.value = false
})
</script>
