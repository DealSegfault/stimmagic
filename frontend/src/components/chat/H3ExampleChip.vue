<script setup lang="ts">
import { onBeforeUnmount, ref, useId } from 'vue'
import AppImage from '../media/AppImage.vue'
import Button from '../ui/Button.vue'
import H3ExamplePreview from './H3ExamplePreview.vue'
import { getH3Example, getH3ThumbnailUrl } from '../../composables/useH3Examples'
import { useAnchoredMenuPosition } from '../../composables/useContextMenuPosition'
import type { H3Example } from '../../utils/h3Examples'

const props = defineProps<{ id: string; label: string }>()
const emit = defineEmits<{ open: [id: string] }>()
const anchor = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const anchorRect = ref<DOMRect | null>(null)
const visible = ref(false)
const example = ref<H3Example | null>(null)
const tooltipId = useId()
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const { menuStyle } = useAnchoredMenuPosition(panel, anchorRect, visible, { gap: 6 })
let timer: ReturnType<typeof setTimeout> | null = null
let hovering = false

function hide() {
  hovering = false
  if (timer) clearTimeout(timer)
  timer = null
  visible.value = false
}

function show() {
  hide()
  hovering = true
  timer = setTimeout(async () => {
    try {
      example.value = await getH3Example(props.id)
      if (!hovering) return
      anchorRect.value = anchor.value?.getBoundingClientRect() ?? null
      visible.value = true
    } catch { /* The detail panel presents retry/error state on click. */ }
  }, 400)
}

function open() { hide(); emit('open', props.id) }
onBeforeUnmount(hide)
</script>

<template>
  <span ref="anchor" class="not-prose inline-flex max-w-full align-middle" @pointerenter="show" @pointerleave="hide" @focusin="show" @focusout="hide" @keydown.esc.stop="hide">
    <Button variant="ghost" size="sm" :aria-describedby="visible ? tooltipId : undefined" :aria-label="`Voir l’exemple ${label}`" @click.stop="open">
      <AppImage :src="getH3ThumbnailUrl(id)" alt="" container-class="h-6 w-8 shrink-0 overflow-hidden rounded-media bg-matte" img-class="h-full w-full object-cover" />
      <span class="min-w-0 truncate">{{ label || `H3 ${id}` }}</span>
    </Button>
    <Teleport to="body">
      <div v-if="visible && example" :id="tooltipId" ref="panel" role="tooltip" class="pointer-events-none fixed z-menu w-72 max-w-[calc(100vw-1rem)] overflow-hidden rounded-lg border border-edge-subtle bg-surface shadow-lg" :style="menuStyle">
        <div class="aspect-video">
          <H3ExamplePreview :example="example" :preview="!reducedMotion" />
        </div>
        <div class="flex items-center justify-between gap-2 px-3 py-2 text-xs text-content-secondary">
          <span>{{ example.style_label }}</span>
          <span class="font-mono tabular-nums">{{ example.seconds }} s</span>
        </div>
      </div>
    </Teleport>
  </span>
</template>
