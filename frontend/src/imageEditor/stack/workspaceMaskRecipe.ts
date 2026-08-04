/**
 * The workspace selection as a RECIPE, not only a bitmap.
 *
 * The selection model flattens every gesture into one alpha canvas — correct
 * for consumers that want coverage, lossy for the one that wants ingredients:
 * a scoped adjustment's composite mask. This module keeps the parallel
 * record: one entry per landed gesture, with the gesture's own coverage,
 * combine mode, and identity (gradient geometry, semantic name, tool label).
 *
 * The recipe is strictly best-effort bookkeeping. Any operation it cannot
 * describe — invert, grow/shrink, a handle drag on the flattened raster, a
 * gesture combined onto a selection that predates tracking — resolves to
 * null, and consumers fall back to the flattened raster exactly as before.
 * A missing recipe is honest; a wrong one is not.
 *
 * Generic over the mask payload so the reducer is testable without a DOM.
 */
import type { GradientMask, MaskComponentMode, SelectionSemantic } from './types.ts'
import type { SelectionMode } from './toolFamilies.ts'

export interface WorkspaceMaskGesture<TMask> {
  /** How this gesture met the coverage before it; the first entry is `add`. */
  mode: MaskComponentMode
  /** Tool name for the component row: Rectangle, Ellipse, Lasso, Wand, Brush… */
  label?: string
  /** The gesture's own coverage, for raster gestures. */
  mask?: TMask
  /** Parametric identity, for gradient gestures. */
  gradient?: GradientMask
  /** Recomputable identity, for AI gestures ("sky", the subject). */
  semantic?: SelectionSemantic
}

export interface WorkspaceGestureInput<TMask> {
  /** The island's combine mode at gesture time. */
  combine: SelectionMode
  /** Whether a selection existed BEFORE this gesture landed. */
  hadSelection: boolean
  /** Pop the previous entry first — object-pick granularity cycling re-lands
   *  the same click at a different granularity over the pre-click selection. */
  replacesPrevious?: boolean
  label?: string
  mask?: TMask
  gradient?: GradientMask
  semantic?: SelectionSemantic
}

/** Labels the drawn tools contribute to their component rows. */
export const GESTURE_TOOL_LABELS: Record<string, string> = {
  rect: 'Rectangle',
  ellipse: 'Ellipse',
  lasso: 'Lasso',
  magnetic: 'Lasso',
  wand: 'Wand',
  brush: 'Brush',
  object: 'Object',
}

function entryOf<TMask>(
  gesture: WorkspaceGestureInput<TMask>,
  mode: MaskComponentMode,
): WorkspaceMaskGesture<TMask> {
  return {
    mode,
    ...(gesture.label ? { label: gesture.label } : {}),
    ...(gesture.mask !== undefined ? { mask: gesture.mask } : {}),
    ...(gesture.gradient ? { gradient: { ...gesture.gradient } } : {}),
    ...(gesture.semantic ? { semantic: { ...gesture.semantic } } : {}),
  }
}

/** Whether two entries are the same brush being extended, not a new idea. */
function extendsBrush<TMask>(
  last: WorkspaceMaskGesture<TMask> | undefined,
  entry: WorkspaceMaskGesture<TMask>,
): boolean {
  return !!last
    && last.label === 'Brush'
    && entry.label === 'Brush'
    && last.mode === entry.mode
    && last.mask !== undefined
    && entry.mask !== undefined
    && !last.semantic
    && !entry.semantic
}

/**
 * Fold one landed gesture into the recipe.
 *
 * `mergeMasks` unions two raster coverages (max), used to keep a run of brush
 * strokes one editable Brush component instead of one row per stroke.
 */
export function appendWorkspaceMaskGesture<TMask>(
  recipe: WorkspaceMaskGesture<TMask>[] | null,
  gesture: WorkspaceGestureInput<TMask>,
  mergeMasks?: (a: TMask, b: TMask) => TMask,
): WorkspaceMaskGesture<TMask>[] | null {
  const previous = gesture.replacesPrevious && recipe?.length
    ? recipe.slice(0, -1)
    : recipe
  const hadSelection = gesture.replacesPrevious && previous !== null
    ? previous.length > 0
    : gesture.hadSelection

  // A gesture that IS the whole selection starts the recipe over; its own
  // combine mode is spent replacing, so it seeds as the base.
  if (gesture.combine === 'new' || !hadSelection) {
    return [entryOf(gesture, 'add')]
  }
  // Combined onto a selection the recipe cannot describe: stay honest.
  if (!previous || !previous.length) return null

  const entry = entryOf(gesture, gesture.combine)
  const last = previous[previous.length - 1]
  if (mergeMasks && extendsBrush(last, entry)) {
    return [
      ...previous.slice(0, -1),
      { ...last, mask: mergeMasks(last.mask as TMask, entry.mask as TMask) },
    ]
  }
  return [...previous, entry]
}
