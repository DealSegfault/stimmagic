<script setup lang="ts">
/**
 * Place vector annotations: text, shapes, redaction.
 *
 * Annotate is a container op with parametric physics — the shapes ARE the
 * params, so re-rendering at any size is free and re-entering the step is
 * lossless. Shapes use the snapshot editor's own schema (normalised 0-1
 * coordinates) so the shared renderer draws them and a migrated document and a
 * newly authored one are the same thing.
 */
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  source: HTMLCanvasElement | null
  displayWidth: number
  displayHeight: number
  tool?: 'text' | 'shape' | 'redact'
  shapeKind?: 'rectangle' | 'ellipse' | 'line'
  textStyle?: 'pill' | 'plain' | 'outline' | 'neon'
  color?: string
}>(), {
  tool: 'text',
  shapeKind: 'rectangle',
  textStyle: 'pill',
  color: '#ffffff',
})

const emit = defineEmits<{ add: [any] }>()

const overlay = ref<HTMLElement | null>(null)
const pendingText = ref<{ x: number; y: number } | null>(null)
const draftText = ref('')

let dragStart: { x: number; y: number } | null = null
const dragCurrent = ref<{ x: number; y: number } | null>(null)

/** Normalised 0-1 in the composite's space, as the shape schema expects. */
function normalised(event: PointerEvent | MouseEvent) {
  const rect = overlay.value!.getBoundingClientRect()
  return {
    x: (event.clientX - rect.left) / Math.max(1, rect.width),
    y: (event.clientY - rect.top) / Math.max(1, rect.height),
  }
}

function hexToColor(hex: string) {
  const value = hex.replace('#', '')
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
    a: 1,
  }
}

function newId() {
  return `shape-${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`
}

function onClick(event: MouseEvent) {
  if (props.tool !== 'text') return
  pendingText.value = normalised(event)
  draftText.value = ''
}

function commitText() {
  const at = pendingText.value
  const text = draftText.value.trim()
  pendingText.value = null
  if (!at || !text) return

  const colour = hexToColor(props.color)
  // Rough metrics: the renderer scales from baseWidth/baseHeight, so an
  // estimate here only sets the initial box, not the fidelity.
  const width = Math.min(0.9, 0.03 * text.length + 0.04)
  const height = 0.07

  emit('add', {
    id: newId(),
    type: 'text',
    x: at.x, y: at.y,
    rotation: 0, opacity: 1,
    text,
    width, height, baseWidth: width, baseHeight: height,
    fontFamily: 'Inter, system-ui, sans-serif',
    fontWeight: props.textStyle === 'plain' ? 'normal' : 'bold',
    fontStyle: 'normal',
    textAlign: 'center',
    textColor: colour,
    ...(props.textStyle === 'pill'
      ? {
          backgroundColor: { r: 0, g: 0, b: 0, a: 0.65 },
          backgroundPadding: 0.35,
          backgroundCornerRadius: 1,
        }
      : {}),
    ...(props.textStyle === 'outline'
      ? { textEffect: 'outline', strokeColor: { r: 0, g: 0, b: 0, a: 1 }, strokeWidth: 0.01 }
      : {}),
    ...(props.textStyle === 'neon'
      ? { textEffect: 'neon', glowIntensity: 70, glowColor: colour }
      : {}),
  })
}

function onPointerDown(event: PointerEvent) {
  if (props.tool === 'text') return
  dragStart = normalised(event)
  dragCurrent.value = dragStart
  overlay.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!dragStart) return
  dragCurrent.value = normalised(event)
}

function onPointerUp(event: PointerEvent) {
  const from = dragStart
  const to = dragCurrent.value
  dragStart = null
  dragCurrent.value = null
  overlay.value?.releasePointerCapture(event.pointerId)
  if (!from || !to) return

  const width = Math.abs(to.x - from.x)
  const height = Math.abs(to.y - from.y)
  if (width < 0.01 || height < 0.01) return
  const x = (from.x + to.x) / 2
  const y = (from.y + to.y) / 2
  const colour = hexToColor(props.color)

  if (props.tool === 'redact') {
    emit('add', {
      id: newId(), type: 'redact',
      x, y, rotation: 0, opacity: 1,
      width, height, blockSize: 16,
    })
    return
  }

  if (props.shapeKind === 'line') {
    emit('add', {
      id: newId(), type: 'line',
      x: from.x, y: from.y, rotation: 0, opacity: 1,
      x2: to.x, y2: to.y,
      strokeColor: colour, strokeWidth: 0.006,
    })
    return
  }

  emit('add', {
    id: newId(),
    type: props.shapeKind,
    x, y, rotation: 0, opacity: 1,
    width, height,
    strokeColor: colour,
    strokeWidth: 0.006,
  })
}

const draftBox = computed(() => {
  if (!dragStart || !dragCurrent.value) return null
  const from = dragStart
  const to = dragCurrent.value
  return {
    left: `${Math.min(from.x, to.x) * 100}%`,
    top: `${Math.min(from.y, to.y) * 100}%`,
    width: `${Math.abs(to.x - from.x) * 100}%`,
    height: `${Math.abs(to.y - from.y) * 100}%`,
  }
})
</script>

<template>
  <div
    ref="overlay"
    class="absolute inset-0 cursor-crosshair touch-none"
    :style="{ width: displayWidth + 'px', height: displayHeight + 'px' }"
    @click="onClick"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
  >
    <div
      v-if="draftBox"
      class="pointer-events-none absolute border border-white/80"
      :style="draftBox"
    />

    <!-- Text is typed where it lands, so what you see is where it goes. -->
    <div
      v-if="pendingText"
      class="absolute -translate-x-1/2 -translate-y-1/2"
      :style="{ left: pendingText.x * 100 + '%', top: pendingText.y * 100 + '%' }"
    >
      <input
        v-model="draftText"
        autofocus
        placeholder="Type, then Enter"
        class="px-2 py-1 text-sm rounded-md bg-surface-overlay border border-edge-strong text-content focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        @keydown.enter.stop="commitText"
        @keydown.esc.stop="pendingText = null"
        @blur="commitText"
        @click.stop
      />
    </div>
  </div>
</template>
