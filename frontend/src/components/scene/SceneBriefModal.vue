<template>
  <div v-if="show" class="fixed inset-0 z-modal flex items-center justify-center p-4">
    <!-- Backdrop -->
    <div class="fixed inset-0 bg-black/60 backdrop-blur-sm transition-opacity" @click="$emit('close')" />

    <!-- Modal Box -->
    <div class="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-edge bg-surface shadow-2xl transition-all">
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-edge-subtle bg-surface-raised/40 px-6 py-4">
        <div class="flex items-center gap-2.5">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15 font-mono text-xs font-bold text-accent">
            S{{ scene?.scene_number ? String(scene.scene_number).padStart(2, '0') : '01' }}
          </span>
          <div>
            <h3 class="text-sm font-bold text-content">Brief créatif — {{ scene?.title }}</h3>
            <p class="text-[11px] text-content-muted">Intentions de mise en scène & direction visuelle</p>
          </div>
        </div>

        <button
          type="button"
          class="rounded-lg p-1.5 text-content-muted hover:bg-overlay-light hover:text-content transition-colors"
          @click="$emit('close')"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="p-6 space-y-4 max-h-[70vh] overflow-y-auto custom-scrollbar">
        <!-- Script Excerpt -->
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-content-secondary">
            Extrait du script / Scénario
          </label>
          <textarea
            v-model="draftDescription"
            rows="4"
            class="w-full rounded-xl border border-edge bg-base px-3.5 py-2.5 text-xs leading-relaxed text-content placeholder:text-content-muted focus:border-accent focus:outline-none transition-colors"
            placeholder="Action, dialogue, indications scénaristiques..."
            @keydown.meta.enter.prevent="save"
            @keydown.ctrl.enter.prevent="save"
          />
        </div>

        <!-- Director Prompt -->
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-content-secondary">
            Prompt Directeur (Éclairage, ambiance, focale, style)
          </label>
          <textarea
            v-model="draftPrompt"
            rows="4"
            class="w-full rounded-xl border border-edge bg-base px-3.5 py-2.5 text-xs leading-relaxed text-content placeholder:text-content-muted focus:border-accent focus:outline-none transition-colors"
            placeholder="Directives visuelles pour guider les outils et les modèles IA..."
            @keydown.meta.enter.prevent="save"
            @keydown.ctrl.enter.prevent="save"
          />
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between border-t border-edge-subtle bg-surface-raised/40 px-6 py-3">
        <span class="text-[11px] text-content-muted">Raccourci : ⌘↵ pour enregistrer</span>

        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg border border-edge bg-surface px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
            @click="$emit('close')"
          >
            Annuler
          </button>
          <button
            type="button"
            class="rounded-lg bg-accent px-4 py-1.5 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors disabled:opacity-40"
            :disabled="!isDirty || saveState === 'saving'"
            @click="save"
          >
            {{ saveState === 'saving' ? 'Enregistrement…' : 'Enregistrer les modifications' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  scene: { type: Object, default: null },
  saveState: { type: String, default: 'idle' }
})

const emit = defineEmits(['save', 'close'])

const draftDescription = ref('')
const draftPrompt = ref('')

watch(
  () => props.scene,
  (s) => {
    if (s) {
      draftDescription.value = s.description || ''
      draftPrompt.value = s.prompt || ''
    }
  },
  { immediate: true }
)

const isDirty = computed(() => {
  if (!props.scene) return false
  return (
    draftDescription.value !== (props.scene.description || '') ||
    draftPrompt.value !== (props.scene.prompt || '')
  )
})

function save() {
  if (!isDirty.value) return
  emit('save', {
    description: draftDescription.value,
    prompt: draftPrompt.value
  })
}
</script>
