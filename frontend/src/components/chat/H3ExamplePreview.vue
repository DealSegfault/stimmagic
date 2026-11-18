<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppImage from '../media/AppImage.vue'
import Button from '../ui/Button.vue'
import type { H3Example } from '../../utils/h3Examples'

const props = withDefaults(defineProps<{
  example: H3Example
  preview?: boolean
  controls?: boolean
}>(), { preview: false, controls: false })

const video = ref<HTMLVideoElement | null>(null)
const failed = ref(false)
const attempt = ref(0)
const playing = computed(() => props.preview || props.controls)

watch(() => [props.example.id, playing.value, attempt.value], async () => {
  failed.value = false
  await nextTick()
  if (props.preview && !props.controls && video.value) {
    // Autoplay failure leaves the still visible; opening details provides native Play.
    try { await video.value.play() } catch { /* Browser autoplay policy. */ }
  }
}, { immediate: true })
</script>

<template>
  <div class="relative h-full w-full overflow-hidden rounded-media bg-matte">
    <AppImage
      :src="example.thumbnail_url"
      :alt="example.style_label"
      container-class="h-full w-full"
      img-class="h-full w-full object-contain"
    />
    <video
      v-if="playing && !failed"
      :key="`${example.id}:${attempt}`"
      ref="video"
      :src="example.video_url"
      :poster="example.thumbnail_url"
      :controls="controls"
      :muted="!controls"
      :loop="!controls"
      :preload="controls ? 'metadata' : 'none'"
      playsinline
      class="absolute inset-0 h-full w-full object-contain"
      :aria-label="`Exemple ${example.id} · ${example.style_label}`"
      @error="failed = true"
    />
    <div v-if="failed && controls" class="absolute inset-x-0 bottom-0 flex flex-wrap items-center justify-center gap-2 bg-surface/95 p-3">
      <span class="text-xs text-content-secondary">Vidéo indisponible pour le moment.</span>
      <Button variant="ghost" size="sm" @click="attempt++">Réessayer</Button>
    </div>
  </div>
</template>
