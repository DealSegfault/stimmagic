import type { SelectionMode } from './toolFamilies'

/**
 * Combine is explicit while a selection exists. Publishing a mask must never
 * rewrite the next gesture from New to Add; once the mask is empty, combine
 * returns to the only meaningful starting state.
 */
export function combineAfterSelectionChange(
  current: SelectionMode,
  hasSelection: boolean,
): SelectionMode {
  return hasSelection ? current : 'new'
}

export type SelectionMatteAction = 'clear-selection' | 'disarm-tool' | 'none'

/**
 * Empty matte resolves visible selection state before changing tools.
 *
 * This keeps one click from both discarding the selection and silently
 * switching away from a deliberately armed tool. Once nothing is selected,
 * the next matte click can return the pointer to idle.
 */
export function selectionMatteAction(
  hasSelection: boolean,
  hasArmedTool: boolean,
): SelectionMatteAction {
  if (hasSelection) return 'clear-selection'
  if (hasArmedTool) return 'disarm-tool'
  return 'none'
}
