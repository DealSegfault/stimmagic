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
