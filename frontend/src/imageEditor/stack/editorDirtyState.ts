/**
 * Which open op-stack documents have edits that aren't in the version chain.
 *
 * The editor saves explicitly, so the head can lag the stack; the sidebar entry
 * carries the indicator that says so. Live session state only — a stack with
 * unsaved edits is persisted server-side, but nothing recomputes this at
 * startup, so the dot appears once the document is open in this session.
 */
import { ref, computed } from 'vue'

const dirtyAssets = ref<Set<string>>(new Set())

export function setEditorDirty(assetId: string | number, dirty: boolean) {
  const key = String(assetId)
  if (dirtyAssets.value.has(key) === dirty) return
  const next = new Set(dirtyAssets.value)
  if (dirty) next.add(key)
  else next.delete(key)
  dirtyAssets.value = next
}

export function isEditorDirty(assetId: string | number): boolean {
  return dirtyAssets.value.has(String(assetId))
}

export const dirtyEditorAssets = computed(() => dirtyAssets.value)
