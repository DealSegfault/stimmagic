<script setup lang="ts">
/**
 * The selected annotation's properties.
 *
 * An annotation IS mutable later — its colour, its weight, its glow, its text
 * — so by the placement rule everything here belongs in the inspector rather
 * than the toolbar. The toolbar only carries what is consumed at the moment of
 * the gesture: which tool, and the colour the next one starts with.
 *
 * Colours use the ported picker, so the annotation surface offers the same
 * spectrum, palette and eyedropper as everywhere else.
 */
import { computed } from 'vue'
import ColorPicker from '../ported/ColorPicker.vue'
import ToolbarPopover from './ToolbarPopover.vue'
import ToolIcon from './ToolIcon.vue'
import type { Shape } from '../ported/shapeTypes'
import type { RgbaColor } from '../ported/geometry'

const props = defineProps<{
  shape: Shape | null
  /** Colours sampled from the image, offered alongside the fixed swatches. */
  palette?: RgbaColor[]
}>()

const emit = defineEmits<{
  change: [Record<string, any>]
  remove: []
}>()

const any = computed(() => props.shape as any)

/** The families every OS ships, so nothing here depends on a webfont. */
const FONTS = [
  { id: 'Inter, system-ui, sans-serif', label: 'Sans' },
  { id: 'Georgia, "Times New Roman", serif', label: 'Serif' },
  { id: 'ui-monospace, Menlo, Consolas, monospace', label: 'Mono' },
  { id: '"Comic Sans MS", "Chalkboard SE", cursive', label: 'Casual' },
  { id: 'Impact, "Haettenschweiler", sans-serif', label: 'Poster' },
]

