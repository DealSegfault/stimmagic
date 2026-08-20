<script setup lang="ts">
import { computed, ref } from 'vue'
import { CubeIcon, MagnifyingGlassIcon, MapPinIcon, PlusIcon } from '@heroicons/vue/24/outline'
import Button from '../ui/Button.vue'
import ReferenceStatusBadge from './ReferenceStatusBadge.vue'
import type { ReferencePack } from '../../composables/useProjectReferencesApi'

const props = defineProps<{
  packs: ReferencePack[]
  selectedId: number | null
  creating?: boolean
}>()

defineEmits<{
  select: [number]
  create: ['location' | 'prop']
}>()

const query = ref('')
const filter = ref<'all' | 'location' | 'prop'>('all')
const filtered = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase('fr')
  return props.packs.filter((pack) => {
    if (filter.value !== 'all' && pack.pack_type !== filter.value) return false
    if (!needle) return true
    return `${pack.element.name} ${pack.element.reference_id}`.toLocaleLowerCase('fr').includes(needle)
  })
})
</script>

<template>
  <aside class="flex min-h-0 flex-col rounded-lg border border-edge bg-surface" aria-label="Packs de références">
    <div class="space-y-3 border-b border-edge-subtle p-3">
      <div class="relative">
        <MagnifyingGlassIcon class="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-content-muted" />
        <input
          v-model="query"
          type="search"
          placeholder="Rechercher une référence"
          class="w-full rounded-md border border-edge bg-base py-2 pl-8 pr-3 text-xs text-content outline-none placeholder:text-content-muted focus:border-accent"
        />
      </div>
      <div class="grid grid-cols-3 gap-1 rounded-md bg-overlay-faint p-1" role="tablist" aria-label="Filtrer les références">
        <button
          v-for="choice in [{ key: 'all', label: 'Toutes' }, { key: 'location', label: 'Lieux' }, { key: 'prop', label: 'Props' }]"
          :key="choice.key"
          type="button"
          role="tab"
          class="rounded px-2 py-1.5 text-[11px] font-medium transition-colors"
          :class="filter === choice.key ? 'bg-accent/15 text-accent' : 'text-content-muted hover:text-content'"
          :aria-selected="filter === choice.key"
          @click="filter = choice.key as typeof filter"
        >
          {{ choice.label }}
        </button>
      </div>
    </div>

    <div class="min-h-[240px] flex-1 space-y-1 overflow-y-auto p-2 custom-scrollbar">
      <button
        v-for="pack in filtered"
        :key="pack.id"
        type="button"
        class="flex w-full items-start gap-2.5 rounded-md px-3 py-2.5 text-left transition-colors"
        :class="selectedId === pack.id ? 'bg-accent/15 ring-1 ring-accent/30' : 'hover:bg-overlay-faint'"
        @click="$emit('select', pack.id)"
      >
        <MapPinIcon v-if="pack.pack_type === 'location'" class="mt-0.5 h-4 w-4 shrink-0 text-content-muted" />
        <CubeIcon v-else class="mt-0.5 h-4 w-4 shrink-0 text-content-muted" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-xs font-medium text-content">{{ pack.element.name }}</span>
          <span class="mt-1 block font-mono text-[9px] text-content-muted">{{ pack.element.reference_id }}</span>
        </span>
        <ReferenceStatusBadge :status="pack.status" />
      </button>
      <div v-if="!filtered.length" class="px-3 py-8 text-center text-xs text-content-muted">
        Aucune référence dans ce filtre.
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 border-t border-edge-subtle p-3">
      <Button size="sm" variant="secondary" :disabled="creating" @click="$emit('create', 'location')">
        <MapPinIcon class="h-4 w-4" />
        Nouveau lieu
      </Button>
      <Button size="sm" variant="secondary" :disabled="creating" @click="$emit('create', 'prop')">
        <PlusIcon class="h-4 w-4" />
        Nouveau prop
      </Button>
    </div>
  </aside>
</template>
