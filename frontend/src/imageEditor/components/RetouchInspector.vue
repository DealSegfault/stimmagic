<script setup lang="ts">
/**
 * Properties for one selected Retouch child.
 *
 * These controls alter how the selected child's retained repair is composited.
 * They belong to the region, never the parent Retouch row.
 */
import { computed, onBeforeUnmount } from 'vue'
import type { GradientMask, MaskComponent, RetouchRegion, RetouchRegionSettings } from '../stack/types'
import { adjustControl, lookById, photoAdjustmentGroup } from '../stack/adjustSections'
import { gradientSliderOf, isGradientMask, withGradientSlider } from '../stack/regionMask'
import { maskComponentLabel, regionMaskComponents } from '../stack/maskComponents'
import type { ToneCurveHistogram } from '../stack/toneCurve'
import LookControls from './LookControls.vue'
import PhotoAdjustmentControls from './PhotoAdjustmentControls.vue'
import ScrubValue from '../../components/ui/ScrubValue.vue'
import { MAX_FEATHER_PX } from '../stack/featherScale'

const props = defineProps<{
  region: RetouchRegion
  /** Selected mask component inside this region, when one is. */
  selectedComponentId?: string | null
  /** A semantic component being re-segmented right now. */
  recomputingComponentId?: string | null
  histogram?: ToneCurveHistogram
  /** Point color only: the canvas eyedropper is currently armed. */
  picking?: boolean
  clipShadows?: boolean
  clipHighlights?: boolean
}>()

const emit = defineEmits<{
  settings: [Partial<RetouchRegionSettings>, string]
  settingsCommit: []
  /** Point color asks the host view to arm the canvas eyedropper. */
  pick: []
  clip: [{ shadows: boolean; highlights: boolean }]
  /** New geometry for this region's gradient mask. */
  gradient: [GradientMask]
  gradientCommit: []
  /** The gradient falloff slider started or ended a gesture. */
  gradientAdjusting: [boolean]
  /** Route the next selection gestures into this region's mask. */
  editMask: []
  /** The next gesture replaces the base component, keeping the modifiers. */
  replaceBase: []
  /** Re-segment a semantic base against the current pixels below the step. */
  recomputeBase: [string]
  /** Convert this scoped step to a whole-image one, keeping its values. */
  unscope: []
}>()

/** The mask components view of this region — legacy single masks included. */
const components = computed<MaskComponent[]>(() => regionMaskComponents(props.region))
const selectedComponent = computed<MaskComponent | null>(() => {
  const id = props.selectedComponentId
  if (!id) return null
  return components.value.find(component => component.id === id) ?? null
})
const selectedComponentIsBase = computed(() =>
  !!selectedComponent.value && components.value[0]?.id === selectedComponent.value.id
)
/** The base offers Recompute only when it knows what it was a selection OF. */
const baseSemantic = computed(() => {
  const base = components.value[0]
  return base?.semantic?.prompt
    || base?.semantic?.intent
    ? base
    : null
})

/**
 * A gradient's shape is editable HERE as well as on the canvas: the handles
 * set where the ramp runs, and this sets how abruptly it gets there. Drawn
 * masks have no equivalent — their shape is the pixels they were painted
 * with — so the section only exists for gradients: the legacy single-gradient
 * region, or the selected gradient component of a composite mask.
 */
const gradient = computed<GradientMask | null>(() => {
  if (props.region.mask_components?.length) {
    const mask = selectedComponent.value?.mask
    return isGradientMask(mask) ? mask : null
  }
  return isGradientMask(props.region.mask) ? props.region.mask : null
})
const gradientSlider = computed(
  () => gradient.value ? gradientSliderOf(gradient.value) : null
)
const gradientLabel = computed(() =>
  gradient.value?.kind === 'linear' ? 'Linear gradient' : 'Radial gradient'
)

function setGradientSlider(value: number) {
  if (!gradient.value) return
  emit('gradientAdjusting', true)
  emit('gradient', withGradientSlider(gradient.value, Math.round(value)))
}

function finishGradientSlider() {
  emit('gradientCommit')
  emit('gradientAdjusting', false)
}

onBeforeUnmount(() => emit('gradientAdjusting', false))

