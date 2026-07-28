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

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

export interface RgbaColor {
  r: number
  g: number
  b: number
  a?: number
}

/** Either a CSS colour string or channel values 0-255. */
export type Color = string | RgbaColor

export function colorToCss(color: Color): string {
  if (typeof color === 'string') return color
  const { r, g, b, a = 1 } = color
  return a === 1 ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${a})`
}

/** How the image is placed in the canvas. The new editor draws unzoomed and
 *  unrotated, so this is the identity in practice — but the ported annotation
 *  code takes it as a parameter and there is no reason to cut it out. */
export interface ViewTransform {
  zoom: number
  panX: number
  panY: number
  rotation: number
}

/** How a new selection meets the existing one. */
export type SelectionMode = 'new' | 'add' | 'subtract' | 'intersect'

// The brush types live with the rest of the shape vocabulary, where the
// snapshot editor put them. Re-exported here so the paint side does not have
// to know that.
export type { BrushSettings, BrushPreset } from './shapeTypes'
