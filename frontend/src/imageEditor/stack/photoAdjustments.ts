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
  /** Mixer: `mixer{Hue|Sat|Lum}{Band}` sliders, -100..100. */
  [key: `mixer${string}`]: number | undefined
  // Point color: the eyedropped reference plus the shifts applied around it.
  pointHue?: number
  pointSat?: number
  pointLum?: number
  pointHueShift?: number
  pointSatShift?: number
  pointLumShift?: number
  pointRange?: number
  // Grading: three luminance-zone wheels.
  gradeShadowHue?: number
  gradeShadowSat?: number
  gradeShadowLum?: number
  gradeMidHue?: number
  gradeMidSat?: number
  gradeMidLum?: number
  gradeHighlightHue?: number
  gradeHighlightSat?: number
  gradeHighlightLum?: number
  gradeBlend?: number
  gradeBalance?: number
}

/** Band centers, in the Mixer's fixed order. Mirrored by the GPU preview. */
export const MIXER_BAND_HUES = [0, 30, 60, 120, 180, 240, 285, 330]
const MIXER_BAND_IDS = [
  'Red', 'Orange', 'Yellow', 'Green', 'Aqua', 'Blue', 'Purple', 'Magenta',
]

export function mixerBandValues(
  params: PhotographicAdjustmentParams,
  mode: 'Hue' | 'Sat' | 'Lum',
): number[] {
  return MIXER_BAND_IDS.map(band =>
    (params as Record<string, any>)[`mixer${mode}${band}`] ?? 0,
  )
}

/**
 * The value the band sliders give a hue: linear interpolation between the two
 * neighbouring band centers, wrapping at red. At a center the band owns the
 * hue outright; between centers the two neighbours share it, weights summing
 * to one — the same partition the GPU preview computes per band.
 */
export function mixerValueAtHue(hue: number, bandValues: number[]): number {
  const wrapped = ((hue % 360) + 360) % 360
  for (let index = 0; index < MIXER_BAND_HUES.length; index++) {
    const left = MIXER_BAND_HUES[index]
    const right = index === MIXER_BAND_HUES.length - 1
      ? 360
      : MIXER_BAND_HUES[index + 1]
    if (wrapped >= left && wrapped < right) {
      const t = (wrapped - left) / (right - left)
      const next = (index + 1) % MIXER_BAND_HUES.length
      return bandValues[index] * (1 - t) + bandValues[next] * t
    }
  }
  return bandValues[0]
}

export function hasMixerAdjustments(params: PhotographicAdjustmentParams) {
  return (['Hue', 'Sat', 'Lum'] as const).some(mode =>
    mixerBandValues(params, mode).some(value => value !== 0),
  )
}

export function hasPointColorAdjustments(params: PhotographicAdjustmentParams) {
  return (
    (params.pointHueShift ?? 0) !== 0 ||
    (params.pointSatShift ?? 0) !== 0 ||
    (params.pointLumShift ?? 0) !== 0
  )
}

export function hasGradingAdjustments(params: PhotographicAdjustmentParams) {
  return (
    (params.gradeShadowSat ?? 0) !== 0 || (params.gradeShadowLum ?? 0) !== 0 ||
    (params.gradeMidSat ?? 0) !== 0 || (params.gradeMidLum ?? 0) !== 0 ||
    (params.gradeHighlightSat ?? 0) !== 0 || (params.gradeHighlightLum ?? 0) !== 0
  )
}

