<script setup lang="ts">
import { computed } from 'vue'
import { bgClass, dotClass, textClass, type StatusBucket } from '../../utils/statusColors'
import type { ReferenceStatus } from '../../composables/useProjectReferencesApi'

const props = defineProps<{ status: ReferenceStatus }>()

const labels: Record<ReferenceStatus, string> = {
  missing: 'Manquante',
  draft: 'Brouillon',
  generating: 'Génération',
  review: 'À revoir',
  approved: 'Approuvée',
  stale: 'À régénérer',
  inconsistent: 'Incohérente',
  rejected: 'Rejetée',
  error: 'Erreur',
}

const buckets: Record<ReferenceStatus, StatusBucket> = {
  missing: 'queued',
  draft: 'queued',
  generating: 'running',
  review: 'awaiting',
  approved: 'done',
  stale: 'warning',
  inconsistent: 'warning',
  rejected: 'skipped',
  error: 'failed',
}

const bucket = computed(() => buckets[props.status] || 'queued')
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-medium"
    :class="[bgClass(bucket), textClass(bucket)]"
  >
    <span class="h-1.5 w-1.5 rounded-full" :class="dotClass(bucket)" />
    {{ labels[status] }}
  </span>
</template>