function setGradientInvert(invert: boolean) {
  const mask = gradient.value
  if (mask?.kind !== 'radial') return
  emit('gradient', { ...mask, invert })
  emit('gradientCommit')
}

function setFeather(region: RetouchRegion, pixels: number) {
  emit('settings', {
    feather_px: Math.max(0, Math.min(MAX_FEATHER_PX, Math.round(pixels))),
  }, `retouch-feather:${region.id}`)
}

/** A Looks tile scoped to a selection: many groups in one region. */
const look = computed(() =>
  props.region.kind === 'look'
    ? lookById(props.region.settings?.look ?? '') ?? null
    : null
)

const isAdjustment = computed(() =>
  props.region.kind === 'adjust'
  || props.region.kind === 'look'
  || !!photoAdjustmentGroup(props.region.kind)
)
const adjustmentGroup = computed(() =>
  photoAdjustmentGroup(props.region.kind === 'adjust' ? 'light' : props.region.kind)
)
/**
 * Blur renders through the photographic pipeline but is not a Detail-group
 * slider; a Blur-brush region still needs its amount adjustable here.
 */
const adjustmentControls = computed(() => {
  const group = adjustmentGroup.value
  if (!group) return []
  if (props.region.kind !== 'detail') return group.controls
  const blur = adjustControl('blur')
  return blur ? [...group.controls, blur] : group.controls
})

function setPhotoValue(patch: Record<string, any>, coalesceKey: string) {
  emit('settings', patch, coalesceKey)
}

</script>

