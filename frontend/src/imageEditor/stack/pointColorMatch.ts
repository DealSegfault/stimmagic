/**
 * The Point color edit's brand-match math.
 *
 * The eyedropper stores a reference color as HSL; the render path applies
 * hue/sat/lum SHIFTS around it. Match inverts that: given the reference and a
 * target hex, compute the shift values that land the reference exactly on the
 * target, so "make this red the brand red" is one click and the result stays
 * editable as ordinary sliders.
 *
 * The luminance inversion mirrors the renderer's asymmetric lift
 * (`l + shift * (shift > 0 ? 1 - l : l) * 0.6`), so the solved shift is exact
 * rather than approximate.
 */

export interface HslColor {
  /** Degrees, 0..360. */
  hue: number
  /** Percent, 0..100. */
  sat: number
  /** Percent, 0..100. */
  lum: number
}

export interface PointColorShifts {
  pointHueShift: number
  pointSatShift: number
  pointLumShift: number
}

const clamp = (value: number, low: number, high: number) =>
  Math.max(low, Math.min(high, value))

export function hexToHsl(hex: string): HslColor | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!match) return null
  const packed = parseInt(match[1], 16)
  return rgbToHslColor((packed >> 16) & 255, (packed >> 8) & 255, packed & 255)
}

/** 0..255 channels → the HSL shape the point-color params store. */
export function rgbToHslColor(red: number, green: number, blue: number): HslColor {
  const r = red / 255
  const g = green / 255
  const b = blue / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const delta = max - min
  const lightness = (max + min) / 2
  let hue = 0
  let saturation = 0
  if (delta > 1e-6) {
    saturation = lightness > 0.5 ? delta / (2 - max - min) : delta / (max + min)
    hue = max === r
      ? 60 * (((g - b) / delta) % 6)
      : max === g
        ? 60 * ((b - r) / delta + 2)
        : 60 * ((r - g) / delta + 4)
    if (hue < 0) hue += 360
  }
  return { hue, sat: saturation * 100, lum: lightness * 100 }
}

export function hslToHex(color: HslColor): string {
  const h = ((color.hue % 360) + 360) % 360
  const s = clamp(color.sat, 0, 100) / 100
  const l = clamp(color.lum, 0, 100) / 100
  const chroma = (1 - Math.abs(2 * l - 1)) * s
  const x = chroma * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - chroma / 2
  let rgb: [number, number, number]
  if (h < 60) rgb = [chroma, x, 0]
  else if (h < 120) rgb = [x, chroma, 0]
  else if (h < 180) rgb = [0, chroma, x]
  else if (h < 240) rgb = [0, x, chroma]
  else if (h < 300) rgb = [x, 0, chroma]
  else rgb = [chroma, 0, x]
  const channel = (value: number) =>
    Math.round(clamp(value + m, 0, 1) * 255).toString(16).padStart(2, '0')
  return `#${channel(rgb[0])}${channel(rgb[1])}${channel(rgb[2])}`
}

/**
 * Shift values that move `picked` onto `target` through the renderer's
 * application at full weight. Values clamp to slider range, so an
 * out-of-reach target lands as close as the sliders allow.
 */
export function matchShifts(picked: HslColor, target: HslColor): PointColorShifts {
  let hueDelta = target.hue - picked.hue
  if (hueDelta > 180) hueDelta -= 360
  if (hueDelta < -180) hueDelta += 360

  // Renderer: s' = s * (1 + shift/100). Inverse is a ratio; a gray reference
  // cannot be re-saturated multiplicatively, so it pins to the extreme.
  const pickedSat = picked.sat / 100
  const targetSat = target.sat / 100
  const satShift = pickedSat < 0.005
    ? (targetSat > 0.005 ? 100 : 0)
    : ((targetSat / pickedSat) - 1) * 100

  // Renderer: l' = l + shift * (shift > 0 ? 1 - l : l) * 0.6.
  const pickedLum = picked.lum / 100
  const targetLum = target.lum / 100
  const lumDelta = targetLum - pickedLum
  const lumShift = lumDelta > 0
    ? (pickedLum >= 0.995 ? 0 : lumDelta / ((1 - pickedLum) * 0.6))
    : (pickedLum <= 0.005 ? 0 : lumDelta / (pickedLum * 0.6))

  return {
    pointHueShift: Math.round(clamp(hueDelta, -180, 180)),
    pointSatShift: Math.round(clamp(satShift, -100, 100)),
    pointLumShift: Math.round(clamp(lumShift * 100, -100, 100)),
  }
}
