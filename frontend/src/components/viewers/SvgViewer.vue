<!--
  Viewer for .svg documents.

  The document renders through an <img>, never by inlining its markup into the
  page. An <img>-loaded SVG cannot execute script or fetch anything, so a file
  that arrived from a watched Source is inert here regardless of what it
  contains — and its ids and styles cannot collide with the app shell.
-->
<template>
  <div
    ref="containerRef"
    class="w-full h-full flex flex-col items-center justify-center overflow-hidden"
  >
    <div v-if="loading" class="text-content-tertiary text-sm">
      Loading…
    </div>

    <div v-else-if="error" class="text-sm text-content-secondary px-6 text-center">
      {{ error }}
    </div>

    <template v-else>
      <div class="flex-1 min-h-0 w-full flex items-center justify-center p-4">
        <div :class="['overflow-hidden rounded-media', backgroundClass]" :style="stageStyle">
          <img
            :src="documentUrl"
            :style="imageStyle"
            class="block"
            :alt="`SVG document, ${naturalWidth} by ${naturalHeight}`"
            draggable="false"
            @error="imageFailed = true"
            @load="imageFailed = false"
          />
        </div>
      </div>

      <div class="flex-shrink-0 flex items-center gap-4 px-4 pb-3 pt-1">
        <div class="flex items-center gap-1">
          <button
            v-for="option in ZOOM_OPTIONS"
            :key="option.value"
            :class="toggleClass(zoom === option.value)"
            @click="zoom = option.value"
          >
            {{ option.label }}
          </button>
        </div>

        <div class="w-px h-5 bg-edge"></div>

        <div class="flex items-center gap-1">
          <button
            v-for="option in BACKGROUND_OPTIONS"
            :key="option.value"
            :class="toggleClass(background === option.value)"
            @click="background = option.value"
          >
            {{ option.label }}
          </button>
        </div>

        <div class="text-xs text-content-tertiary tabular-nums">
          {{ naturalWidth }} × {{ naturalHeight }}
        </div>
      </div>

      <div
        v-if="imageFailed"
        class="flex-shrink-0 px-4 pb-3 text-xs text-content-secondary text-center"
      >
        The document could not be rendered.
      </div>

      <div
        v-else-if="warnings.length"
        class="flex-shrink-0 px-4 pb-3 text-xs text-content-tertiary max-w-xl text-center"
      >
        {{ warnings.join(' · ') }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { getApiBase } from '../../apiConfig'
import { useMediaApi } from '../../composables/useMediaApi'

const props = defineProps({
  mediaId: {
    type: Number,
    required: true,
  },
})

const ZOOM_OPTIONS = [
  { value: 'fit', label: 'Fit' },
  { value: 1, label: '100%' },
  { value: 2, label: '200%' },
]

// Transparency is the normal state for an icon or a logo, so the ground is a
// control rather than a fixed choice: a white mark and a black mark cannot both
// be legible against the same backdrop.
const BACKGROUND_OPTIONS = [
  { value: 'checker', label: 'Checker' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

const loading = ref(true)
const error = ref(null)
const naturalWidth = ref(0)
const naturalHeight = ref(0)
const warnings = ref([])
const zoom = ref('fit')
const background = ref('checker')
const imageFailed = ref(false)

const containerRef = ref(null)
const containerWidth = ref(0)
const containerHeight = ref(0)
let resizeObserver = null

const { getSvgDocumentUrl } = useMediaApi()

// Built by useMediaApi, not by hand: an <img> cannot send the X-Profile-ID
// header, so the URL has to carry its database in the path.
const documentUrl = computed(() => getSvgDocumentUrl(props.mediaId))

const backgroundClass = computed(() => ({
  checker: 'bg-checker',
  light: 'bg-white',
  dark: 'bg-black',
}[background.value]))

function toggleClass(active) {
  const base = 'px-2.5 h-7 rounded text-xs font-medium transition-colors cursor-pointer'
  return active
    ? `${base} bg-accent/15 text-accent-hi`
    : `${base} text-content-tertiary hover:text-content hover:bg-surface`
}

const scale = computed(() => {
  if (zoom.value !== 'fit') return zoom.value
  if (!containerWidth.value || !containerHeight.value) return 1
  if (!naturalWidth.value || !naturalHeight.value) return 1
  // Padding allowance matches the p-4 on the stage wrapper.
  const available = Math.max(1, containerWidth.value - 32)
  const availableHeight = Math.max(1, containerHeight.value - 32)
  return Math.min(available / naturalWidth.value, availableHeight / naturalHeight.value, 1)
})

const renderWidth = computed(() => Math.max(1, Math.round(naturalWidth.value * scale.value)))
const renderHeight = computed(() => Math.max(1, Math.round(naturalHeight.value * scale.value)))

const stageStyle = computed(() => ({
  width: `${renderWidth.value}px`,
  height: `${renderHeight.value}px`,
}))

const imageStyle = computed(() => ({
  width: `${renderWidth.value}px`,
  height: `${renderHeight.value}px`,
}))

onMounted(() => {
  resizeObserver = new ResizeObserver(entries => {
    for (const entry of entries) {
      containerWidth.value = entry.contentRect.width
      containerHeight.value = entry.contentRect.height
    }
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

async function loadInfo() {
  loading.value = true
  error.value = null
  warnings.value = []
  imageFailed.value = false
  try {
    const { data } = await axios.get(`${getApiBase()}/media/${props.mediaId}/svg-info`)
    naturalWidth.value = data.width
    naturalHeight.value = data.height
    warnings.value = data.warnings || []
  } catch (e) {
    error.value = e.response?.data?.detail || `Failed to load SVG: ${e.message}`
  } finally {
    loading.value = false
  }
}

watch(() => props.mediaId, loadInfo, { immediate: true })
</script>
