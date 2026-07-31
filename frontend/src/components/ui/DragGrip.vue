<script setup lang="ts">
// Atelier DragGrip — the one drag-handle mark: a 2×3 grid of dots.
// Dots read as "pick this up" the way bars do not; bars are also the resize
// affordance elsewhere in the app, and one mark should mean one thing.
</script>

<template>
  <svg viewBox="0 0 10 16" fill="currentColor" aria-hidden="true">
    <circle cx="3" cy="4" r="1.1" />
    <circle cx="7" cy="4" r="1.1" />
    <circle cx="3" cy="8" r="1.1" />
    <circle cx="7" cy="8" r="1.1" />
    <circle cx="3" cy="12" r="1.1" />
    <circle cx="7" cy="12" r="1.1" />
  </svg>
</template>
