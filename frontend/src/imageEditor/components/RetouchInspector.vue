<script setup lang="ts">
/**
 * Properties for one selected Retouch child.
 *
 * These controls alter how the selected child's retained repair is composited.
 * They belong to the region, never the parent Retouch row.
 */
import { computed } from 'vue'
import type { GradientMask, RetouchRegion, RetouchRegionSettings } from '../stack/types'
import { photoAdjustmentGroup } from '../stack/adjustSections'
import { gradientSliderOf, isGradientMask, withGradientSlider } from '../stack/regionMask'
import type { ToneCurveHistogram } from '../stack/toneCurve'
import PhotoAdjustmentControls from './PhotoAdjustmentControls.vue'
import {
  FEATHER_SLIDER_MAX,
  MAX_FEATHER_PX,
  featherPxFromSlider,
  featherSliderFromPx,
} from '../stack/featherScale'

const props = defineProps<{
  region: RetouchRegion
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
}>()

/**
 * A gradient region's shape is editable HERE as well as on the canvas: the
 * handles set where the ramp runs, and this sets how abruptly it gets there.
 * Drawn regions have no equivalent — their shape is the pixels they were
 * painted with — so the section only exists for gradients.
 */
const gradient = computed<GradientMask | null>(
  () => isGradientMask(props.region.mask) ? props.region.mask : null
)
const gradientSlider = computed(
  () => gradient.value ? gradientSliderOf(gradient.value) : null
)
const gradientLabel = computed(() =>
  gradient.value?.kind === 'linear' ? 'Linear gradient' : 'Radial gradient'
)

function setGradientSlider(value: number) {
  if (!gradient.value) return
  emit('gradient', withGradientSlider(gradient.value, Math.round(value)))
}

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

const isAdjustment = computed(() =>
  props.region.kind === 'adjust'
  || !!photoAdjustmentGroup(props.region.kind)
)
const adjustmentGroup = computed(() =>
  photoAdjustmentGroup(props.region.kind === 'adjust' ? 'light' : props.region.kind)
)

function setPhotoValue(patch: Record<string, any>, coalesceKey: string) {
  emit('settings', patch, coalesceKey)
}

</script>

<template>
  <div class="p-3">
    <section v-if="isAdjustment && adjustmentGroup" class="space-y-3">
      <h3 class="text-xs font-semibold text-content-secondary">
        {{ adjustmentGroup.label }}
      </h3>
      <PhotoAdjustmentControls
        :controls="adjustmentGroup.controls"
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
          @input="setGradientSlider(Number(($event.target as HTMLInputElement).value))"
          @change="emit('gradientCommit')"
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
      <label class="grid grid-cols-[64px_1fr_38px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Opacity</span>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          :value="Math.round(region.settings.opacity * 100)"
          @input="emit('settings', {
            opacity: Number(($event.target as HTMLInputElement).value) / 100,
          }, `retouch-opacity:${region.id}`)"
          @change="emit('settingsCommit')"
        />
        <span class="font-mono tabular-nums text-right text-content-secondary">
          {{ Math.round(region.settings.opacity * 100) }}%
        </span>
      </label>
      <label class="grid grid-cols-[64px_1fr_58px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Feather</span>
        <input
          type="range"
          min="0"
          :max="FEATHER_SLIDER_MAX"
          step="1"
          :value="featherSliderFromPx(region.settings.feather_px)"
          @input="setFeather(
            region,
            featherPxFromSlider(Number(($event.target as HTMLInputElement).value)),
          )"
          @change="emit('settingsCommit')"
        />
        <input
          type="number"
          min="0"
          :max="MAX_FEATHER_PX"
          step="1"
          :value="Math.round(region.settings.feather_px)"
          aria-label="Feather in image pixels"
          class="w-full rounded-control border border-edge-subtle bg-surface-raised px-1.5 py-1
                 text-right font-mono tabular-nums text-content-secondary
                 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
          @change="setFeather(
            region,
            Number(($event.target as HTMLInputElement).value),
          ); emit('settingsCommit')"
        />
      </label>
    </section>
  </div>
</template>
