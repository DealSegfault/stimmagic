<script setup lang="ts">
import type {
  AdjustControl,
  AdjustSliderControl,
  ToneCurve,
} from '../stack/adjustSections'
import type { ToneCurveHistogram } from '../stack/toneCurve'
import { toneCurveValueOf } from '../stack/adjustSections'
import ToneCurveControl from './ToneCurveControl.vue'

const props = defineProps<{
  controls: AdjustControl[]
  values: Record<string, any>
  histogram?: ToneCurveHistogram
  disabled?: boolean
  coalescePrefix: string
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
}>()

function sliderValue(control: AdjustSliderControl) {
  const value = props.values?.[control.key]
  return typeof value === 'number' ? value : control.default
}

function curveValue(control: Extract<AdjustControl, { kind: 'curve' }>): ToneCurve {
  return toneCurveValueOf(props.values?.[control.key])
}

function setValue(key: string, value: number | ToneCurve) {
  emit('change', { [key]: value }, `${props.coalescePrefix}:${key}`)
}
</script>

<template>
  <div class="space-y-2">
    <template v-for="control in controls" :key="control.key">
      <ToneCurveControl
        v-if="control.kind === 'curve'"
        class="pt-1"
        :label="control.label"
        :value="curveValue(control)"
        :histogram="histogram"
        :disabled="disabled"
        @input="setValue(control.key, $event)"
        @commit="emit('commit')"
      />
      <label
        v-else
        class="grid grid-cols-[112px_1fr_42px] items-center gap-2 text-xs"
      >
        <span class="text-content-tertiary">{{ control.label }}</span>
        <input
          type="range"
          class="min-w-0"
          :min="control.min"
          :max="control.max"
          :step="control.step"
          :disabled="disabled"
          :value="sliderValue(control)"
          @input="setValue(
            control.key,
            Number(($event.target as HTMLInputElement).value),
          )"
          @change="emit('commit')"
        />
        <span class="text-right font-mono tabular-nums text-content-secondary">
          {{ sliderValue(control) }}
        </span>
      </label>
    </template>
  </div>
</template>
