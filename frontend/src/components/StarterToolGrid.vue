<template>
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
    <button
      v-for="pick in picks"
      :key="pick.tool.full_tool_id"
      @click="emit('open', pick.tool.full_tool_id)"
      class="flex items-start gap-3.5 rounded-lg p-3.5 text-left transition-all cursor-pointer"
      :class="isStimmaCloudTool(pick.tool)
        ? 'bg-overlay-faint stimma-cloud-border hover:bg-overlay-subtle'
        : 'bg-overlay-faint border border-edge-subtle hover:bg-overlay-subtle hover:border-edge'"
    >
      <ToolIcon :tool="pick.tool" size="lg" :ring="false" />
      <div class="flex-1 min-w-0">
        <div class="text-sm font-semibold text-content truncate">{{ pick.tool.name }}</div>
        <p v-if="description(pick.tool)" class="text-xs text-content-secondary line-clamp-2 mt-1 leading-relaxed">{{ description(pick.tool) }}</p>
        <div class="flex items-center gap-2 mt-2 overflow-hidden">
          <span v-if="isStimmaCloudTool(pick.tool)" class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-full bg-teal-600/10 border border-teal-600/25 flex-shrink-0">
            <span class="stimma-cloud-text">{{ STIMMA_TOOL_PROVIDER_DISPLAY_NAME }}</span>
          </span>
          <span v-else class="px-2 py-0.5 text-[10px] font-medium rounded-full border border-edge text-content-secondary flex-shrink-0 truncate">
            {{ providerLabel(pick.tool) }}
          </span>
          <span v-if="pick.taskType" class="px-2 py-0.5 text-[10px] font-medium rounded-full border border-edge text-content-secondary flex-shrink-0">
            {{ formatTaskTypeLabel(pick.taskType) }}
          </span>
        </div>
      </div>
    </button>
  </div>
</template>

<script setup>
import ToolIcon from './tools/ToolIcon.vue'
import { formatTaskTypeLabel } from '../utils/taskTypeIcons'
import { isStimmaCloudTool, toolProviderDisplayName, STIMMA_TOOL_PROVIDER_DISPLAY_NAME } from '../utils/stimmaCloud'

defineProps({
  /** Array of { tool, taskType } — taskType may be '' to omit the task badge. */
  picks: { type: Array, required: true },
})

const emit = defineEmits(['open'])

function providerLabel(tool) {
  return toolProviderDisplayName(tool, tool.provider_id || '')
}

function description(tool) {
  return tool.metadata?.description || tool.subtitle || ''
}
</script>
