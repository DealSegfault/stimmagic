/**
 * Feather is stored in source-image pixels, but a linear 0–1000 slider makes
 * the useful 0–50 range almost impossible to hit. This exponential display
 * curve preserves precision at small radii while still reaching large-image
 * blends. The document value remains an ordinary pixel radius.
 */
export const MAX_FEATHER_PX = 1000
export const FEATHER_SLIDER_MAX = 1000
const CURVE = 4
const CURVE_RANGE = Math.exp(CURVE) - 1

export function featherPxFromSlider(value: number): number {
  const position = Math.max(0, Math.min(FEATHER_SLIDER_MAX, value)) / FEATHER_SLIDER_MAX
  return Math.round(MAX_FEATHER_PX * (Math.exp(CURVE * position) - 1) / CURVE_RANGE)
}

export function featherSliderFromPx(value: number): number {
  const pixels = Math.max(0, Math.min(MAX_FEATHER_PX, value))
  const position = Math.log1p((pixels / MAX_FEATHER_PX) * CURVE_RANGE) / CURVE
  return Math.round(position * FEATHER_SLIDER_MAX)
}
