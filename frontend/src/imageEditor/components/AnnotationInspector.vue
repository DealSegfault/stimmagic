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
      <h3 class="text-xs font-medium text-content flex-1 capitalize">
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
            <span
              class="w-4 h-4 rounded-md border border-edge-subtle"
              :style="{ background: rgbaCss(isText ? any.textColor : any.strokeColor) }"
            />
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

    <section v-if="hasFill || isText" class="px-3 py-2 space-y-2">
      <div class="flex items-center gap-2">
        <span class="text-[11px] text-content-tertiary flex-1">{{ isText ? 'Background' : 'Fill' }}</span>
        <ToolbarPopover label="" :width="292">
          <template #trigger>
            <span
              class="w-4 h-4 rounded-md border border-edge-subtle"
              :class="any.backgroundColor ? '' : 'bg-transparent'"
              :style="{ background: rgbaCss(any.backgroundColor) }"
            />
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
