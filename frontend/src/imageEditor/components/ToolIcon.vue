<script setup lang="ts">
/**
 * One glyph from the snapshot editor's icon registry.
 *
 * The registry stores whole `<svg>` strings, so this renders them sanitized
 * rather than reaching for a component per icon.
 */
import { computed } from 'vue'
import { icons } from '../ported/icons'
import type { IconName } from '../ported/icons'
import { sanitizeSvg } from '../../utils/sanitizeHtml'

const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 })

const svg = computed(() => sanitizeSvg(icons[props.name] ?? ''))
</script>

<template>
  <span
    class="inline-flex items-center justify-center shrink-0 [&>svg]:w-full [&>svg]:h-full"
    :style="{ width: size + 'px', height: size + 'px' }"
    v-html="svg"
  />
</template>
