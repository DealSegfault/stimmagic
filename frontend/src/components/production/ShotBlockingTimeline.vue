<script setup>
defineProps({
  frames: { type: Array, required: true },
  activeIndex: { type: Number, required: true },
})

defineEmits(['select'])

function timeLabel(frame) {
  return `${frame.time_start.toFixed(1)}–${frame.time_end.toFixed(1)} s`
}
</script>

<template>
  <section aria-labelledby="blocking-timeline-title" class="min-w-0">
    <div class="mb-3 flex items-center justify-between">
      <div>
        <h3 id="blocking-timeline-title" class="text-xs font-semibold text-content-secondary">Blocking seconde par seconde</h3>
        <p class="mt-1 text-[11px] text-content-muted">Sélectionne une seconde pour mettre à jour le schéma.</p>
      </div>
      <span class="font-mono text-[11px] text-content-muted">{{ frames.length }} état(s)</span>
    </div>

    <div class="max-h-[510px] space-y-1 overflow-y-auto pr-1 custom-scrollbar" role="list" aria-label="Timeline de blocking">
      <button
        v-for="frame in frames"
        :key="frame.index"
        type="button"
        class="w-full rounded-md px-3 py-2.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :class="frame.index === activeIndex ? 'bg-selection/15 text-content' : 'hover:bg-overlay-subtle'"
        :aria-current="frame.index === activeIndex ? 'step' : undefined"
        @click="$emit('select', frame.index)"
      >
        <div class="flex items-baseline gap-3">
          <span class="w-[62px] shrink-0 font-mono text-[10px] tabular-nums" :class="frame.index === activeIndex ? 'text-selection' : 'text-content-muted'">{{ timeLabel(frame) }}</span>
          <span class="text-xs font-medium leading-snug text-content">{{ frame.summary }}</span>
        </div>
        <div class="ml-[74px] mt-1.5 space-y-1 text-[11px] leading-relaxed text-content-muted">
          <p>{{ frame.spatial_note }}</p>
          <p class="font-mono text-[10px] text-content-tertiary">{{ frame.camera_note }}</p>
          <p v-for="actor in frame.actors" :key="actor.id" class="text-content-secondary">
            Regard {{ actor.gaze_label }} · {{ actor.position_label }}
          </p>
        </div>
      </button>
    </div>
  </section>
</template>
