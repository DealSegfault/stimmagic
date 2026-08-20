<script setup>
import { computed } from 'vue'

const props = defineProps({
  blocking: { type: Object, required: true },
  frame: { type: Object, required: true },
  previousBlocking: { type: Object, default: null },
})

const previousActors = computed(() => {
  const frames = props.previousBlocking?.frames || []
  return frames.length ? (frames[frames.length - 1].actors || []) : []
})

const raccords = computed(() => (props.frame.actors || []).flatMap((actor) => {
  const previous = previousActors.value.find((item) => item.id === actor.id)
  if (!previous) return []
  const distance = Math.hypot(actor.x - previous.x, actor.y - previous.y) / 82
  return [{ id: actor.id, previous, current: actor, distance: distance.toFixed(1) }]
}))

function cameraTransform(camera) {
  return `translate(${camera.x} ${camera.y}) rotate(${camera.facing})`
}

function midpoint(first, second) {
  return { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 }
}
</script>

<template>
  <figure class="min-w-0">
    <div class="overflow-hidden rounded-media bg-matte">
      <svg
        viewBox="0 0 900 600"
        class="block aspect-[3/2] w-full"
        role="img"
        :aria-label="`Blocking zénithal — ${blocking.location.label}, seconde ${frame.index + 1}`"
      >
        <defs>
          <marker id="blocking-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" class="fill-content-tertiary" />
          </marker>
          <marker id="blocking-gaze-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" class="fill-accent" />
          </marker>
        </defs>

        <rect x="24" y="24" width="852" height="552" rx="8" class="fill-base stroke-edge" stroke-width="2" />

        <g v-for="space in blocking.spaces" :key="space.id">
          <rect
            :x="space.x"
            :y="space.y"
            :width="space.width"
            :height="space.height"
            rx="5"
            class="fill-surface stroke-edge-subtle"
            stroke-width="1.5"
          />
          <text :x="space.x + 12" :y="space.y + 20" class="fill-content-muted text-[11px] font-medium">{{ space.label }}</text>
        </g>

        <g aria-label="Repères fixes" class="fill-none stroke-edge-strong" stroke-width="2">
          <path d="M 83 88 H 300 V 132 H 83 Z" />
          <ellipse cx="535" cy="265" rx="54" ry="32" />
          <path d="M 392 63 H 610 M 420 71 V 87 M 480 71 V 87 M 540 71 V 87 M 600 71 V 87" />
          <path d="M 730 285 V 375 M 760 285 V 375" stroke-dasharray="5 5" />
          <path d="M 650 420 H 720 M 650 475 H 720" />
        </g>

        <g aria-label="Raccord avec le plan précédent">
          <g v-for="actor in previousActors" :key="`previous-${actor.id}`" opacity="0.46">
            <circle :cx="actor.x" :cy="actor.y" r="15" class="fill-none stroke-selection" stroke-width="2" stroke-dasharray="4 4" />
          </g>
          <g v-for="raccord in raccords" :key="`raccord-${raccord.id}`">
            <line
              :x1="raccord.previous.x"
              :y1="raccord.previous.y"
              :x2="raccord.current.x"
              :y2="raccord.current.y"
              class="stroke-selection"
              stroke-width="1.5"
              stroke-dasharray="7 6"
              marker-end="url(#blocking-arrow)"
            />
            <g :transform="`translate(${midpoint(raccord.previous, raccord.current).x} ${midpoint(raccord.previous, raccord.current).y})`">
              <rect x="-24" y="-11" width="48" height="19" rx="5" class="fill-base stroke-edge-subtle" />
              <text y="3" text-anchor="middle" class="fill-content-secondary text-[10px] font-mono">{{ raccord.distance }} m</text>
            </g>
          </g>
        </g>

        <g v-for="prop in blocking.props" :key="prop.id" :transform="`translate(${prop.x} ${prop.y})`">
          <rect x="-16" y="-12" width="32" height="24" rx="4" class="fill-surface-raised stroke-content-muted" stroke-width="1.5" />
          <text y="4" text-anchor="middle" class="fill-content-secondary text-[9px] font-mono">{{ prop.symbol }}</text>
          <text y="29" text-anchor="middle" class="fill-content-muted text-[9px]">{{ prop.label }}</text>
        </g>

        <g v-for="actor in frame.actors" :key="actor.id">
          <line
            :x1="actor.x"
            :y1="actor.y"
            :x2="actor.gaze_x"
            :y2="actor.gaze_y"
            class="stroke-accent"
            stroke-width="1.5"
            stroke-dasharray="4 4"
            marker-end="url(#blocking-gaze-arrow)"
          />
          <circle :cx="actor.x" :cy="actor.y" r="21" class="fill-base stroke-base" stroke-width="6" />
          <circle
            :cx="actor.x"
            :cy="actor.y"
            r="18"
            :class="actor.id === 'maya_ext' ? 'fill-selection' : 'fill-accent'"
          />
          <text :x="actor.x" :y="actor.y + 4" text-anchor="middle" class="fill-white text-[11px] font-semibold">{{ actor.initials }}</text>
          <text :x="actor.x" :y="actor.y + 37" text-anchor="middle" class="fill-content-secondary text-[10px] font-medium">{{ actor.label }}</text>
        </g>

        <g :transform="cameraTransform(blocking.camera)" aria-label="Position caméra">
          <path d="M 0 0 L 95 -45 L 95 45 Z" class="fill-accent/10 stroke-accent/30" stroke-width="1" />
          <path d="M -13 -11 L 16 0 L -13 11 Z" class="fill-content stroke-base" stroke-width="3" />
          <text x="-2" y="-20" text-anchor="middle" class="fill-content-secondary text-[10px] font-mono" :transform="`rotate(${-blocking.camera.facing})`">
            CAM · {{ blocking.camera.lens }} · {{ blocking.camera.fov }}° · {{ blocking.camera.distance_meters }} m
          </text>
        </g>

        <g transform="translate(65 565)">
          <line x1="0" y1="0" x2="70" y2="0" class="stroke-content-tertiary" stroke-width="1.5" marker-end="url(#blocking-arrow)" />
          <text x="80" y="4" class="fill-content-muted text-[10px]">Axe principal · Ouest → Est</text>
        </g>
        <g transform="translate(835 62)">
          <line x1="0" y1="26" x2="0" y2="0" class="stroke-content-tertiary" stroke-width="1.5" marker-end="url(#blocking-arrow)" />
          <text x="0" y="42" text-anchor="middle" class="fill-content-muted text-[10px] font-mono">N</text>
        </g>
      </svg>
    </div>

    <figcaption class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-content-muted">
      <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-accent" />Maya</span>
      <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-selection" />Maya extérieure</span>
      <span class="inline-flex items-center gap-1.5"><span class="h-2.5 w-5 border-t border-dashed border-selection" />Position au plan précédent</span>
      <span class="font-mono">{{ blocking.location.main_view }}</span>
    </figcaption>
  </figure>
</template>
