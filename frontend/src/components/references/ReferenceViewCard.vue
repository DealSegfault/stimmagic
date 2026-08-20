<script setup lang="ts">
import { computed } from 'vue'
import { ArrowPathIcon, CheckIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { MediaImage } from '../media'
import Button from '../ui/Button.vue'
import ReferenceStatusBadge from './ReferenceStatusBadge.vue'
import type { ReferenceView } from '../../composables/useProjectReferencesApi'

const props = defineProps<{
  view: ReferenceView
  busy?: boolean
}>()

defineEmits<{
  generate: [ReferenceView]
  approve: [ReferenceView]
  reject: [ReferenceView]
}>()

const displayMediaId = computed(() => props.view.candidate_media_id || props.view.approved_media_id)
const isCandidate = computed(() => Boolean(props.view.candidate_media_id))
const shotNumbers = computed(() => {
  const values = props.view.view_spec?.shot_numbers
  return Array.isArray(values) ? values : []
})
</script>

<template>
  <article class="overflow-hidden rounded-lg border border-edge bg-surface">
    <div class="relative aspect-[4/3] bg-matte">
      <MediaImage
        v-if="displayMediaId"
        :media-id="displayMediaId"
        :asset-id="view.asset_id || undefined"
        :thumbnail="false"
        :contain="true"
        :enable-context-menu="false"
        :alt="`${view.label} — ${isCandidate ? 'candidate' : 'approved'}`"
        container-class="h-full w-full"
        img-class="h-full w-full object-contain"
      />
      <div v-else class="flex h-full flex-col items-center justify-center px-5 text-center">
        <span class="font-mono text-[10px] uppercase tracking-[0.18em] text-content-muted">{{ view.view_key }}</span>
        <p class="mt-2 text-xs text-content-secondary">Cette vue n’a pas encore été générée.</p>
      </div>
      <span v-if="isCandidate" class="absolute left-2 top-2 rounded bg-black/70 px-2 py-1 text-[10px] text-white">Candidate</span>
      <div class="absolute right-2 top-2"><ReferenceStatusBadge :status="view.status" /></div>
    </div>

    <div class="space-y-3 p-3">
      <div>
        <div class="flex items-center justify-between gap-3">
          <h3 class="truncate text-xs font-semibold text-content">{{ view.label }}</h3>
          <span class="shrink-0 font-mono text-[9px] text-content-muted">v{{ view.approved_revision_id || '—' }}</span>
        </div>
        <p v-if="shotNumbers.length" class="mt-1 truncate text-[10px] text-content-muted">
          Utilisée par P{{ shotNumbers.map((number) => String(number).padStart(2, '0')).join(', P') }}
        </p>
        <p v-else class="mt-1 font-mono text-[9px] text-content-muted">
          {{ view.view_type }} · {{ view.state_key }}
        </p>
      </div>

      <div v-if="isCandidate" class="grid grid-cols-2 gap-2">
        <Button size="sm" :disabled="busy" @click="$emit('approve', view)">
          <CheckIcon class="h-4 w-4" /> Approuver
        </Button>
        <Button size="sm" variant="secondary" :disabled="busy" @click="$emit('reject', view)">
          <XMarkIcon class="h-4 w-4" /> Rejeter
        </Button>
      </div>
      <Button v-else size="sm" variant="secondary" class="w-full" :loading="busy" @click="$emit('generate', view)">
        <ArrowPathIcon class="h-4 w-4" />
        {{ view.approved_media_id ? 'Nouvelle candidate' : 'Générer la vue' }}
      </Button>
    </div>
  </article>
</template>
