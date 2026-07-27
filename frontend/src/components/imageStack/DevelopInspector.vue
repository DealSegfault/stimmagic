<script setup lang="ts">
/**
 * The selected Develop row's full control surface.
 *
 * Two-zone by design: the row keeps only the eye as an immediate hand
 * affordance, and everything that needs space lives here, under the stack.
 * "Free ops have live controls" means live HERE — every slider recomposites
 * immediately and costs nothing.
 *
 * A drag is one undo step, not one per tick, which is what `coalesceKey` on the
 * document's edit recorder is for.
 */
import { computed, ref } from 'vue'
import { DEVELOP_SECTIONS } from '../../composables/imageStack/developSections'

const props = defineProps<{
  params: Record<string, any>
  disabled?: boolean
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
}>()

const openSection = ref<string>('light')

function valueOf(key: string, fallback: number) {
  const value = props.params?.[key]
  return typeof value === 'number' ? value : fallback
}

function setValue(key: string, value: number) {
  emit('change', { [key]: value }, `develop:${key}`)
}

function setToggle(key: string, value: boolean) {
  emit('change', { [key]: value }, `develop:${key}`)
}

const sections = computed(() => DEVELOP_SECTIONS)
</script>

<template>
  <div class="divide-y divide-edge-subtle">
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
