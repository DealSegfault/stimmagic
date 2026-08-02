import type { GradientMask } from './types.ts'

/**
 * The selection an Adjust action saw at the instant it was activated.
 *
 * Creating an adjustment may first remove an untouched provisional step. That
 * work can render and reproject workspace state, so reading the live selection
 * afterwards makes the click race the housekeeping that precedes it. Capture
 * the representation the scoped step will consume up front: editable geometry
 * for a matching gradient, or an immutable raster copy for every other mask.
 */
export type AdjustmentScopeSnapshot<TMask> =
  | { kind: 'gradient'; gradient: GradientMask }
  | { kind: 'raster'; mask: TMask }

export function captureAdjustmentScope<TMask>(
  selection: TMask | null,
  copyMask: (source: TMask) => TMask,
  workspaceGradient: GradientMask | null,
  workspaceGradientKey: string | null,
  selectionAppliedKey: string | null,
): AdjustmentScopeSnapshot<TMask> | null {
  if (!selection) return null
  if (workspaceGradient && workspaceGradientKey === selectionAppliedKey) {
    return { kind: 'gradient', gradient: { ...workspaceGradient } }
  }
  return { kind: 'raster', mask: copyMask(selection) }
}
