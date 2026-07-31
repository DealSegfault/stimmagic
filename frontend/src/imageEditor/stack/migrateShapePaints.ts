/**
 * Shapes written before a gradient was a color.
 *
 * The old model carried ONE gradient per shape, hung off `style.effect` (or,
 * for text, off `textEffect`), and the renderer decided which slot it landed
 * in: the fill if the shape had one, otherwise the stroke. Now the gradient
 * lives in the slot itself, so this reads that decision back out and writes it
 * where it belongs — which is also the only way an old document keeps looking
 * like itself.
 *
 * Idempotent, and applied to every shape list on the way in: a document may
 * have been written by either model, and both must render.
 */
import type { Color } from '../ported/geometry.ts'
import type { GradientDirection, Shape } from '../ported/shapeTypes.ts'
import { makeGradient, hexToColor, isGradient } from './paints.ts'

interface LegacyStyle {
  effect?: string
  glowIntensity?: number
  glowColor?: Color
  gradientColors?: (Color | string)[]
  gradientDirection?: GradientDirection
}

function toColors(raw: (Color | string)[] | undefined): Color[] {
  return (raw ?? []).map(c => (typeof c === 'string' ? hexToColor(c) : c))
}

/** One shape, converted if it needs it. Returns the same object when it does not. */
export function migrateShapePaint<T extends Shape>(shape: T): T {
  const any = shape as any
  let next: any = shape

  // Shape-level gradient effect: fill if the shape had one, else stroke —
  // the rule the old renderer applied at draw time.
  const style: LegacyStyle | undefined = any.style
  if (style?.effect === 'gradient') {
    const colors = toColors(style.gradientColors)
    const { effect: _effect, gradientColors: _c, gradientDirection: _d, ...keptStyle } = style as any
    next = { ...next, style: Object.keys(keptStyle).length ? { ...keptStyle, effect: 'none' } : undefined }
    if (colors.length >= 2) {
      const paint = makeGradient(colors, style.gradientDirection ?? 'horizontal')
      if (any.backgroundColor) next.backgroundColor = paint
      else if (any.strokeColor) next.strokeColor = paint
    }
  }

  // Text carried its own, as CSS strings, and always on the text itself.
  if (any.textEffect === 'gradient') {
    const colors = toColors(any.gradientColors)
    next = { ...next, textEffect: 'none' }
    if (colors.length >= 2) {
      next.textColor = makeGradient(colors, any.gradientDirection ?? 'horizontal')
    }
  }

  // The loose gradient fields have no meaning once the paint holds them.
  if (next !== shape || any.gradientColors || any.gradientDirection) {
    const { gradientColors: _gc, gradientDirection: _gd, ...rest } = next === shape ? any : next
    next = rest
  }

  return next as T
}

export function migrateShapePaints<T extends Shape>(shapes: T[] | undefined): T[] {
  if (!shapes?.length) return shapes ?? []
  return shapes.map(migrateShapePaint)
}

/** Whether a shape still speaks the old dialect — used by tests and the loader. */
export function needsPaintMigration(shape: any): boolean {
  return shape?.style?.effect === 'gradient' ||
    shape?.textEffect === 'gradient' ||
    (!!shape?.gradientColors && !isGradient(shape?.textColor))
}
