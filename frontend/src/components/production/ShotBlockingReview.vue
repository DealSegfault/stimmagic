<script setup>
import { computed, ref, watch } from 'vue'
import { CheckCircleIcon, ChevronLeftIcon, ChevronRightIcon, ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import Button from '../ui/Button.vue'
import IconButton from '../ui/IconButton.vue'
import Tooltip from '../ui/Tooltip.vue'
import { MediaImage } from '../media'
import ShotBlockingSvg from './ShotBlockingSvg.vue'
import ShotBlockingTimeline from './ShotBlockingTimeline.vue'

const props = defineProps({
  shot: { type: Object, required: true },
  sequence: { type: Object, required: true },
  previousShot: { type: Object, default: null },
  nextShot: { type: Object, default: null },
  index: { type: Number, required: true },
  total: { type: Number, required: true },
  saving: { type: Boolean, default: false },
})

defineEmits(['previous', 'next', 'toggle-review', 'open-reference'])

const activeFrameIndex = ref(0)
const blocking = computed(() => props.shot.blocking || null)
const frames = computed(() => blocking.value?.frames || [])
const activeFrame = computed(() => frames.value[activeFrameIndex.value] || frames.value[0] || null)
const approved = computed(() => blocking.value?.status === 'approved')
const continuity = computed(() => blocking.value?.continuity || {})
const continuityTone = computed(() => continuity.value.verdict === 'review' ? 'text-amber-400' : continuity.value.verdict === 'ok' ? 'text-emerald-400' : 'text-content-secondary')
const locationReference = computed(() => blocking.value?.location_reference || null)

watch(() => props.shot.id, () => { activeFrameIndex.value = 0 })
</script>

<template>
  <section v-if="blocking && activeFrame" class="overflow-hidden rounded-lg border border-edge bg-surface">
    <header class="flex flex-col gap-4 px-5 py-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
      <div class="flex min-w-0 items-start gap-3">
        <div class="flex shrink-0 items-center gap-1">
          <Tooltip text="Plan précédent">
            <IconButton aria-label="Voir le plan précédent" :disabled="!previousShot" @click="$emit('previous')">
              <ChevronLeftIcon class="h-4 w-4" />
            </IconButton>
          </Tooltip>
          <span class="min-w-[66px] text-center font-mono text-[11px] tabular-nums text-content-muted">{{ index + 1 }} / {{ total }}</span>
          <Tooltip text="Plan suivant">
            <IconButton aria-label="Voir le plan suivant" :disabled="!nextShot" @click="$emit('next')">
              <ChevronRightIcon class="h-4 w-4" />
            </IconButton>
          </Tooltip>
        </div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
            <span class="font-mono text-accent">S{{ String(sequence.sequence_number).padStart(2, '0') }} / P{{ String(shot.shot_number).padStart(2, '0') }}</span>
            <span>·</span>
            <span>{{ blocking.location.label }}</span>
            <span>·</span>
            <span class="font-mono">{{ blocking.camera.plan_type }} · {{ blocking.camera.lens }}</span>
          </div>
          <h2 class="mt-1 truncate font-brand text-lg font-semibold text-content">{{ shot.title }}</h2>
          <p class="mt-1 line-clamp-2 max-w-3xl text-xs leading-relaxed text-content-secondary">{{ shot.description }}</p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <span class="inline-flex items-center gap-1.5 text-xs" :class="approved ? 'text-emerald-400' : 'text-content-muted'">
          <CheckCircleIcon class="h-4 w-4" />
          {{ approved ? 'Blocking validé' : 'Brouillon à valider' }}
        </span>
        <Button size="sm" :variant="approved ? 'secondary' : 'primary'" :loading="saving" @click="$emit('toggle-review')">
          {{ approved ? 'Rouvrir la revue' : 'Valider le blocking' }}
        </Button>
      </div>
    </header>

    <div class="grid gap-6 border-t border-edge-subtle px-5 py-5 2xl:grid-cols-[minmax(0,1.45fr)_minmax(330px,0.75fr)]">
      <ShotBlockingSvg :blocking="blocking" :frame="activeFrame" :previous-blocking="previousShot?.blocking" />
      <div class="space-y-4">
        <ShotBlockingTimeline :frames="frames" :active-index="activeFrameIndex" @select="activeFrameIndex = $event" />
        <section v-if="locationReference" class="overflow-hidden rounded-lg border border-edge-subtle bg-base">
          <div v-if="locationReference.approved_media_id" class="aspect-video bg-matte">
            <MediaImage
              :media-id="locationReference.approved_media_id"
              :thumbnail="false"
              :contain="true"
              :enable-context-menu="false"
              :alt="`Location view ${locationReference.label}`"
              container-class="h-full w-full"
              img-class="h-full w-full object-contain"
            />
          </div>
          <div class="flex items-center justify-between gap-3 p-3">
            <div class="min-w-0">
              <p class="truncate text-[11px] font-semibold text-content">{{ locationReference.label }}</p>
              <p class="mt-1 font-mono text-[9px] text-content-muted">{{ locationReference.view_key }} · {{ locationReference.status }}</p>
            </div>
            <Button size="sm" variant="secondary" @click="$emit('open-reference', locationReference)">
              {{ locationReference.approved_media_id ? 'Ouvrir la référence' : 'Générer la référence' }}
            </Button>
          </div>
        </section>
        <section v-else class="rounded-lg border border-dashed border-edge p-4 text-center">
          <p class="text-[11px] text-content-muted">Aucune location view n’est encore reliée à cet angle.</p>
          <Button class="mt-3" size="sm" variant="secondary" @click="$emit('open-reference', null)">Synchroniser les vues</Button>
        </section>
      </div>
    </div>

    <footer class="border-t border-edge-subtle px-5 py-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex min-w-0 items-start gap-2">
          <ExclamationTriangleIcon v-if="continuity.verdict === 'review'" class="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <CheckCircleIcon v-else class="mt-0.5 h-4 w-4 shrink-0" :class="continuityTone" />
          <div>
            <p class="text-xs font-medium" :class="continuityTone">Raccord entrant · {{ continuity.message }}</p>
            <p v-if="continuity.jumps?.length" class="mt-1 text-[11px] text-content-muted">
              <span v-for="jump in continuity.jumps" :key="jump.actor" class="mr-3">{{ jump.actor }} · saut {{ jump.distance_meters.toFixed(1) }} m</span>
            </p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-2 font-mono text-[10px] text-content-muted">
          <span>{{ previousShot ? `P${String(previousShot.shot_number).padStart(2, '0')}` : 'Début' }}</span>
          <span>→</span>
          <span class="text-content">P{{ String(shot.shot_number).padStart(2, '0') }}</span>
          <span>→</span>
          <span>{{ nextShot ? `P${String(nextShot.shot_number).padStart(2, '0')}` : 'Fin' }}</span>
        </div>
      </div>
    </footer>
  </section>

  <div v-else class="rounded-lg border border-edge bg-surface p-10 text-center">
    <h2 class="font-brand text-lg font-semibold text-content">Blocking indisponible</h2>
    <p class="mt-2 text-sm text-content-secondary">Ce plan ne contient pas encore de description exploitable.</p>
  </div>
</template>
