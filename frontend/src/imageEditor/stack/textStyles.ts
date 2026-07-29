/**
 * The text presets, in one place.
 *
 * A preset is not a field — "Pill" is a background box with no effect, "Neon"
 * is an effect with no box — so the toolbar (which arms the next text) and the
 * inspector (which edits the selected one) have to agree about a mapping that
 * spans four properties. They agreed by coincidence before, and drifted: the
 * inspector offered neon as a checkbox and could not name Outline at all.
 *
 * Gradient is not among them. A gradient is a color, so it is picked in the
 * Text color well like any other — see `paints.ts`.
 */
import type { Paint } from '../ported/shapeTypes'

export type TextStyleId = 'pill' | 'plain' | 'outline' | 'neon'

export const TEXT_STYLES: { id: TextStyleId; label: string }[] = [
  { id: 'pill', label: 'Pill' },
  { id: 'plain', label: 'Plain' },
  { id: 'outline', label: 'Outline' },
  { id: 'neon', label: 'Neon' },
]

/** The pill's box, which is the only preset that carries one. */
const PILL_BACKGROUND = { r: 0, g: 0, b: 0, a: 0.65 }

/** Which preset a text shape is currently wearing. */
export function textStyleOfShape(shape: any): TextStyleId {
  const effect = shape?.textEffect ?? 'none'
  if (effect === 'outline' || effect === 'neon') return effect
  return shape?.backgroundColor ? 'pill' : 'plain'
}

/**
 * The preset as a patch onto a text shape.
 *
 * `backgroundColor: undefined` is a real value here — the patch is spread over
 * the shape, so the key has to be present to clear a pill's box.
 */
export function textStylePatch(
  style: TextStyleId,
  options: { glowIntensity?: number } = {},
): Record<string, any> {
  switch (style) {
    case 'plain':
      return { textEffect: 'none', backgroundColor: undefined }
    case 'outline':
      return { textEffect: 'outline', backgroundColor: undefined }
    case 'neon':
      return {
        textEffect: 'neon',
        backgroundColor: undefined,
        glowIntensity: options.glowIntensity ?? 70,
      }
    default:
      return {
        textEffect: 'none',
        backgroundColor: { ...PILL_BACKGROUND },
        backgroundPadding: 0.35,
        backgroundCornerRadius: 1,
      }
  }
}

/**
 * The same preset expressed as the ported annotation state, which is what the
 * gesture code reads when it creates the next text shape.
 */
export function textStyleAnnotationState(
  style: TextStyleId,
  color: Paint,
): Record<string, any> {
  const patch = textStylePatch(style)
  return {
    annotateTextColor: color,
    annotateTextBgColor: patch.backgroundColor ?? null,
    annotateTextEffect: patch.textEffect,
    annotateTextFontWeight: style === 'plain' ? ('normal' as const) : undefined,
    annotateTextGlowIntensity: patch.glowIntensity,
    annotateTextBackgroundPadding: patch.backgroundPadding,
    annotateTextBackgroundCornerRadius: patch.backgroundCornerRadius,
  }
}
