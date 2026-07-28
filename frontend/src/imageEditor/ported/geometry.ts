/**
 * Geometry primitives, copied from the snapshot editor's `types/geometry.ts`.
 *
 * Copied rather than imported: the snapshot editor is frozen, and the new
 * editor needs to be free to change these without touching it.
 */

export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

export interface Color {
  r: number
  g: number
  b: number
  a?: number
}

/** How a new selection meets the existing one. */
export type SelectionMode = 'new' | 'add' | 'subtract' | 'intersect'

/** Brush parameters, copied from the snapshot editor's `types/shapes.ts`. */
export interface BrushSettings {
  size: number       // pixels
  hardness: number   // 0-100 (0 = soft, 100 = hard edge)
  opacity: number    // 0-100
  flow: number       // 0-100 — paint per stamp; lower builds up
  spacing: number    // 0-100 — % of brush size between stamps
  glow?: number
  jitter?: number
  scatter?: number
}
