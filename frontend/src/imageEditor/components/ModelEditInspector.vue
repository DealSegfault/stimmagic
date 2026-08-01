<script setup lang="ts">
/**
 * Properties for one model-backed Remove or Repaint patch.
 *
 * Prompt is the normal Repaint surface. Provider controls and patch blending
 * are shown directly: Properties is already the disclosure boundary, so a
 * second Advanced disclosure only makes the controls harder to reach.
 */
import { computed } from 'vue'
import Button from '../../components/ui/Button.vue'
import ReferenceImageStrip from './ReferenceImageStrip.vue'
import ToolAdvancedParams from './ToolAdvancedParams.vue'
import type { GenerativeOp, ModelReferenceImage, OpBlend } from '../stack/types'
import {
  modelReferenceLimits,
  sanitizeModelToolParams,
} from '../stack/modelToolParams'
import {
  FEATHER_SLIDER_MAX,
  MAX_FEATHER_PX,
  featherPxFromSlider,
  featherSliderFromPx,
} from '../stack/featherScale'

const props = defineProps<{
  op: GenerativeOp
  tool: any | null
  running?: boolean
}>()

const emit = defineEmits<{
  params: [Record<string, any>]
  references: [ModelReferenceImage[]]
  blend: [Partial<OpBlend>]
  blendCommit: []
  run: []
}>()

const isRepaint = computed(() =>
  props.op.operation === 'repaint'
  || (!props.op.operation && props.op.label === 'Repaint')
)
const blend = computed(() => ({
  feather_px: props.op.blend?.feather_px ?? 6,
  opacity: props.op.blend?.opacity ?? 1,
}))
const toolParams = computed(() =>
  sanitizeModelToolParams(props.tool, props.op.params)
)
// Only Regenerate: outpaint-image tools take the original and the four
// percents, nothing else — the old inpaint-backed Expand's references are gone
// with it.
const supportsReferences = computed(() => props.op.operation === 'repaint')
const referenceLimits = computed(() => modelReferenceLimits(props.tool))
const referencesValid = computed(() => {
  const count = props.op.reference_images?.length ?? 0
  return count >= referenceLimits.value.min && count <= referenceLimits.value.max
})

</script>

<template>
  <div class="p-3 space-y-5">
    <section v-if="isRepaint" class="space-y-2">
      <h3 class="text-xs font-semibold text-content-secondary">Prompt</h3>
      <textarea
        :value="op.params.prompt ?? ''"
        rows="3"
        placeholder="Describe what should replace the selected area"
        class="w-full resize-y rounded-md border border-transparent bg-overlay-subtle
               px-3 py-2 text-sm text-content outline-none placeholder:text-content-muted
               focus:border-accent focus-visible:ring-2 ring-accent/40"
        @input="emit('params', {
          prompt: ($event.target as HTMLTextAreaElement).value,
        })"
      />
    </section>

    <section
      v-if="supportsReferences && (referenceLimits.max > 0 || op.reference_images?.length)"
    >
      <ReferenceImageStrip
        :model-value="op.reference_images || []"
        :min-items="referenceLimits.min"
        :max-items="referenceLimits.max"
        :disabled="running"
        @update:model-value="emit('references', $event)"
      />
    </section>

    <section class="space-y-2">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <h3 class="text-xs font-semibold text-content-secondary">
            {{ tool?.name || 'Tool unavailable' }}
          </h3>
          <p class="text-xs text-content-tertiary">
            Parameter changes apply the next time this edit runs.
          </p>
        </div>
        <Button
          class="shrink-0 whitespace-nowrap"
          size="sm"
          :loading="running"
          :disabled="!tool || !referencesValid"
          @click="emit('run')"
        >
          Run again
        </Button>
      </div>
    </section>

    <ToolAdvancedParams
      v-if="tool"
      :tool="tool"
      :values="toolParams"
      @update="(name, value) => emit('params', { [name]: value })"
    />

    <section class="space-y-3">
      <h3 class="text-xs font-semibold text-content-secondary">Blend</h3>
      <label class="grid grid-cols-[64px_1fr_38px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Opacity</span>
        <input
          type="range"
          min="0"
          max="100"
          step="1"
          :value="Math.round(blend.opacity * 100)"
          @input="emit('blend', {
            opacity: Number(($event.target as HTMLInputElement).value) / 100,
          })"
          @change="emit('blendCommit')"
        />
        <span class="text-right font-mono tabular-nums text-content-secondary">
          {{ Math.round(blend.opacity * 100) }}%
        </span>
      </label>
      <label class="grid grid-cols-[64px_1fr_58px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Feather</span>
        <input
          type="range"
          min="0"
          :max="FEATHER_SLIDER_MAX"
          step="1"
          :value="featherSliderFromPx(blend.feather_px)"
          @input="emit('blend', {
            feather_px: featherPxFromSlider(
              Number(($event.target as HTMLInputElement).value),
            ),
          })"
          @change="emit('blendCommit')"
        />
        <input
          type="number"
          min="0"
          :max="MAX_FEATHER_PX"
          step="1"
          :value="Math.round(blend.feather_px)"
          aria-label="Feather in image pixels"
          class="w-full rounded-md border border-transparent bg-overlay-subtle px-1.5 py-1
                 text-right font-mono tabular-nums text-content-secondary outline-none
                 focus:border-accent focus-visible:ring-2 ring-accent/40"
          @change="emit('blend', {
            feather_px: Math.max(
              0,
              Math.min(
                MAX_FEATHER_PX,
                Number(($event.target as HTMLInputElement).value),
              ),
            ),
          }); emit('blendCommit')"
        />
      </label>
    </section>
  </div>
</template>
