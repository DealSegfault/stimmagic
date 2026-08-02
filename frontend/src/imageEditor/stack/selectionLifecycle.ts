import type { SelectionMode, SelectToolId } from './toolFamilies'

/** A brush is additive by nature; an empty canvas still starts in union mode. */
export function emptySelectionCombine(tool: SelectToolId | null): SelectionMode {
  return tool === 'brush' ? 'add' : 'new'
}

/**
 * Combine is explicit while a selection exists. Publishing a mask must never
 * rewrite the next gesture from New to Add; once the mask is empty, combine
 * returns to the only meaningful starting state.
 */
export function combineAfterSelectionChange(
  current: SelectionMode,
  hasSelection: boolean,
  tool: SelectToolId | null = null,
): SelectionMode {
  return hasSelection ? current : emptySelectionCombine(tool)
}

export type EditorEscapeAction =
  | 'clear-selection'
  | 'dismiss-retouch-feedback'
  | 'leave-family'
  | 'clear-shape'
  | 'none'

/**
 * Resolve Escape against canvas CONTENT, not the tool chrome around it.
 *
 * An armed selection tool's raised parameter palette is the visible expression
 * of the selected tool, not a transient popup. Escape may clear the pixels that
 * tool selected, but only a different tool choice or an explicit pointer
 * handoff may disarm the tool. It also must not tunnel through the armed tool
 * and close a suspended family underneath it.
 */
export function editorEscapeAction(state: {
  hasSelection: boolean
  hasRetouchFeedback: boolean
  hasArmedSelectionTool: boolean
  hasFamily: boolean
  hasSelectedShape: boolean
}): EditorEscapeAction {
  if (state.hasSelection) return 'clear-selection'
  if (state.hasRetouchFeedback) return 'dismiss-retouch-feedback'
  if (state.hasArmedSelectionTool) return 'none'
  if (state.hasFamily) return 'leave-family'
  if (state.hasSelectedShape) return 'clear-shape'
  return 'none'
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
