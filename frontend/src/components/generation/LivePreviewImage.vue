<template>
  <!-- Double-buffered live preview frame. Two stacked <img> layers: a new
       frame is assigned to the hidden layer and only revealed on its own
       `load` event, so the previously shown frame stays painted the entire
       time. Swapping a single <img>'s src blanks the element while the new
       image attaches/decodes — brief, but very visible as a flash to black
       when frames arrive every few seconds.
       Transient blob: URLs only — never library media, hence raw <img>. -->
  <div class="relative w-full h-full">
    <img
      v-for="(buf, i) in buffers"
      :key="i"
      :src="buf.url || undefined"
      :class="[
        'absolute inset-0 w-full h-full',
        contain ? 'object-contain object-top' : 'object-cover',
        buf.url && i === frontIndex ? 'opacity-100' : 'opacity-0',
      ]"
      draggable="false"
      alt=""
      @load="onBufferLoad(i)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  /** Ephemeral blob: URL of the current preview frame. */
  url?: string
  /** Fit the whole frame (hero) vs fill the box (tile). */
  contain?: boolean
}>(), {
  url: '',
  contain: false,
})

const buffers = ref<{ url: string }[]>([{ url: '' }, { url: '' }])
const frontIndex = ref(0)

watch(() => props.url, (next) => {
  if (!next) {
    // Job settled / preview cleared: drop both layers.
    buffers.value = [{ url: '' }, { url: '' }]
    return
  }
  if (buffers.value[frontIndex.value].url === next) return
  // Stage into the back buffer; onBufferLoad flips once it's painted.
  const back = frontIndex.value === 0 ? 1 : 0
  buffers.value[back] = { url: next }
}, { immediate: true })

function onBufferLoad(i: number) {
  // Only promote the back buffer — a late load event from the front one
  // (same frame re-decoding) must not toggle anything.
  if (i !== frontIndex.value && buffers.value[i].url) {
    frontIndex.value = i
  }
}
</script>