<template>
  <div class="p-3">
    <!-- A scoped Looks tile: the groups it moved, same surface as the
         whole-image version — the mask is the only difference. -->
    <section v-if="region.kind === 'look'" class="space-y-3">
      <h3 class="text-xs font-semibold text-content-secondary">
        {{ look?.label ?? 'Look' }}
      </h3>
      <LookControls
        :values="region.settings"
        :label="look?.label"
        :histogram="histogram"
        :picking="picking"
        :clip-shadows="clipShadows"
        :clip-highlights="clipHighlights"
        :coalesce-prefix="`retouch:${region.id}`"
        @change="setPhotoValue"
        @commit="emit('settingsCommit')"
        @pick="emit('pick')"
        @clip="emit('clip', $event)"
      />
    </section>

    <section v-if="isAdjustment && adjustmentGroup" class="space-y-3">
      <h3 class="text-xs font-semibold text-content-secondary">
        {{ adjustmentGroup.label }}
      </h3>
      <PhotoAdjustmentControls
        :controls="adjustmentControls"
        :values="region.settings"
        :histogram="histogram"
        :presentation="adjustmentGroup.presentation"
        :picking="picking"
        :clip-shadows="clipShadows"
        :clip-highlights="clipHighlights"
        :coalesce-prefix="`retouch:${region.id}`"
        @change="setPhotoValue"
        @commit="emit('settingsCommit')"
        @pick="emit('pick')"
        @clip="emit('clip', $event)"
      />
    </section>

    <!-- Mask: an adjustment region is a scoped Adjust step with ONE effective
         mask. It can be refined with the selection tools (each gesture lands
         as an editable component), or dropped to cover the whole image (the
         values survive; the mask and its blend dials do not). -->
    <section v-if="isAdjustment" class="mt-5 space-y-1.5">
      <h3 class="text-xs font-semibold text-content-secondary">Mask</h3>
      <div class="flex items-center gap-2">
        <span class="min-w-0 flex-1 text-xs text-content-tertiary">Selection</span>
        <button
          type="button"
          class="shrink-0 whitespace-nowrap px-2 py-1.5 text-xs rounded-md border border-edge-subtle
                 text-content-secondary hover:text-content hover:bg-overlay-subtle"
          aria-label="Edit selection mask"
          title="Edit the mask — each gesture lands as a component, using the combine mode"
          @click="emit('editMask')"
        >
          Edit
        </button>
        <button
          type="button"
          class="shrink-0 whitespace-nowrap px-2 py-1.5 text-xs rounded-md border border-edge-subtle
                 text-content-secondary hover:text-content hover:bg-overlay-subtle"
          aria-label="Apply adjustment to whole image"
          title="Apply adjustment to whole image"
          @click="emit('unscope')"
        >
          Whole image
        </button>
      </div>
      <!-- The base component's verbs: swap its coverage for a new gesture, or
           re-segment what it names against the current picture. -->
      <div
        v-if="selectedComponentIsBase || baseSemantic"
        class="flex items-center gap-2"
      >
        <span class="min-w-0 flex-1 text-xs text-content-tertiary truncate">
          {{ maskComponentLabel(components[0]) }}
        </span>
        <button
          type="button"
          class="shrink-0 whitespace-nowrap px-2 py-1.5 text-xs rounded-md border border-edge-subtle
                 text-content-secondary hover:text-content hover:bg-overlay-subtle"
          aria-label="Replace the base component"
          title="Replace the base — the next gesture becomes the new base, modifiers stay"
          @click="emit('replaceBase')"
        >
          Replace
        </button>
        <button
          v-if="baseSemantic"
          type="button"
          class="shrink-0 whitespace-nowrap px-2 py-1.5 text-xs rounded-md border border-edge-subtle
                 text-content-secondary hover:text-content hover:bg-overlay-subtle
                 disabled:opacity-50"
          :disabled="recomputingComponentId === baseSemantic.id"
          aria-label="Recompute the base selection"
          title="Re-segment this selection against the current picture"
          @click="emit('recomputeBase', baseSemantic.id)"
        >
          {{ recomputingComponentId === baseSemantic.id ? 'Recomputing…' : 'Recompute' }}
        </button>
      </div>
    </section>

    <!-- Mask: only gradients have a shape that outlives the gesture. -->
    <section v-if="gradient && gradientSlider" class="space-y-3" :class="isAdjustment && 'mt-5'">
      <h3 class="text-xs font-semibold text-content-secondary">Mask</h3>
      <p class="text-xs text-content-tertiary">
        {{ gradientLabel }} — drag its handles on the canvas to re-aim it.
      </p>
      <label class="grid grid-cols-[64px_1fr_38px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">{{ gradientSlider.label }}</span>
        <input
          type="range"
          :min="gradient.kind === 'radial' ? 2 : 0"
          max="100"
          step="1"
          :value="gradientSlider.value"
          @pointerdown="emit('gradientAdjusting', true)"
          @input="setGradientSlider(Number(($event.target as HTMLInputElement).value))"
          @change="finishGradientSlider"
          @pointerup="emit('gradientAdjusting', false)"
          @pointercancel="emit('gradientAdjusting', false)"
          @blur="emit('gradientAdjusting', false)"
        />
        <span class="font-mono tabular-nums text-right text-content-secondary">
          {{ Math.round(gradientSlider.value) }}
        </span>
      </label>
      <label
        v-if="gradient.kind === 'radial'"
        class="flex items-center gap-2 text-xs text-content-tertiary"
      >
        <input
          type="checkbox"
          class="accent-accent"
          :checked="gradient.invert"
          @change="setGradientInvert(($event.target as HTMLInputElement).checked)"
        >
        Affect outside the ellipse
      </label>
    </section>

    <section class="space-y-3" :class="(isAdjustment || gradient) && 'mt-5'">
      <h3 class="text-xs font-semibold text-content-secondary">Blend</h3>
      <label class="flex items-center justify-between gap-3 text-xs">
        <span class="text-content-tertiary">Opacity</span>
        <span class="min-w-12 text-right">
          <ScrubValue
            :model-value="Math.round(region.settings.opacity * 100)"
            :min="0"
            :max="100"
            :step="1"
            :non-default="region.settings.opacity !== 1"
            :format="value => `${value}%`"
            title="Drag to adjust opacity · click for slider"
            @update:model-value="emit('settings', {
              opacity: $event / 100,
            }, `retouch-opacity:${region.id}`)"
            @commit="emit('settingsCommit')"
          />
        </span>
      </label>
      <label class="flex items-center justify-between gap-3 text-xs">
        <span class="text-content-tertiary">Feather</span>
        <span class="min-w-12 text-right">
          <ScrubValue
            :model-value="Math.round(region.settings.feather_px)"
            :min="0"
            :max="MAX_FEATHER_PX"
            :step="1"
            :non-default="region.settings.feather_px !== 0"
            :format="value => `${value}px`"
            title="Drag to adjust feather · click for slider"
            @update:model-value="setFeather(region, $event)"
            @commit="emit('settingsCommit')"
          />
        </span>
      </label>
    </section>
  </div>
</template>
