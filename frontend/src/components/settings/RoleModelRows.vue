<script setup lang="ts">
/**
 * The four LLM role selectors, shared by profile settings and project settings.
 *
 * Same four roles, same order, same labels in both places — the only difference
 * is what an unset value means, which `inheritLabel` carries. Profiles fall back
 * to `auto` (pick the best available model); projects fall back to the profile.
 */
import { computed, onMounted } from 'vue'
import { useAvailableModels } from '../../composables/useAvailableModels'
import { resolveModelVendorId } from '../../utils/modelVendors'
import SettingsDropdown from '../ui/SettingsDropdown.vue'
import SettingRow from './SettingRow.vue'

const props = defineProps<{
  /** role -> saved slug. '' / null means unset (inherit). */
  modelValue: Record<string, string | null>
  /** Project scope, so the resolved preview reflects this project's overrides. */
  projectId?: number | null
  /** True in project settings, where an unset role inherits the profile. */
  inherits?: boolean
}>()

const emit = defineEmits<{ (e: 'update:role', role: string, slug: string): void }>()

const { selectableModels, roleDefaults, fetchModels } = useAvailableModels()

const ROLES = [
  {
    key: 'quick_task',
    label: 'LLM for Quick Tasks',
    description: 'Captioning, chat names, and other background work.',
  },
  {
    key: 'tool_assistant',
    label: 'LLM for Tool Assistant',
    description: 'The assistant and prompt tools inside a tool.',
  },
  {
    key: 'chat',
    label: 'LLM for new Chats',
    description: 'The model a new chat starts on.',
  },
  {
    key: 'flow',
    label: 'LLM for Flows',
    description: 'The model written into new flow programs.',
  },
]

function endpointHost(url?: string) {
  if (!url) return ''
  try { return new URL(url).host } catch { return url }
}

const modelOptions = computed(() => selectableModels.value
  .filter(model => model.source !== 'auto' && !model.collapsed)
  .map(model => ({
    value: model.slug,
    label: model.name,
    description: `via ${model.source === 'stimma_cloud' ? 'Stimma' : (model.provider_name || endpointHost(model.endpoint_url) || 'your endpoint')}`,
    meta: model.cost_tier || '',
    tone: model.source === 'stimma_cloud' ? 'cloud' : undefined,
    vendor: resolveModelVendorId(model) || undefined,
  })))

/** Name of the model a role currently resolves to, for the inherit label. */
function resolvedName(role: string) {
  const slug = props.inherits
    ? roleDefaults.value[role]?.profile
    : roleDefaults.value[role]?.resolved
  if (!slug || slug === 'auto') {
    const resolved = roleDefaults.value[role]?.resolved
    const match = selectableModels.value.find(m => m.slug === resolved)
    return match?.name || ''
  }
  const match = selectableModels.value.find(m => m.slug === slug)
  return match?.name || slug
}

function inheritOption(role: string) {
  const name = resolvedName(role)
  const base = props.inherits ? 'Inherit from profile' : 'Automatic'
  return {
    value: '',
    label: name ? `${base} (${name})` : base,
    description: props.inherits
      ? 'Use whatever this profile is set to.'
      : 'Pick the best available model for this kind of work.',
  }
}

function optionsFor(role: string) {
  return [inheritOption(role), ...modelOptions.value]
}

/** '' selects the inherit row; an unknown saved slug also falls back to it. */
function selectedFor(role: string) {
  const slug = props.modelValue?.[role]
  if (!slug || slug === 'auto') return ''
  return modelOptions.value.some(o => o.value === slug) ? slug : ''
}

onMounted(() => fetchModels(props.projectId ?? null, true))
</script>

<template>
  <div>
    <SettingRow
      v-for="role in ROLES"
      :key="role.key"
      :label="role.label"
      :description="role.description"
    >
      <SettingsDropdown
        control
        fill
        class="w-72"
        :menu-width="320"
        :model-value="selectedFor(role.key)"
        :options="optionsFor(role.key)"
        @update:model-value="slug => emit('update:role', role.key, slug)"
      />
    </SettingRow>
  </div>
</template>
