import { computed, ref } from 'vue'
import { useAvailableModels } from './useAvailableModels'

/**
 * Resolve whether an agent input has any model it can actually use, and — when
 * it doesn't — WHY, because the two reasons get opposite treatments:
 *
 * - `llmUnconfigured`: the user has no LLM source at all (no provider, no
 *   endpoint, no Stimma account that ever held credits). That's a deliberate
 *   opt-out — optional LLM surfaces hide or gray themselves out quietly.
 * - `llmDegraded`: at least one source is configured but none is usable right
 *   now (zero balance, failed provider test, cloud unreachable). The UI keeps
 *   its normal shape and interactions fail loudly with a remedy CTA.
 *
 * Each input owns its checked flag so it stays interactive while its first
 * availability request is in flight instead of flashing the unavailable
 * treatment during startup. The model catalog itself remains shared.
 */
export function useAgentModelAvailability() {
  const { selectableModels, llmConfigured, error, loading, fetchModels } = useAvailableModels()
  const checked = ref(false)

  const hasViableAgentModel = computed(() => selectableModels.value.length > 0)

  const agentModelUnavailable = computed(() => (
    checked.value && !loading.value && !error.value && !hasViableAgentModel.value
  ))

  // Strict opt-out only: an unknown flag (old backend, fetch not yet resolved)
  // must never hide UI, so it counts as configured.
  const llmUnconfigured = computed(() => (
    agentModelUnavailable.value && llmConfigured.value === false
  ))

  const llmDegraded = computed(() => (
    agentModelUnavailable.value && llmConfigured.value !== false
  ))

  async function checkAgentModels(projectId = null, force = false) {
    try {
      await fetchModels(projectId, force)
    } finally {
      checked.value = true
    }
  }

  return {
    agentModelUnavailable,
    llmUnconfigured,
    llmDegraded,
    hasViableAgentModel,
    checkAgentModels,
  }
}
