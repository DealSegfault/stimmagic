<script setup lang="ts">
import { TrashIcon } from '@heroicons/vue/24/outline'
import IconButton from '../ui/IconButton.vue'
import H3ExampleChip from './H3ExampleChip.vue'
import type { H3ExampleReference } from '../../utils/h3Examples'

defineProps<{ references: H3ExampleReference[] }>()
const emit = defineEmits<{ remove: [id: string]; open: [id: string] }>()
</script>

<template>
  <div v-if="references.length" class="flex flex-wrap items-center gap-2 px-3 pt-2" aria-label="Styles sélectionnés">
    <div v-for="reference in references" :key="reference.id" class="flex min-w-0 max-w-full items-center rounded-md bg-accent-selection/15">
      <H3ExampleChip :id="reference.id" :label="reference.label" @open="emit('open', $event)" />
      <IconButton :aria-label="`Retirer le style ${reference.label}`" @click="emit('remove', reference.id)"><TrashIcon class="h-3.5 w-3.5" /></IconButton>
    </div>
  </div>
</template>
