<script setup lang="ts">
import ElementReferenceChip from './ElementReferenceChip.vue'
import type { ProjectElement } from '../../composables/useProjectElementsApi'

defineProps<{ elements: ProjectElement[] }>()
defineEmits<{ remove: [referenceId: string] }>()
</script>

<template>
  <div v-if="elements.length" class="flex flex-wrap gap-2 border-b border-edge-subtle px-3 py-2">
    <ElementReferenceChip
      v-for="element in elements"
      :key="element.reference_id"
      :element="element"
      removable
      @remove="$emit('remove', element.reference_id)"
    />
  </div>
</template>
