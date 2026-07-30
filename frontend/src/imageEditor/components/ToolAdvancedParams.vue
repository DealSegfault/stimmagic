<script setup lang="ts">
/**
 * The ordinary STP parameter surface for an editor-hosted model tool.
 *
 * These are the same schema-driven controls ToolView uses. Inputs owned by the
 * editor (image, mask, prompt, and patch dimensions) are deliberately absent.
 */
import { computed } from 'vue'
import SchemaParamGroup from '../../components/generation/SchemaParamGroup.vue'
import { useToolSchemaFeatures } from '../../composables/useToolSchemaFeatures'

const props = defineProps<{
  tool: any | null
  values: Record<string, any>
}>()

const emit = defineEmits<{
  update: [string, any]
}>()

const toolRef = computed(() => props.tool)
const {
  groupedGenericParams,
} = useToolSchemaFeatures({
  tool: toolRef,
  availableLoras: computed(() => []),
})

const scalarGroups = computed(() =>
  groupedGenericParams.value
    .map(group => ({
      ...group,
      params: group.params.filter(param =>
        !!param.enum || ['string', 'number', 'integer', 'boolean'].includes(param.type)
      ),
    }))
    .filter(group => group.params.length > 0)
)

</script>

<template>
  <div v-if="tool" class="space-y-3">
    <SchemaParamGroup
      v-if="scalarGroups.length"
      :full-tool-id="tool.full_tool_id"
      :groups="scalarGroups"
      :values="values"
      flat
      disable-collapse
      @update:param="(name: string, value: any) => emit('update', name, value)"
    />

    <p
      v-if="!scalarGroups.length"
      class="text-xs text-content-tertiary"
    >
      This tool has no additional parameters.
    </p>
  </div>
</template>