export function hasPhotographicAdjustments(params: PhotographicAdjustmentParams) {
  return (
    (params.highlights ?? 0) !== 0 || (params.shadows ?? 0) !== 0 ||
    (params.whites ?? 0) !== 0 || (params.blacks ?? 0) !== 0 ||
    !isIdentityToneCurve(params.curve) ||
    (params.hue ?? 0) !== 0 || (params.vibrance ?? 0) !== 0 ||
    (params.colorizeAmount ?? 0) !== 0 ||
    (params.dehaze ?? 0) !== 0 ||
    hasMixerAdjustments(params) ||
    hasPointColorAdjustments(params) ||
    hasGradingAdjustments(params)
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

/** RGB (0..1) → HSL with hue in degrees, saturation and lightness 0..1. */
function rgbToHsl01(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const delta = max - min
  const lightness = (max + min) / 2
  if (delta < 1e-6) return [0, 0, lightness]
  const saturation = lightness > 0.5
    ? delta / (2 - max - min)
    : delta / (max + min)
  let hue = max === r
    ? 60 * (((g - b) / delta) % 6)
    : max === g
      ? 60 * ((b - r) / delta + 2)
      : 60 * ((r - g) / delta + 4)
  if (hue < 0) hue += 360
  return [hue, saturation, lightness]
}

function hsl01ToRgb(h: number, s: number, l: number): [number, number, number] {
  const hue = ((h % 360) + 360) % 360
  const chroma = (1 - Math.abs(2 * l - 1)) * s
  const x = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const m = l - chroma / 2
  let rgb: [number, number, number]
  if (hue < 60) rgb = [chroma, x, 0]
  else if (hue < 120) rgb = [x, chroma, 0]
  else if (hue < 180) rgb = [0, chroma, x]
  else if (hue < 240) rgb = [0, x, chroma]
  else if (hue < 300) rgb = [x, 0, chroma]
  else rgb = [chroma, 0, x]
  return [rgb[0] + m, rgb[1] + m, rgb[2] + m]
}

function smooth01(t: number) {
  if (t <= 0) return 0
  if (t >= 1) return 1
  return t * t * (3 - 2 * t)
}

/** Angular hue distance, 0..180. */
function hueDistance(a: number, b: number) {
  const raw = Math.abs(a - b) % 360
  return raw > 180 ? 360 - raw : raw
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

  // Mixer: per-band values normalised once; the loop only interpolates.
  const mixerActive = hasMixerAdjustments(params)
  const mixerHues = mixerBandValues(params, 'Hue').map(value => value / 100)
  const mixerSats = mixerBandValues(params, 'Sat').map(value => value / 100)
  const mixerLums = mixerBandValues(params, 'Lum').map(value => value / 100)

  // Point color: reference and shifts. Range maps to the hue falloff width.
  const pointActive = hasPointColorAdjustments(params)
  const pointRefHue = params.pointHue ?? 0
  const pointRefSat = (params.pointSat ?? 0) / 100
  const pointRefLum = (params.pointLum ?? 0) / 100
  const pointHueShift = params.pointHueShift ?? 0
  const pointSatShift = (params.pointSatShift ?? 0) / 100
  const pointLumShift = (params.pointLumShift ?? 0) / 100
  const pointRangeDeg = 12 + (params.pointRange ?? 50) * 0.78

  // Grading: per-zone tint deltas and luminance lifts, precomputed as RGB
  // offsets the way split toning does it.
  const gradeActive = hasGradingAdjustments(params)
  const gradeBlend = (params.gradeBlend ?? 50) / 100
  const gradeBalance = (params.gradeBalance ?? 0) / 100
  const gradeMidpoint = 0.5 + gradeBalance * 0.2
  const gradeSoftness = 0.12 + gradeBlend * 0.33
  const gradeLowCross = gradeMidpoint - 0.17
  const gradeHighCross = gradeMidpoint + 0.17
  const gradeTint = (hueValue: number | undefined, satValue: number | undefined) => {
    const tint = hueColor(hueValue ?? 0, 1, 1)
    const strength = ((satValue ?? 0) / 100) * 0.3
    return [
      (tint[0] - 0.5) * strength,
      (tint[1] - 0.5) * strength,
      (tint[2] - 0.5) * strength,
    ]
  }
  const gradeShadowTint = gradeTint(params.gradeShadowHue, params.gradeShadowSat)
  const gradeMidTint = gradeTint(params.gradeMidHue, params.gradeMidSat)
  const gradeHighTint = gradeTint(params.gradeHighlightHue, params.gradeHighlightSat)
  const gradeShadowLum = (params.gradeShadowLum ?? 0) / 100
  const gradeMidLum = (params.gradeMidLum ?? 0) / 100
  const gradeHighLum = (params.gradeHighlightLum ?? 0) / 100

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

    if (mixerActive || pointActive) {
      let [pixelHue, pixelSat, pixelLum] = rgbToHsl01(
        Math.max(0, Math.min(1, r)),
        Math.max(0, Math.min(1, g)),
        Math.max(0, Math.min(1, b)),
      )

      if (mixerActive) {
        // Near-grays have no meaningful hue; fading the effect in over the
        // first stops of saturation keeps them from flickering between bands.
        const grayGuard = smooth01((pixelSat - 0.04) / 0.12)
        if (grayGuard > 0) {
          const hueDelta = mixerValueAtHue(pixelHue, mixerHues) * grayGuard
          const satDelta = mixerValueAtHue(pixelHue, mixerSats) * grayGuard
          const lumDelta = mixerValueAtHue(pixelHue, mixerLums) * grayGuard
          pixelHue += hueDelta * 30
          pixelSat = Math.max(0, Math.min(1, pixelSat * (1 + satDelta)))
          pixelLum += lumDelta * (lumDelta > 0 ? 1 - pixelLum : pixelLum) * 0.5
        }
      }

      if (pointActive) {
        // A near-gray reference cannot anchor on hue, so it relies on the
        // saturation/lightness windows alone.
        const hueWeight = pointRefSat < 0.05
          ? 1
          : smooth01(1 - hueDistance(pixelHue, pointRefHue) / pointRangeDeg)
        const satWeight = smooth01(1 - Math.abs(pixelSat - pointRefSat) / 0.7)
        const lumWeight = smooth01(1 - Math.abs(pixelLum - pointRefLum) / 0.7)
        const weight = hueWeight * satWeight * lumWeight
        if (weight > 0) {
          pixelHue += pointHueShift * weight
          pixelSat = Math.max(0, Math.min(1, pixelSat * (1 + pointSatShift * weight)))
          pixelLum += pointLumShift * weight
            * (pointLumShift > 0 ? 1 - pixelLum : pixelLum) * 0.6
        }
      }

      ;[r, g, b] = hsl01ToRgb(
        pixelHue,
        pixelSat,
        Math.max(0, Math.min(1, pixelLum)),
      )
    }

    if (gradeActive) {
      luminance = Math.max(0, Math.min(1, r * 0.2126 + g * 0.7152 + b * 0.0722))
      const shadowWeight = 1 - smoothstep(
        gradeLowCross - gradeSoftness, gradeLowCross + gradeSoftness, luminance,
      )
      const highWeight = smoothstep(
        gradeHighCross - gradeSoftness, gradeHighCross + gradeSoftness, luminance,
      )
      const midWeight = Math.max(0, Math.min(1, 1 - shadowWeight - highWeight))
      r += gradeShadowTint[0] * shadowWeight + gradeMidTint[0] * midWeight + gradeHighTint[0] * highWeight
      g += gradeShadowTint[1] * shadowWeight + gradeMidTint[1] * midWeight + gradeHighTint[1] * highWeight
      b += gradeShadowTint[2] * shadowWeight + gradeMidTint[2] * midWeight + gradeHighTint[2] * highWeight
      const lift = (
        gradeShadowLum * shadowWeight + gradeMidLum * midWeight + gradeHighLum * highWeight
      ) * 0.25
      r += lift
      g += lift
      b += lift
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
