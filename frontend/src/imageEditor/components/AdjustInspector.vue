<script setup lang="ts">
/**
 * The selected adjustment row's full control surface.
 *
 * Two-zone by design: the row keeps only the eye as an immediate hand
 * affordance, and everything that needs space lives here, under the stack.
 * "Free ops have live controls" means live HERE — every slider recomposites
 * immediately and costs nothing.
 *
 * A drag is one undo step, not one per tick, which is what `coalesceKey` on the
 * document's edit recorder is for.
 */
import { computed, ref, watch } from 'vue'
import {
  ADJUST_SECTIONS, FILTER_CATEGORIES, sectionsForFamily,
} from '../stack/adjustSections'
import type { AdjustFamily } from '../stack/adjustSections'
import { applyColorMatrix } from '../ported/colorMatrix'
import { FILTER_MATRICES } from '../ported/filterMatrices'

const props = defineProps<{
  params: Record<string, any>
  /** The composite, so each preset can be previewed on the actual picture. */
  source?: HTMLCanvasElement | null
  /** The open doorway. With none, the row is selected and everything shows. */
  family?: AdjustFamily | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
}>()

// Open the group the family came in for. Defaulting to a fixed one meant
// Effects opened showing a collapsed Effects header and nothing else, which
// reads as an empty panel.
const openSection = ref<string>('levels')
watch(() => props.family, family => {
  if (family) openSection.value = sectionsForFamily(family)[0]?.id ?? openSection.value
}, { immediate: true })

function valueOf(key: string, fallback: number) {
  const value = props.params?.[key]
  return typeof value === 'number' ? value : fallback
}

function setValue(key: string, value: number) {
  emit('change', { [key]: value }, `adjust:${key}`)
}

function setToggle(key: string, value: boolean) {
  emit('change', { [key]: value }, `adjust:${key}`)
}

// With a family open the inspector shows that family's groups; selecting a row
// with no family open shows everything the step carries, which is what makes an
// earlier step fully editable from the stack.
const sections = computed(() =>
  props.family ? sectionsForFamily(props.family) : ADJUST_SECTIONS
)
const showsFilters = computed(() => !props.family || props.family === 'filters')
const activeFilter = computed(() => props.params?.filter ?? 'none')

/**
 * A thumbnail per preset, rendered off the real image.
 *
 * Naming a filter tells you nothing — 'Kodachrome' and 'Portra 400' are only
 * distinguishable by looking. Each tile is the current composite at 44px with
 * that preset's matrix applied, which is cheap because the matrix is a
 * per-pixel multiply over about two thousand pixels.
 */
const THUMB = 44
const thumbs = ref<Record<string, string>>({})

function renderThumbs() {
  const source = props.source
  if (!source || !source.width) { thumbs.value = {}; return }

  const base = document.createElement('canvas')
  base.width = THUMB
  base.height = THUMB
  const baseCtx = base.getContext('2d', { willReadFrequently: true })
  if (!baseCtx) return
  // Cover, not contain: a letterboxed tile would compare the matte, not the
  // picture.
  const side = Math.min(source.width, source.height)
  baseCtx.drawImage(
    source,
    (source.width - side) / 2, (source.height - side) / 2, side, side,
    0, 0, THUMB, THUMB
  )
  const pixels = baseCtx.getImageData(0, 0, THUMB, THUMB)

  const out: Record<string, string> = {}
  const tile = document.createElement('canvas')
  tile.width = THUMB
  tile.height = THUMB
  const tileCtx = tile.getContext('2d')!
  for (const category of FILTER_CATEGORIES) {
    for (const preset of category.filters) {
      const matrix = (FILTER_MATRICES as any)[preset.id]
      const copy = new ImageData(
        new Uint8ClampedArray(pixels.data), pixels.width, pixels.height
      )
      tileCtx.putImageData(matrix ? applyColorMatrix(copy, matrix) : copy, 0, 0)
      out[preset.id] = tile.toDataURL()
    }
  }
  thumbs.value = out
}

watch(() => [props.source, showsFilters.value], () => {
  if (showsFilters.value) renderThumbs()
}, { immediate: true })

function chooseFilter(id: string) {
  emit('change', { filter: id === 'none' ? null : id }, 'adjust:filter')
  emit('commit')
}
</script>

<template>
  <div class="divide-y divide-edge-subtle">

    <!-- A chosen filter's only property: how much of it. -->
    <section v-if="params?.filter && (!family || family === 'filters')" class="px-3 py-2">
      <label class="flex items-center gap-2 text-xs text-content-tertiary">
        <span class="w-16 shrink-0">Amount</span>
        <input
          type="range" min="0" max="100" step="1" class="flex-1"
          :disabled="disabled"
          :value="params.filterAmount ?? 100"
          @input="emit('change', { filterAmount: Number(($event.target as HTMLInputElement).value) }, 'adjust:filterAmount')"
          @change="emit('commit')"
        />
        <span class="w-8 text-right tabular-nums">{{ params.filterAmount ?? 100 }}</span>
      </label>
    </section>
    <section v-for="section in sections" :key="section.id">
      <button
        type="button"
        class="w-full flex items-center gap-2 px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 ring-accent/60 rounded-md"
        @click="openSection = openSection === section.id ? '' : section.id"
      >
        <span class="text-xs font-medium text-content-secondary flex-1">{{ section.label }}</span>
        <span
          v-if="section.toggle"
          class="text-[11px] px-1.5 py-0.5 rounded-md"
          :class="params?.[section.toggle.key]
            ? 'bg-selection/20 text-content'
            : 'bg-overlay-subtle text-content-tertiary'"
          @click.stop="setToggle(section.toggle.key, !params?.[section.toggle.key])"
        >
          {{ section.toggle.label }}
        </span>
      </button>

      <div v-if="openSection === section.id" class="px-3 pb-3 space-y-2">
        <label
          v-for="control in section.controls"
          :key="control.key"
          class="flex items-center gap-2"
        >
          <span class="w-28 shrink-0 text-xs text-content-tertiary">{{ control.label }}</span>
          <input
            type="range"
            class="flex-1"
            :min="control.min"
            :max="control.max"
            :step="control.step"
            :disabled="disabled"
            :value="valueOf(control.key, control.default)"
            @input="setValue(control.key, Number(($event.target as HTMLInputElement).value))"
            @change="emit('commit')"
          />
          <span class="w-10 text-right text-xs text-content-tertiary tabular-nums">
            {{ valueOf(control.key, control.default) }}
          </span>
        </label>
      </div>
    </section>
  </div>
</template>
