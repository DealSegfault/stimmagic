<template>
  <div class="border-b border-edge-subtle bg-surface-raised/40 p-4 transition-all">
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold uppercase tracking-wider text-accent">Brief & Direction créative</span>
          <span v-if="saveState === 'saved'" class="text-[11px] font-medium text-emerald-400">Enregistré</span>
          <span v-else-if="isDirty" class="text-[11px] font-medium text-amber-400">Non enregistré (⌘↵)</span>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg border border-edge bg-surface px-2.5 py-1 text-xs font-medium text-content-secondary hover:bg-overlay-light hover:text-content transition-colors"
            @click="$emit('close')"
          >
            Fermer
          </button>
          <button
            type="button"
            class="rounded-lg bg-accent px-3 py-1 text-xs font-semibold text-accent-contrast shadow-sm hover:bg-accent-hover transition-colors disabled:opacity-40"
            :disabled="!isDirty || saveState === 'saving'"
            @click="save"
          >
            {{ saveState === 'saving' ? 'Enregistrement…' : 'Enregistrer' }}
          </button>
        </div>
      </div>

      <!-- Description / Script & Director Prompt Grid -->
      <div class="grid gap-3 sm:grid-cols-2">
        <!-- Script Excerpt / Description -->
        <div class="space-y-1">
          <label class="text-[11px] font-semibold text-content-secondary">Extrait du scénario / Description</label>
          <textarea
            v-model="draftDescription"
            rows="3"
            class="w-full rounded-lg border border-edge bg-base px-3 py-2 text-xs leading-relaxed text-content placeholder:text-content-muted focus:border-accent focus:outline-none transition-colors custom-scrollbar"
            placeholder="Description scénaristique de la scène..."
            @keydown.meta.enter.prevent="save"
            @keydown.ctrl.enter.prevent="save"
          />
        </div>

        <!-- Director Prompt -->
        <div class="space-y-1">
          <label class="text-[11px] font-semibold text-content-secondary">Prompt Directeur (Intentions visuelles, focale, éclairage)</label>
          <textarea
            v-model="draftPrompt"
            rows="3"
            class="w-full rounded-lg border border-edge bg-base px-3 py-2 text-xs leading-relaxed text-content placeholder:text-content-muted focus:border-accent focus:outline-none transition-colors custom-scrollbar"
            placeholder="Directives visuelles pour l'IA et les modèles..."
            @keydown.meta.enter.prevent="save"
            @keydown.ctrl.enter.prevent="save"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
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
