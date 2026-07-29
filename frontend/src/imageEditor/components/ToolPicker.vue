<script setup lang="ts">
/**
 * The tools that can run the active sub-tool, and nothing else.
 *
 * Deliberately NOT the full catalog menu: that one opens on the task type,
 * offers every task, and carries a search — all of which is wrong when the
 * question is only "which tool does this inpaint". What is reused is the ROW —
 * icon, name, provider label — so a tool reads the same here as everywhere.
 */
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import ToolIcon from '../../components/tools/ToolIcon.vue'
import ToolProviderLabel from '../../components/tools/ToolProviderLabel.vue'

const props = withDefaults(defineProps<{
  tools: any[]
  /** Only tools that can run this task are listed. */
  taskType: string
  selectedId?: string | null
  /**
   * Width. A fixed 320px is right under a toolbar with the whole window to
   * spill into; in the right-hand sidebar it hangs off the edge of the screen,
   * so that host asks for the column's width instead.
   */
  widthClass?: string
}>(), { widthClass: 'w-[320px]' })

const emit = defineEmits<{ select: [any]; close: [] }>()

const root = ref<HTMLElement | null>(null)

const eligible = computed(() =>
  props.tools.filter(tool => (tool.task_types || []).includes(props.taskType))
)

function isCloud(tool: any): boolean {
  return tool.provider_type === 'stimma-cloud' || tool.is_stimma_cloud === true
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) emit('close')
}
onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown, true))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointerDown, true))
</script>

<template>
  <div
    ref="root"
    :class="[
      widthClass,
      'max-h-[min(420px,50vh)] overflow-y-auto custom-scrollbar',
      'rounded-lg border border-edge-subtle bg-surface-overlay shadow-xl py-1',
    ]"
  >
    <p v-if="!eligible.length" class="px-3.5 py-3 text-xs text-content-tertiary">
      No installed tool can do this yet.
    </p>
    <button
      v-for="tool in eligible"
      :key="tool.full_tool_id"
      type="button"
      class="w-full px-3.5 py-2 text-left text-[13px] flex items-center gap-2.5 transition-colors"
      :class="tool.full_tool_id === selectedId
        ? 'bg-selection/20 text-content'
        : 'text-content hover:bg-overlay-light'"
      @click="emit('select', tool)"
    >
      <div class="w-3.5 h-3.5 shrink-0" :class="isCloud(tool) ? '' : 'text-content-tertiary'">
        <ToolIcon :tool="tool" size="xs" :bare="true" :ring="false" />
      </div>
      <span class="flex-1 min-w-0 truncate">{{ tool.name }}</span>
      <ToolProviderLabel :cloud="isCloud(tool)" :provider-name="tool.provider_name" class="pl-3" />
    </button>
  </div>
</template>
