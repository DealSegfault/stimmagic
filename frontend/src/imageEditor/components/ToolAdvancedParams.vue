<script lang="ts">
import type { GenericParamGroup } from '../../composables/useToolSchemaFeatures'

/**
 * The scalar parameters this popover can host, after the hosting surface's
 * exclusions. Exported so the trigger that OPENS the popover can hide itself
 * when there is nothing to show — an affordance that opens an apology is a
 * broken promise, not a control.
 */
export function filterScalarGroups(
  groups: GenericParamGroup[],
  exclude?: string[],
): GenericParamGroup[] {
  const excluded = new Set(exclude ?? [])
  return groups
    .map(group => ({
      ...group,
      params: group.params.filter(param =>
        !excluded.has(param.name)
        && (!!param.enum || ['string', 'number', 'integer', 'boolean'].includes(param.type))
      ),
    }))
    .filter(group => group.params.length > 0)
}
</script>

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
  /**
   * Parameter names the hosting surface renders with its own control — the
   * Expand card owns the four edge percents — so Advanced must not show a
   * second, disagreeing copy.
   */
  exclude?: string[]
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

const scalarGroups = computed(() => {
  const groups = filterScalarGroups(groupedGenericParams.value, props.exclude)
  // A lone section needs no header — the popover IS the section, and a
  // provider label like "Advanced" over the only group reads as noise.
  return groups.length === 1
    ? groups.map(group => ({ ...group, label: '' }))
    : groups
})

</script>

<template>
  <div v-if="tool" class="space-y-3">
    <SchemaParamGroup
      v-if="scalarGroups.length"
      :full-tool-id="tool.full_tool_id"
      :groups="scalarGroups"
      :values="values"
      flat
      :dividers="false"
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
