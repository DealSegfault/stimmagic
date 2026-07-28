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
      <h3 class="text-xs font-medium text-content-secondary flex-1 capitalize">
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
      <div class="flex items-center gap-1">
        <button
          v-for="weight in ['normal', 'bold']"
          :key="weight"
          type="button"
          class="px-2 py-1 text-[11px] rounded-md capitalize"
          :class="any.fontWeight === weight
            ? 'bg-selection/20 text-content'
            : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          @click="emit('change', { fontWeight: weight })"
        >
          {{ weight }}
        </button>
        <span class="w-px h-4 bg-edge-subtle mx-1" />
        <button
          v-for="align in ['left', 'center', 'right']"
          :key="align"
          type="button"
          class="px-2 py-1 text-[11px] rounded-md capitalize"
          :class="any.textAlign === align
            ? 'bg-selection/20 text-content'
            : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
          @click="emit('change', { textAlign: align })"
        >
          {{ align }}
        </button>
      </div>
    </section>

    <section v-if="hasStroke" class="px-3 py-2 space-y-2">
      <div class="text-[11px] text-content-tertiary">{{ isText ? 'Text' : 'Stroke' }}</div>
      <ColorPicker
        :model-value="isText ? any.textColor : any.strokeColor"
        :image-palette="palette"
        @update:model-value="emit('change', isText ? { textColor: $event } : { strokeColor: $event })"
      />
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
      <div class="text-[11px] text-content-tertiary">{{ isText ? 'Background' : 'Fill' }}</div>
      <ColorPicker
        :model-value="isText ? (any.backgroundColor ?? null) : (any.backgroundColor ?? null)"
        :image-palette="palette"
        allow-null
        @update:model-value="emit('change', { backgroundColor: $event })"
      />
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
