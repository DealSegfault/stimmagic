<script setup lang="ts">
/**
 * Three-way color grading: shadow / midtone / highlight wheels.
 *
 * Each wheel is hue (angle, red at the top, clockwise) and strength (radius),
 * with a luminance slider beneath — the layout every grading surface since
 * the telecine has taught. Blend widens the zone crossovers; Balance slides
 * them toward shadows or highlights.
 */
import { ref } from 'vue'

const props = defineProps<{
  values: Record<string, any>
  disabled?: boolean
}>()

const emit = defineEmits<{
  change: [Record<string, any>, string]
  commit: []
}>()

const WHEELS = [
  { id: 'Shadow', label: 'Shadows' },
  { id: 'Mid', label: 'Midtones' },
  { id: 'Highlight', label: 'Highlights' },
] as const

const wheelEls = ref<Record<string, HTMLDivElement | null>>({})
let draggingWheel: string | null = null

function numberOf(key: string, fallback = 0) {
  const value = props.values?.[key]
  return typeof value === 'number' ? value : fallback
}

function dotStyle(wheel: (typeof WHEELS)[number]) {
  const hue = numberOf(`grade${wheel.id}Hue`)
  const sat = numberOf(`grade${wheel.id}Sat`) / 100
  const radians = ((hue - 90) * Math.PI) / 180
  return {
    left: `${50 + Math.cos(radians) * sat * 46}%`,
    top: `${50 + Math.sin(radians) * sat * 46}%`,
  }
}

function applyPointer(wheel: (typeof WHEELS)[number], event: PointerEvent) {
  const rect = wheelEls.value[wheel.id]?.getBoundingClientRect()
  if (!rect?.width) return
  const x = (event.clientX - rect.left) / rect.width - 0.5
  const y = (event.clientY - rect.top) / rect.height - 0.5
  const radius = Math.min(1, Math.hypot(x, y) / 0.46)
  let hue = (Math.atan2(y, x) * 180) / Math.PI + 90
  hue = ((hue % 360) + 360) % 360
  emit('change', {
    [`grade${wheel.id}Hue`]: Math.round(hue),
    [`grade${wheel.id}Sat`]: Math.round(radius * 100),
  }, `grade-wheel:${wheel.id}`)
}

function startWheel(wheel: (typeof WHEELS)[number], event: PointerEvent) {
  if (props.disabled) return
  draggingWheel = wheel.id
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  applyPointer(wheel, event)
  event.preventDefault()
}

function moveWheel(wheel: (typeof WHEELS)[number], event: PointerEvent) {
  if (draggingWheel !== wheel.id) return
  applyPointer(wheel, event)
}

function endWheel(wheel: (typeof WHEELS)[number], event: PointerEvent) {
  if (draggingWheel !== wheel.id) return
  applyPointer(wheel, event)
  draggingWheel = null
  emit('commit')
}

function clearWheel(wheel: (typeof WHEELS)[number]) {
  if (props.disabled) return
  emit('change', {
    [`grade${wheel.id}Hue`]: 0,
    [`grade${wheel.id}Sat`]: 0,
    [`grade${wheel.id}Lum`]: 0,
  }, `grade-wheel:${wheel.id}`)
  emit('commit')
}

function setValue(key: string, value: number) {
  emit('change', { [key]: value }, key)
}

function reset() {
  if (props.disabled) return
  emit('change', {
    gradeShadowHue: 0, gradeShadowSat: 0, gradeShadowLum: 0,
    gradeMidHue: 0, gradeMidSat: 0, gradeMidLum: 0,
    gradeHighlightHue: 0, gradeHighlightSat: 0, gradeHighlightLum: 0,
    gradeBlend: 50, gradeBalance: 0,
  }, 'grade-reset')
  emit('commit')
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between gap-2">
      <span class="text-xs font-semibold text-content-secondary">Grading</span>
      <button
        type="button"
        class="rounded-md px-2 py-1 text-[11px] text-content-tertiary
               hover:bg-overlay-subtle hover:text-content transition-colors duration-150
               focus-visible:outline-none focus-visible:ring-2 ring-accent/60
               disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="disabled"
        @click="reset"
      >
        Reset
      </button>
    </div>

    <div class="grid grid-cols-3 gap-2.5">
      <div v-for="wheel in WHEELS" :key="wheel.id" class="space-y-1.5 text-center">
        <span class="block text-[10.5px] text-content-tertiary">{{ wheel.label }}</span>
        <div
          :ref="element => { wheelEls[wheel.id] = element as HTMLDivElement | null }"
          class="relative mx-auto w-full max-w-[86px] aspect-square rounded-full
                 border border-edge-strong cursor-crosshair touch-none select-none"
          :style="{
            background: `radial-gradient(circle,
                rgb(var(--color-surface-rgb)) 0%,
                rgb(var(--color-surface-rgb) / 0.55) 34%,
                transparent 72%),
              conic-gradient(#f00, #ff0 60deg, #0f0 120deg, #0ff 180deg,
                #00f 240deg, #f0f 300deg, #f00 360deg)`,
          }"
          role="slider"
          :aria-label="`${wheel.label} color`"
          :aria-valuenow="numberOf(`grade${wheel.id}Hue`)"
          aria-valuemin="0"
          aria-valuemax="360"
          @pointerdown="startWheel(wheel, $event)"
          @pointermove="moveWheel(wheel, $event)"
          @pointerup="endWheel(wheel, $event)"
          @pointercancel="endWheel(wheel, $event)"
          @dblclick="clearWheel(wheel)"
        >
          <span
            class="absolute w-2.5 h-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full
                   bg-white border border-black/70 shadow pointer-events-none"
            :style="dotStyle(wheel)"
          />
        </div>
        <input
          type="range"
          class="w-full max-w-[86px]"
          min="-100"
          max="100"
          step="1"
          :disabled="disabled"
          :value="numberOf(`grade${wheel.id}Lum`)"
          :aria-label="`${wheel.label} luminance`"
          :title="`${wheel.label} luminance`"
          @input="setValue(`grade${wheel.id}Lum`, Number(($event.target as HTMLInputElement).value))"
          @change="emit('commit')"
        />
      </div>
    </div>

    <div class="space-y-2">
      <label class="grid grid-cols-[74px_1fr_42px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Blend</span>
        <input
          type="range" class="min-w-0" min="0" max="100" step="1"
          :disabled="disabled"
          :value="numberOf('gradeBlend', 50)"
          @input="setValue('gradeBlend', Number(($event.target as HTMLInputElement).value))"
          @change="emit('commit')"
        />
        <span class="text-right font-mono tabular-nums text-content-secondary">
          {{ numberOf('gradeBlend', 50) }}
        </span>
      </label>
      <label class="grid grid-cols-[74px_1fr_42px] items-center gap-2 text-xs">
        <span class="text-content-tertiary">Balance</span>
        <input
          type="range" class="min-w-0" min="-100" max="100" step="1"
          :disabled="disabled"
          :value="numberOf('gradeBalance')"
          @input="setValue('gradeBalance', Number(($event.target as HTMLInputElement).value))"
          @change="emit('commit')"
        />
        <span class="text-right font-mono tabular-nums text-content-secondary">
          {{ numberOf('gradeBalance') }}
        </span>
      </label>
    </div>

    <p class="text-[11px] text-content-tertiary">
      Drag a wheel to tint its zone. Double-click a wheel to clear it.
    </p>
  </div>
</template>