function rgbaCss(color: any) {
  if (!color) return 'transparent'
  if (typeof color === 'string') return color
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${color.a ?? 1})`
}

/** Text scale, derived from the box against its measured natural size. */
const textScale = computed(() => {
  const shape = any.value
  if (!shape?.baseHeight) return 1
  return shape.height / shape.baseHeight
})

function setTextScale(scale: number) {
  const shape = any.value
  if (!shape?.baseHeight) return
  emit('change', { width: shape.baseWidth * scale, height: shape.baseHeight * scale })
}

/** Which controls this kind of shape actually has. */
const hasStroke = computed(() =>
  !!props.shape && ['rectangle', 'ellipse', 'line', 'curved-arrow', 'path', 'text'].includes(props.shape.type)
)
const hasFill = computed(() =>
  !!props.shape && ['rectangle', 'ellipse'].includes(props.shape.type)
)
const isText = computed(() => props.shape?.type === 'text')
const isPath = computed(() => props.shape?.type === 'path')
const isLine = computed(() =>
  props.shape?.type === 'line' || props.shape?.type === 'curved-arrow'
)
const isRect = computed(() => props.shape?.type === 'rectangle')

/**
 * How the stroke is laid down, as opposed to what colour it is.
 *
 * A pen stroke has a character — how hard its edge is, how much paint each
 * stamp lays, how far apart the stamps fall, and how much they wander. The old
 * editor exposed all of it and a Path without it is just a coloured line.
 */
const PATH_STYLE = [
  { key: 'hardness', label: 'Hardness', min: 0, max: 100, step: 1, fallback: 100 },
  { key: 'flow', label: 'Flow', min: 1, max: 100, step: 1, fallback: 100 },
  { key: 'spacing', label: 'Spacing', min: 1, max: 100, step: 1, fallback: 25 },
  { key: 'jitter', label: 'Jitter', min: 0, max: 100, step: 1, fallback: 0 },
  { key: 'scatter', label: 'Scatter', min: 0, max: 100, step: 1, fallback: 0 },
]

/** Ends, so an arrow can be an arrow at either end or neither. */
const LINE_ENDS = [
  { id: 'none', label: 'None' },
  { id: 'arrow', label: 'Arrow' },
  { id: 'arrow-solid', label: 'Solid arrow' },
  { id: 'circle', label: 'Circle' },
  { id: 'circle-solid', label: 'Solid circle' },
  { id: 'square', label: 'Square' },
  { id: 'square-solid', label: 'Solid square' },
  { id: 'bar', label: 'Bar' },
]

function numberOr(key: string, fallback: number): number {
  const value = any.value?.[key]
  return typeof value === 'number' ? value : fallback
}

/** Neon is a universal shape style; text spells it as a text effect. */
const glowOn = computed(() =>
  isText.value ? any.value?.textEffect === 'neon' : any.value?.style?.effect === 'neon'
)

function setGlow(on: boolean) {
  if (isText.value) {
    emit('change', { textEffect: on ? 'neon' : 'none', glowIntensity: any.value?.glowIntensity ?? 60 })
  } else {
    emit('change', {
      style: { ...(any.value?.style || {}), effect: on ? 'neon' : 'none', glowIntensity: any.value?.style?.glowIntensity ?? 60 },
    })
  }
}

function setGlowIntensity(value: number) {
  if (isText.value) emit('change', { glowIntensity: value })
  else emit('change', { style: { ...(any.value?.style || {}), effect: 'neon', glowIntensity: value } })
}

const glowIntensity = computed(() =>
  (isText.value ? any.value?.glowIntensity : any.value?.style?.glowIntensity) ?? 60
)
</script>

<template>
  <div v-if="shape" class="divide-y divide-edge-subtle">
    <header class="px-3 py-2 flex items-center gap-2">
      <h3 class="text-sm text-content flex-1 capitalize">
        {{ shape.type.replace('-', ' ') }}
      </h3>
      <button
        type="button"
        class="p-1 rounded-md text-content-tertiary hover:text-red-400 hover:bg-overlay-subtle"
        aria-label="Delete annotation"
        @click="emit('remove')"
      >
        <ToolIcon name="trash" />
      </button>
    </header>

    <section v-if="isText" class="px-3 py-2 space-y-2">
      <textarea
        class="w-full px-2 py-1.5 text-sm rounded-md bg-surface-raised text-content resize-none focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        rows="2"
        :value="any.text"
        @input="emit('change', { text: ($event.target as HTMLTextAreaElement).value })"
      />
      <select
        class="w-full px-2 py-1.5 text-xs rounded-md bg-surface-raised text-content focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :value="any.fontFamily"
        @change="emit('change', { fontFamily: ($event.target as HTMLSelectElement).value })"
      >
        <option v-for="font in FONTS" :key="font.id" :value="font.id" :style="{ fontFamily: font.id }">
          {{ font.label }}
        </option>
      </select>

      <div class="flex items-center gap-1">
        <button
          type="button"
          class="px-2 py-1 text-[11px] rounded-md font-bold"
          :class="any.fontWeight === 'bold'
            ? 'bg-selection/20 text-content'
            : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          aria-label="Bold"
          @click="emit('change', { fontWeight: any.fontWeight === 'bold' ? 'normal' : 'bold' })"
        >
          <ToolIcon name="bold" />
        </button>
        <button
          type="button"
          class="px-2 py-1 text-[11px] rounded-md"
          :class="any.fontStyle === 'italic'
            ? 'bg-selection/20 text-content'
            : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          aria-label="Italic"
          @click="emit('change', { fontStyle: any.fontStyle === 'italic' ? 'normal' : 'italic' })"
        >
          <ToolIcon name="italic" />
        </button>
        <span class="w-px h-4 bg-edge-subtle mx-1" />
        <button
          v-for="align in [
            { id: 'left', icon: 'alignLeft' },
            { id: 'center', icon: 'alignCenter' },
            { id: 'right', icon: 'alignRight' },
          ]"
          :key="align.id"
          type="button"
          class="px-2 py-1 rounded-md"
          :class="any.textAlign === align.id
            ? 'bg-selection/20 text-content'
            : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          :aria-label="align.id"
          @click="emit('change', { textAlign: align.id })"
        >
          <ToolIcon :name="(align.icon as any)" />
        </button>
      </div>

      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Size
        <input
          type="range" min="0.2" max="4" step="0.05" class="flex-1"
          :value="textScale"
          @input="setTextScale(Number(($event.target as HTMLInputElement).value))"
        />
        <span class="w-8 text-right tabular-nums">{{ textScale.toFixed(1) }}×</span>
      </label>
    </section>

    <section v-if="hasStroke" class="px-3 py-2 space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-[11px] text-content-tertiary flex-1">{{ isText ? 'Text' : 'Stroke' }}</span>
        <ToolbarPopover label="" :width="292">
          <template #trigger>
            <span class="colour-well">
              <span :style="{ background: rgbaCss(isText ? any.textColor : any.strokeColor) }" />
            </span>
          </template>
          <ColorPicker
            :model-value="isText ? any.textColor : any.strokeColor"
            :image-palette="palette"
            @update:model-value="emit('change', isText ? { textColor: $event } : { strokeColor: $event })"
          />
        </ToolbarPopover>
      </div>
      <label v-if="!isText" class="flex items-center gap-2 text-xs text-content-tertiary">
        Weight
        <input
          type="range" min="1" max="60" class="flex-1"
          :value="any.strokeWidth ?? 8"
          @input="emit('change', { strokeWidth: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="w-8 text-right tabular-nums">{{ Math.round(any.strokeWidth ?? 8) }}</span>
      </label>
    </section>

    <!-- Stroke style: how the line is laid down, not what colour it is. -->
    <section v-if="isPath" class="px-3 py-2 space-y-2">
      <label
        v-for="control in PATH_STYLE"
        :key="control.key"
        class="flex items-center gap-2 text-xs text-content-tertiary"
      >
        <span class="w-16 shrink-0">{{ control.label }}</span>
        <input
          type="range"
          class="flex-1"
          :min="control.min" :max="control.max" :step="control.step"
          :value="numberOr(control.key, control.fallback)"
          @input="emit('change', { [control.key]: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="w-8 text-right tabular-nums">{{ numberOr(control.key, control.fallback) }}</span>
      </label>
    </section>

    <section v-if="isLine" class="px-3 py-2 space-y-2">
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        <span class="w-16 shrink-0">Start</span>
        <select
          class="flex-1 px-2 py-1 text-xs rounded-md bg-surface-raised text-content focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :value="any.lineStart ?? 'none'"
          @change="emit('change', { lineStart: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="end in LINE_ENDS" :key="end.id" :value="end.id">{{ end.label }}</option>
        </select>
      </label>
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        <span class="w-16 shrink-0">End</span>
        <select
          class="flex-1 px-2 py-1 text-xs rounded-md bg-surface-raised text-content focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          :value="any.lineEnd ?? 'none'"
          @change="emit('change', { lineEnd: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="end in LINE_ENDS" :key="end.id" :value="end.id">{{ end.label }}</option>
        </select>
      </label>
    </section>

    <section v-if="isRect" class="px-3 py-2">
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        <span class="w-16 shrink-0">Corners</span>
        <input
          type="range" min="0" max="80" step="1" class="flex-1"
          :value="numberOr('cornerRadius', 0)"
          @input="emit('change', { cornerRadius: Number(($event.target as HTMLInputElement).value) })"
        />
        <span class="w-8 text-right tabular-nums">{{ numberOr('cornerRadius', 0) }}</span>
      </label>
    </section>

    <section v-if="hasFill || isText" class="px-3 py-2 space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-[11px] text-content-tertiary flex-1">{{ isText ? 'Background' : 'Fill' }}</span>
        <ToolbarPopover label="" :width="292">
          <template #trigger>
            <span class="colour-well">
              <span :style="{ background: rgbaCss(any.backgroundColor) }" />
            </span>
          </template>
          <ColorPicker
            :model-value="any.backgroundColor ?? null"
            :image-palette="palette"
            allow-null
            @update:model-value="emit('change', { backgroundColor: $event })"
          />
        </ToolbarPopover>
      </div>
    </section>

    <section class="px-3 py-2 space-y-2">
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        <input type="checkbox" :checked="glowOn" @change="setGlow(($event.target as HTMLInputElement).checked)" />
        Neon
      </label>
      <label v-if="glowOn" class="flex items-center gap-2 text-xs text-content-tertiary">
        Glow
        <input
          type="range" min="0" max="100" class="flex-1"
          :value="glowIntensity"
          @input="setGlowIntensity(Number(($event.target as HTMLInputElement).value))"
        />
        <span class="w-8 text-right tabular-nums">{{ glowIntensity }}</span>
      </label>
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        Opacity
        <input
          type="range" min="0" max="1" step="0.05" class="flex-1"
          :value="shape.opacity ?? 1"
          @input="emit('change', { opacity: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
    </section>
  </div>
</template>

<style scoped>
/*
 * A colour well, not a dot. Wide enough to read the colour at a glance and
 * backed by a checkerboard so "no fill" is visibly no fill rather than
 * whatever the panel behind it happens to be.
 */
.colour-well {
  width: 34px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid rgb(var(--color-text-primary-rgb) / 0.18);
  overflow: hidden;
  display: block;
  background-image:
    linear-gradient(45deg, rgb(var(--color-text-primary-rgb) / 0.14) 25%, transparent 25%),
    linear-gradient(-45deg, rgb(var(--color-text-primary-rgb) / 0.14) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, rgb(var(--color-text-primary-rgb) / 0.14) 75%),
    linear-gradient(-45deg, transparent 75%, rgb(var(--color-text-primary-rgb) / 0.14) 75%);
  background-size: 8px 8px;
  background-position: 0 0, 0 4px, 4px -4px, -4px 0;
}

.colour-well > span {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
