<script setup lang="ts">
/**
 * The tool families, across the top of the editor.
 *
 * Clicking a family enters its mode and opens the sub-bar directly beneath;
 * clicking the active one leaves. Entering a mode never edits the stack — the
 * step is created by the first real gesture.
 */
import { computed } from 'vue'
import { TOOL_FAMILIES, FAMILY_EDITOR_ICON } from '../../composables/imageStack/toolFamilies'
import { icons as editorIcons } from '@stimma/image-editor'
import type { FamilyId } from '../../composables/imageStack/toolFamilies'
import { sanitizeSvg } from '../../utils/sanitizeHtml'
import Tooltip from '../ui/Tooltip.vue'

defineProps<{ active: FamilyId | null }>()
const emit = defineEmits<{ select: [FamilyId] }>()

/**
 * A family's mark: the snapshot editor's own icon where it has one, so a tool
 * looks like itself across both editors, and a drawn fragment for the two verbs
 * that are new.
 */
const families = computed(() =>
  TOOL_FAMILIES.map(family => {
    const editorIcon = FAMILY_EDITOR_ICON[family.id]
    return {
      ...family,
      svg: sanitizeSvg(
        editorIcon
          ? (editorIcons as any)[editorIcon]
          : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
              stroke-linecap="round" stroke-linejoin="round">${family.icon}</svg>`
      ),
    }
  })
)
</script>

<template>
  <div class="flex items-center gap-0.5">
    <Tooltip
      v-for="family in families"
      :key="family.id"
      :text="`${family.label} · ${family.key.toUpperCase()}`"
    >
      <button
        type="button"
        class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 ring-accent/60"
        :class="active === family.id
          ? 'bg-accent/15 text-accent-hi'
          : 'text-content-secondary hover:text-content hover:bg-overlay-subtle'"
        @click="emit('select', family.id)"
      >
        <span class="w-[15px] h-[15px] shrink-0" v-html="family.svg" />
        {{ family.label }}
      </button>
    </Tooltip>
  </div>
</template>
