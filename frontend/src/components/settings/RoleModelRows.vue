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
  /** role -> saved effort. '' / null means unset (whatever the role is worth). */
  efforts?: Record<string, string | null>
  /** Project scope, so the resolved preview reflects this project's overrides. */
  projectId?: number | null
  /** True in project settings, where an unset role inherits the profile. */
  inherits?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:role', role: string, slug: string): void
  (e: 'update:effort', role: string, effort: string): void
}>()

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
    description: 'The model new flows run on.',
  },
]

function endpointHost(url?: string) {
  if (!url) return ''
  try { return new URL(url).host } catch { return url }
}

/** A model you host yourself: no bill, and the hostname is plumbing. */
function isLocal(model: any) {
  return model?.provider_kind === 'local' || model?.source === 'endpoint'
}

function optionFor(model: any) {
  const base = {
    value: model.slug,
    label: model.name,
    vendor: resolveModelVendorId(model) || undefined,
  }
  // Local models carry neither of the trailing details: there is no cost, and
  // which box serves it says nothing you'd choose on. Dropping them also gives
  // the long self-hosted names the whole trigger instead of an ellipsis.
  if (isLocal(model)) return base
  return {
    ...base,
    description: `via ${model.source === 'stimma_cloud' ? 'Stimma' : (model.provider_name || endpointHost(model.endpoint_url) || 'your endpoint')}`,
    meta: model.cost_tier || '',
    tone: model.source === 'stimma_cloud' ? 'cloud' : undefined,
  }
}

const modelOptions = computed(() => selectableModels.value
  .filter(model => model.source !== 'auto' && !model.collapsed)
  .map(optionFor))

function modelFor(slug?: string | null) {
  if (!slug) return null
  return selectableModels.value.find(m => m.slug === slug) || null
}

/**
 * What the fallback row would actually give you. This describes the OPTION, not
 * the current selection — in a project that means the profile's resolution
 * (ignoring this project's override), and at profile level it means what the
 * tier heuristic picks, whether or not `auto` is what's saved.
 */
function fallbackModel(role: string) {
  const entry = roleDefaults.value[role]
  return modelFor(props.inherits ? entry?.profile_resolved : entry?.auto)
}

/**
 * The row you land on when nothing is pinned. In the MENU it names the mode
 * ("Automatic"); on the TRIGGER it shows the model actually in effect, tagged so
 * the tracking state is still legible. Showing the mode alone on the trigger
 * would hide the one thing you came to check.
 */
function inheritOption(role: string) {
  const model = fallbackModel(role)
  return {
    value: '',
    label: props.inherits ? 'Inherit from profile' : 'Automatic',
    triggerLabel: model?.name || (props.inherits ? 'Inherit from profile' : 'Automatic'),
    triggerMeta: props.inherits ? 'Inherited' : 'Auto',
    vendor: model ? (resolveModelVendorId(model) || undefined) : undefined,
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

/** The model a role is actually running, so its ladder is the one we offer. */
function effectiveModel(role: string) {
  const slug = props.modelValue?.[role]
  if (slug && slug !== 'auto') return modelFor(slug)
  return fallbackModel(role)
}

function effortLevels(role: string): string[] {
  return effectiveModel(role)?.reasoning?.levels || []
}

/** What's pinned here, or '' when the role's own intent is deciding. */
function selectedEffort(role: string) {
  const pinned = props.efforts?.[role]
  return pinned && effortLevels(role).includes(pinned) ? pinned : ''
}

/** The level the role's intent lands on, shown on the Automatic chip. */
function autoEffort(role: string) {
  return roleDefaults.value[role]?.auto_effort || ''
}

function effortLabel(level: string) {
  if (level === 'off') return 'Off'
  if (level === 'xhigh') return 'XHigh'
  return level.charAt(0).toUpperCase() + level.slice(1)
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
        class="w-80"
        :menu-width="340"
        :model-value="selectedFor(role.key)"
        :options="optionsFor(role.key)"
        @update:model-value="slug => emit('update:role', role.key, slug)"
      >
        <template v-if="effortLevels(role.key).length > 1" #footer>
          <div class="mb-1.5 text-[11px] font-medium text-content-muted">Reasoning</div>
          <div class="flex flex-wrap gap-1">
            <button
              type="button"
              class="rounded-md border px-2 py-1 text-[11px]"
              :class="selectedEffort(role.key) === ''
                ? 'border-blue-500/50 bg-blue-500/15 text-blue-400'
                : 'border-edge-subtle bg-overlay-light text-content-secondary hover:text-content'"
              @click.stop="emit('update:effort', role.key, '')"
            >Automatic{{ autoEffort(role.key) ? ` (${effortLabel(autoEffort(role.key))})` : '' }}</button>
            <button
              v-for="level in effortLevels(role.key)"
              :key="level"
              type="button"
              class="rounded-md border px-2 py-1 text-[11px]"
              :class="selectedEffort(role.key) === level
                ? 'border-blue-500/50 bg-blue-500/15 text-blue-400'
                : 'border-edge-subtle bg-overlay-light text-content-secondary hover:text-content'"
              @click.stop="emit('update:effort', role.key, level)"
            >{{ effortLabel(level) }}</button>
          </div>
        </template>
      </SettingsDropdown>
    </SettingRow>
  </div>
</template>
