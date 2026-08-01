/**
 * Expand (outpaint) geometry, in one place so every consumer agrees.
 *
 * The outpaint-image contract: four integer percents, each of the SOURCE
 * image's corresponding axis, each edge growing by `floor(axis · pct / 100)`
 * pixels. The formula is shared verbatim with the backend's Extend Canvas
 * step, the cloud planner, and the ComfyUI padding node — truncate, never
 * round, or the four implementations disagree by a pixel and the dims check
 * rejects a correct result.
 *
 * Kept free of rendering imports: geometryBelow and the compositor both mirror
 * these numbers, and the mirror law (see cropAffine) demands one source.
 */

import { OUTPAINT_EXPAND_FIELDS } from '../../utils/taskTypeValidation.ts'

export interface ExpandEdges {
  top: number
  bottom: number
  left: number
  right: number
}

export const ZERO_EDGES: ExpandEdges = { top: 0, bottom: 0, left: 0, right: 0 }

function clampPct(value: unknown): number {
  const n = Math.floor(Number(value))
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0
}

/** The wire params for a set of edges, by the contract's exact field names. */
export function expandParamsFromEdges(edges: ExpandEdges): Record<string, number> {
  return {
    expand_top_pct: clampPct(edges.top),
    expand_bottom_pct: clampPct(edges.bottom),
    expand_left_pct: clampPct(edges.left),
    expand_right_pct: clampPct(edges.right),
  }
}

/** Read edges back out of an op's (or tool's) params. */
export function expandEdgesFromParams(params: Record<string, any> | undefined): ExpandEdges {
  return {
    top: clampPct(params?.expand_top_pct),
    bottom: clampPct(params?.expand_bottom_pct),
    left: clampPct(params?.expand_left_pct),
    right: clampPct(params?.expand_right_pct),
  }
}

export interface ExpandFrame {
  /** Grown frame size. */
  width: number
  height: number
  /** Where the source's top-left lands inside the grown frame. */
  left: number
  top: number
}

/** The grown frame for a source of `width`×`height` — the tri-repo formula. */
export function expandedFrame(edges: ExpandEdges, width: number, height: number): ExpandFrame {
  const px = (axis: number, pct: number) => Math.floor((axis * clampPct(pct)) / 100)
  const left = px(width, edges.left)
  const right = px(width, edges.right)
  const top = px(height, edges.top)
  const bottom = px(height, edges.bottom)
  return {
    width: width + left + right,
    height: height + top + bottom,
    left,
    top,
  }
}

export function hasExpansion(edges: ExpandEdges): boolean {
  return OUTPAINT_EXPAND_FIELDS.some(
    field => expandParamsFromEdges(edges)[field] > 0
  )
}

/**
 * The border mask at the GROWN size: white where the tool invents pixels,
 * black where the source sits. Never uploaded — outpaint tools declare no
 * mask input — but the candidate machinery needs it: its dimensions tell the
 * ingest check what size a correct result comes back at, and its bounds crop
 * the candidate (a ring touches every edge, so the patch is the whole frame).
 */
export function expandBorderMask(
  sourceWidth: number,
  sourceHeight: number,
  frame: ExpandFrame,
): HTMLCanvasElement {
  const mask = document.createElement('canvas')
  mask.width = frame.width
  mask.height = frame.height
  const ctx = mask.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, frame.width, frame.height)
  ctx.fillStyle = '#000'
  ctx.fillRect(frame.left, frame.top, sourceWidth, sourceHeight)
  return mask
}
