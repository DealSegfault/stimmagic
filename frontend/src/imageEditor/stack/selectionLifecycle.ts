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
