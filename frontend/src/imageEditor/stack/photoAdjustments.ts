import {
  isIdentityToneCurve,
  toneCurveChannelLut,
  type ToneCurve,
} from './toneCurve.ts'

export interface PhotographicAdjustmentParams {
  highlights?: number
  shadows?: number
  whites?: number
  blacks?: number
  curve?: ToneCurve
  hue?: number
  vibrance?: number
  colorizeHue?: number
  colorizeAmount?: number
  dehaze?: number
}

export function hasPhotographicAdjustments(params: PhotographicAdjustmentParams) {
  return (
    (params.highlights ?? 0) !== 0 || (params.shadows ?? 0) !== 0 ||
    (params.whites ?? 0) !== 0 || (params.blacks ?? 0) !== 0 ||
    !isIdentityToneCurve(params.curve) ||
    (params.hue ?? 0) !== 0 || (params.vibrance ?? 0) !== 0 ||
    (params.colorizeAmount ?? 0) !== 0 ||
    (params.dehaze ?? 0) !== 0
  )
}

function hueColor(hue: number, saturation: number, value: number): [number, number, number] {
  const h = ((hue % 360) + 360) % 360 / 60
  const chroma = value * saturation
  const x = chroma * (1 - Math.abs((h % 2) - 1))
  let rgb: [number, number, number]
  if (h < 1) rgb = [chroma, x, 0]
  else if (h < 2) rgb = [x, chroma, 0]
  else if (h < 3) rgb = [0, chroma, x]
  else if (h < 4) rgb = [0, x, chroma]
  else if (h < 5) rgb = [x, 0, chroma]
  else rgb = [chroma, 0, x]
  const m = value - chroma
  return [rgb[0] + m, rgb[1] + m, rgb[2] + m]
}

function rotateHue(r: number, g: number, b: number, degrees: number): [number, number, number] {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const delta = max - min
  if (delta < 1e-6) return [r, g, b]
  let hue = max === r
    ? 60 * (((g - b) / delta) % 6)
    : max === g
      ? 60 * ((b - r) / delta + 2)
      : 60 * ((r - g) / delta + 4)
  if (hue < 0) hue += 360
  return hueColor(hue + degrees, max <= 0 ? 0 : delta / max, max)
}

/** Tonal and color controls that cannot be represented by a color matrix. */
export function applyPhotographicAdjustments(
  data: ImageData,
  params: PhotographicAdjustmentParams,
) {
  const highlights = (params.highlights ?? 0) / 100
  const shadows = (params.shadows ?? 0) / 100
  const whites = (params.whites ?? 0) / 100
  const blacks = (params.blacks ?? 0) / 100
  const curve = params.curve
  const hue = params.hue ?? 0
  const vibrance = (params.vibrance ?? 0) / 100
  const colorize = (params.colorizeAmount ?? 0) / 100
  const colorizeHue = params.colorizeHue ?? 0
  const dehaze = (params.dehaze ?? 0) / 100
  const hasCurve = !isIdentityToneCurve(curve)
  const curveLuts = hasCurve
    ? {
        red: toneCurveChannelLut(curve, 'red', 4097),
        green: toneCurveChannelLut(curve, 'green', 4097),
        blue: toneCurveChannelLut(curve, 'blue', 4097),
      }
    : null
  const curveLookup = (value: number, lut: number[]) => {
    const scaled = Math.max(0, Math.min(1, value)) * (lut.length - 1)
    const left = Math.min(lut.length - 2, Math.floor(scaled))
    return lut[left] + (lut[left + 1] - lut[left]) * (scaled - left)
  }
  const pixels = data.data
  const smoothstep = (low: number, high: number, candidate: number) => {
    const t = Math.max(0, Math.min(1, (candidate - low) / (high - low)))
    return t * t * (3 - 2 * t)
  }

  for (let i = 0; i < pixels.length; i += 4) {
    let r = pixels[i] / 255
    let g = pixels[i + 1] / 255
    let b = pixels[i + 2] / 255
    let luminance = r * 0.2126 + g * 0.7152 + b * 0.0722

    const tonal =
      highlights * smoothstep(0.45, 1, luminance) * 0.35 +
      shadows * (1 - smoothstep(0, 0.55, luminance)) * 0.35 +
      whites * smoothstep(0.72, 1, luminance) * 0.28 +
      blacks * (1 - smoothstep(0, 0.28, luminance)) * 0.28
    r += tonal
    g += tonal
    b += tonal

    if (dehaze !== 0) {
      luminance = r * 0.2126 + g * 0.7152 + b * 0.0722
      const contrast = 1 + dehaze * 0.55
      const saturation = 1 + dehaze * 0.35
      r = (r - 0.5) * contrast + 0.5 - dehaze * 0.03
      g = (g - 0.5) * contrast + 0.5 - dehaze * 0.03
      b = (b - 0.5) * contrast + 0.5 - dehaze * 0.03
      r = luminance + (r - luminance) * saturation
      g = luminance + (g - luminance) * saturation
      b = luminance + (b - luminance) * saturation
    }

    if (curveLuts) {
      r = curveLookup(r, curveLuts.red)
      g = curveLookup(g, curveLuts.green)
      b = curveLookup(b, curveLuts.blue)
    }

    if (hue !== 0) [r, g, b] = rotateHue(r, g, b, hue)

    if (vibrance !== 0) {
      luminance = r * 0.2126 + g * 0.7152 + b * 0.0722
      const chroma = Math.max(r, g, b) - Math.min(r, g, b)
      // Positive Vibrance favours muted colors; negative values back all color
      // away evenly. Luminance is held constant in either direction.
      const scale = vibrance > 0
        ? 1 + vibrance * (1 - Math.max(0, Math.min(1, chroma))) * 1.35
        : 1 + vibrance
      r = luminance + (r - luminance) * scale
      g = luminance + (g - luminance) * scale
      b = luminance + (b - luminance) * scale
    }

    if (colorize > 0) {
      luminance = Math.max(0, Math.min(1, r * 0.2126 + g * 0.7152 + b * 0.0722))
      const tint = hueColor(colorizeHue, 0.72, Math.max(0.12, luminance))
      r += (tint[0] - r) * colorize
      g += (tint[1] - g) * colorize
      b += (tint[2] - b) * colorize
    }

    pixels[i] = Math.max(0, Math.min(255, r * 255))
    pixels[i + 1] = Math.max(0, Math.min(255, g * 255))
    pixels[i + 2] = Math.max(0, Math.min(255, b * 255))
  }
}
