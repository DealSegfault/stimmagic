/**
 * Paint helpers for the editor's UI.
 *
 * A paint is a flat color or a gradient (see `ported/shapeTypes`). The
 * renderer resolves one against a shape's box; the panels only need to preview
 * one in CSS, convert the built-in presets, and move between the two forms
 * when the user switches a well from Solid to Gradient.
 */
import type { Color } from '../ported/geometry.ts'
import type { GradientDirection, GradientPaint, Paint } from '../ported/shapeTypes.ts'
import { GRADIENT_PRESETS } from '../ported/shapeTypes.ts'

export const DEFAULT_GRADIENT_DIRECTION: GradientDirection = 'horizontal'

export function isGradient(paint: Paint | null | undefined): paint is GradientPaint {
  return !!paint && typeof paint === 'object' && (paint as GradientPaint).type === 'gradient'
}

export function makeGradient(colors: Color[], direction: GradientDirection = DEFAULT_GRADIENT_DIRECTION): GradientPaint {
  return { type: 'gradient', colors: colors.map(c => ({ ...c })), direction }
}

/** The solid a gradient collapses to when a well switches back to Solid. */
export function paintSolid(paint: Paint | null | undefined): Color | null {
  if (!paint) return null
  return isGradient(paint) ? (paint.colors?.[0] ?? null) : paint
}

export function colorCss(color: Color | null | undefined): string {
  if (!color) return 'transparent'
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${color.a ?? 1})`
}

/** A paint as a CSS background, for wells and previews. */
export function paintCss(paint: Paint | null | undefined, angle?: string): string {
  if (!paint) return 'transparent'
  if (!isGradient(paint)) return colorCss(paint)
  const stops = paint.colors?.length ? paint.colors : [{ r: 255, g: 255, b: 255, a: 1 }]
  if (stops.length === 1) return colorCss(stops[0])
  const direction = angle ?? cssAngle(paint.direction)
  return `linear-gradient(${direction}, ${stops.map(colorCss).join(', ')})`
}

export function cssAngle(direction: GradientDirection | undefined): string {
  switch (direction) {
    case 'vertical': return '180deg'
    case 'diagonal': return '135deg'
    default: return '90deg'
  }
}

// -- hex, for the presets and any place a color is written as text ----------

export function hexToColor(css: string): Color {
  const hex = css.trim().replace('#', '')
  const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex
  const value = Number.parseInt(full.slice(0, 6), 16)
  if (Number.isNaN(value)) return { r: 255, g: 255, b: 255, a: 1 }
  return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255, a: 1 }
}

/** The built-in presets as paints. */
export function presetGradients(direction: GradientDirection = DEFAULT_GRADIENT_DIRECTION) {
  return GRADIENT_PRESETS.map(preset => ({
    id: preset.id,
    name: preset.name,
    paint: makeGradient(preset.colors.map(hexToColor), direction),
  }))
}

/**
 * The gradient a solid becomes when a well is switched to Gradient.
 *
 * Seeded FROM the color that was there — a well that jumped to some unrelated
 * preset would read as "gradient replaced my color" rather than "my color is
 * now a gradient". The second stop is the same color rotated round the wheel,
 * which is visibly a gradient without being a different hue family.
 */
export function gradientFromSolid(color: Color | null | undefined): GradientPaint {
  const base = color ?? { r: 255, g: 255, b: 255, a: 1 }
  return makeGradient([{ ...base }, rotateHue(base, 60)])
}

function rotateHue(color: Color, degrees: number): Color {
  const r = color.r / 255, g = color.g / 255, b = color.b / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  let h = 0
  let s = 0
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break
      case g: h = ((b - r) / d + 2) / 6; break
      default: h = ((r - g) / d + 4) / 6; break
    }
  }
  const hue = (h * 360 + degrees + 360) % 360
  // A grey has no hue to rotate, so give it one rather than returning itself.
  const sat = s < 0.05 ? 0.5 : s
  const k = (n: number) => (n + hue / 30) % 12
  const a = sat * Math.min(l, 1 - l)
  const f = (n: number) => l - a * Math.max(Math.min(k(n) - 3, 9 - k(n), 1), -1)
  return {
    r: Math.round(f(0) * 255),
    g: Math.round(f(8) * 255),
    b: Math.round(f(4) * 255),
    a: color.a ?? 1,
  }
}
