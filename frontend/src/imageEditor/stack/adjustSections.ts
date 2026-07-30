/**
 * The control surface for the parametric adjustment families: Adjust and
 * Filters.
 *
 * One rule everywhere: the sub-toolbar offers what you can ADD, clicking it
 * creates a focused step, and the step's controls live in its Properties.
 * Adjust offers small single-purpose edits — Light, Color, Detail, the Autos —
 * each its own step with its own controls. Filters offers the preset strip,
 * which also carries the discrete pixel looks (VHS, Glow, Vignette…) that
 * used to hide behind an Effects dropdown: they are picked-by-eye things with
 * one strength, which is exactly what the strip is for.
 *
 * All of these still execute as ONE op kind (`adjust`) through the same fixed
 * pixel pipeline; a step simply carries only the params its doorway set.
 */

import type { IconName } from '../ported/icons'
import {
  DEFAULT_TONE_CURVE,
  toneCurveValueOf,
  type ToneCurve,
} from './toneCurve.ts'

export {
  DEFAULT_TONE_CURVE,
  toneCurveValueOf,
  type ToneCurve,
} from './toneCurve.ts'

/** Which family a group belongs to — the doorway that shows it. */
export type AdjustFamily = 'levels' | 'filters'

export interface AdjustSliderControl {
  kind?: 'slider'
  key: string
  label: string
  min: number
  max: number
  step: number
  default: number
  /** Shown inline in the sub-toolbar rather than only in the inspector. */
  primary?: boolean
}

export interface AdjustCurveControl {
  kind: 'curve'
  key: string
  label: string
  default: ToneCurve
}

export type AdjustControl = AdjustSliderControl | AdjustCurveControl

export function isAdjustSlider(control: AdjustControl): control is AdjustSliderControl {
  return control.kind !== 'curve'
}

export type PhotoAdjustmentGroupId =
  | 'light' | 'color' | 'detail'
  | 'mixer' | 'point' | 'grade'

export type PhotoAdjustmentSection =
  | 'tone' | 'tint' | 'detail'
  | 'mixer' | 'point' | 'grade'

export interface PhotoAdjustmentGroup {
  id: PhotoAdjustmentGroupId
  /** Stable document marker used by existing whole-image adjustment steps. */
  section: PhotoAdjustmentSection
  label: string
  icon: IconName
  controls: AdjustControl[]
  /**
   * A custom inspector surface for the group. The controls stay plain
   * sliders in the schema — projection, parity and masked sharing all treat
   * them as numbers — and only the rendering is specialised.
   */
  presentation?: 'mixer' | 'point' | 'grade'
}

/**
 * The Mixer's fixed hue bands. Centers are the classic HSL-panel anchors;
 * weights between neighbouring centers are triangular, so every hue belongs
 * to at most two bands and the weights always sum to one.
 */
export const MIXER_BANDS = [
  { id: 'Red', label: 'Red', hue: 0, swatch: '#f87171' },
  { id: 'Orange', label: 'Orange', hue: 30, swatch: '#fb923c' },
  { id: 'Yellow', label: 'Yellow', hue: 60, swatch: '#facc15' },
  { id: 'Green', label: 'Green', hue: 120, swatch: '#4ade80' },
  { id: 'Aqua', label: 'Aqua', hue: 180, swatch: '#2dd4bf' },
  { id: 'Blue', label: 'Blue', hue: 240, swatch: '#60a5fa' },
  { id: 'Purple', label: 'Purple', hue: 285, swatch: '#a78bfa' },
  { id: 'Magenta', label: 'Magenta', hue: 330, swatch: '#f472b6' },
] as const

export type MixerMode = 'Hue' | 'Sat' | 'Lum'
export const MIXER_MODES: Array<{ id: MixerMode; label: string }> = [
  { id: 'Hue', label: 'Hue' },
  { id: 'Sat', label: 'Saturation' },
  { id: 'Lum', label: 'Luminance' },
]

export function mixerKey(mode: MixerMode, band: (typeof MIXER_BANDS)[number]['id']) {
  return `mixer${mode}${band}`
}

const MIXER_CONTROLS: AdjustSliderControl[] = MIXER_MODES.flatMap(mode =>
  MIXER_BANDS.map(band => ({
    key: mixerKey(mode.id, band.id),
    label: band.label,
    min: -100, max: 100, step: 1, default: 0,
  })),
)

/**
 * The photographic adjustment surface.
 *
 * This is deliberately shared by whole-image Adjust and masked Retouch. A
 * control must not exist in one inspector with a different name, range, or
 * default in the other.
 */
export const PHOTO_ADJUSTMENT_GROUPS: PhotoAdjustmentGroup[] = [
  {
    id: 'light',
    section: 'tone',
    label: 'Light',
    icon: 'sun',
    controls: [
      { key: 'exposure', label: 'Exposure', min: -100, max: 100, step: 1, default: 0 },
      { key: 'contrast', label: 'Contrast', min: -100, max: 100, step: 1, default: 0 },
      { key: 'highlights', label: 'Highlights', min: -100, max: 100, step: 1, default: 0 },
      { key: 'shadows', label: 'Shadows', min: -100, max: 100, step: 1, default: 0 },
      { key: 'whites', label: 'Whites', min: -100, max: 100, step: 1, default: 0 },
      { key: 'blacks', label: 'Blacks', min: -100, max: 100, step: 1, default: 0 },
      { key: 'brightness', label: 'Brightness', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gamma', label: 'Gamma', min: 0.1, max: 3, step: 0.05, default: 1 },
      { kind: 'curve', key: 'curve', label: 'Curve', default: DEFAULT_TONE_CURVE },
    ],
  },
  {
    id: 'color',
    section: 'tint',
    label: 'Color',
    icon: 'palette',
    controls: [
      { key: 'temperature', label: 'Temperature', min: -100, max: 100, step: 1, default: 0 },
      { key: 'tint', label: 'Tint', min: -100, max: 100, step: 1, default: 0 },
      { key: 'hue', label: 'Hue', min: -180, max: 180, step: 1, default: 0 },
      { key: 'saturation', label: 'Saturation', min: -100, max: 100, step: 1, default: 0 },
      { key: 'vibrance', label: 'Vibrance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'colorizeHue', label: 'Colorize hue', min: 0, max: 360, step: 1, default: 0 },
      { key: 'colorizeAmount', label: 'Colorize', min: 0, max: 100, step: 1, default: 0 },
      { key: 'defringe', label: 'Defringe', min: 0, max: 100, step: 1, default: 0 },
    ],
  },
  {
    id: 'detail',
    section: 'detail',
    label: 'Detail',
    icon: 'focus',
    controls: [
      { key: 'texture', label: 'Texture', min: -100, max: 100, step: 1, default: 0 },
      { key: 'clarity', label: 'Clarity', min: -100, max: 100, step: 1, default: 0 },
      { key: 'dehaze', label: 'Dehaze', min: -100, max: 100, step: 1, default: 0 },
      { key: 'moire', label: 'Moiré', min: 0, max: 100, step: 1, default: 0 },
      { key: 'sharpen', label: 'Sharpening', min: 0, max: 150, step: 1, default: 0 },
      { key: 'sharpenRadius', label: 'Sharpen radius', min: 0.5, max: 3, step: 0.1, default: 1 },
      { key: 'sharpenDetail', label: 'Sharpen detail', min: 0, max: 100, step: 1, default: 0 },
      { key: 'sharpenMasking', label: 'Sharpen masking', min: 0, max: 100, step: 1, default: 0 },
      { key: 'noiseReduction', label: 'Noise reduction', min: 0, max: 100, step: 1, default: 0 },
      { key: 'noiseReductionDetail', label: 'Luminance detail', min: 0, max: 100, step: 1, default: 0 },
      { key: 'noiseReductionContrast', label: 'Luminance contrast', min: 0, max: 100, step: 1, default: 0 },
      { key: 'colorNoiseReduction', label: 'Color noise', min: 0, max: 100, step: 1, default: 0 },
      { key: 'colorNoiseReductionDetail', label: 'Color detail', min: 0, max: 100, step: 1, default: 0 },
      { key: 'colorNoiseReductionSmoothness', label: 'Color smoothness', min: 0, max: 100, step: 1, default: 0 },
      { key: 'noise', label: 'Grain', min: 0, max: 100, step: 1, default: 0 },
      { key: 'grainSize', label: 'Grain size', min: 0, max: 100, step: 1, default: 0 },
      { key: 'grainRoughness', label: 'Grain roughness', min: 0, max: 100, step: 1, default: 50 },
      { key: 'blur', label: 'Blur', min: 0, max: 40, step: 1, default: 0 },
    ],
  },
  {
    id: 'mixer',
    section: 'mixer',
    label: 'Mixer',
    icon: 'mixer',
    presentation: 'mixer',
    controls: MIXER_CONTROLS,
  },
  {
    id: 'point',
    section: 'point',
    label: 'Point color',
    icon: 'pointColor',
    presentation: 'point',
    // The reference (hue/sat/lum) is what the eyedropper picked; the shifts
    // are the edit. Identity while every shift is zero, whatever the picked
    // reference is.
    controls: [
      { key: 'pointHue', label: 'Picked hue', min: 0, max: 360, step: 1, default: 0 },
      { key: 'pointSat', label: 'Picked saturation', min: 0, max: 100, step: 1, default: 0 },
      { key: 'pointLum', label: 'Picked luminance', min: 0, max: 100, step: 1, default: 0 },
      { key: 'pointHueShift', label: 'Hue shift', min: -180, max: 180, step: 1, default: 0 },
      { key: 'pointSatShift', label: 'Saturation', min: -100, max: 100, step: 1, default: 0 },
      { key: 'pointLumShift', label: 'Luminance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'pointRange', label: 'Range', min: 0, max: 100, step: 1, default: 50 },
    ],
  },
  {
    id: 'grade',
    section: 'grade',
    label: 'Grading',
    icon: 'grading',
    presentation: 'grade',
    controls: [
      { key: 'gradeShadowHue', label: 'Shadow hue', min: 0, max: 360, step: 1, default: 0 },
      { key: 'gradeShadowSat', label: 'Shadow strength', min: 0, max: 100, step: 1, default: 0 },
      { key: 'gradeShadowLum', label: 'Shadow luminance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gradeMidHue', label: 'Midtone hue', min: 0, max: 360, step: 1, default: 0 },
      { key: 'gradeMidSat', label: 'Midtone strength', min: 0, max: 100, step: 1, default: 0 },
      { key: 'gradeMidLum', label: 'Midtone luminance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gradeHighlightHue', label: 'Highlight hue', min: 0, max: 360, step: 1, default: 0 },
      { key: 'gradeHighlightSat', label: 'Highlight strength', min: 0, max: 100, step: 1, default: 0 },
      { key: 'gradeHighlightLum', label: 'Highlight luminance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gradeBlend', label: 'Blend', min: 0, max: 100, step: 1, default: 50 },
      { key: 'gradeBalance', label: 'Balance', min: -100, max: 100, step: 1, default: 0 },
    ],
  },
]

export function photoAdjustmentGroup(id: string): PhotoAdjustmentGroup | undefined {
  return PHOTO_ADJUSTMENT_GROUPS.find(group => group.id === id || group.section === id)
}

export const PHOTO_ADJUSTMENT_CONTROLS = PHOTO_ADJUSTMENT_GROUPS.flatMap(
  group => group.controls,
)

export const PHOTO_ADJUSTMENT_KEYS = PHOTO_ADJUSTMENT_CONTROLS.map(
  control => control.key,
)

/**
 * Project a document/settings object onto the photographic render schema.
 *
 * Whole-image and masked Retouch rendering both call this exact function.
 * Missing fields receive schema defaults, so old documents remain valid while
 * newly added supporting parameters behave identically on both surfaces.
 */
export function photoAdjustmentRenderParams(
  source: Record<string, any> | null | undefined,
): Record<string, any> {
  return Object.fromEntries(PHOTO_ADJUSTMENT_CONTROLS.map(control => {
    const candidate = source?.[control.key]
    if (control.kind === 'curve') {
      return [control.key, toneCurveValueOf(candidate)]
    }
    return [
      control.key,
      typeof candidate === 'number' && Number.isFinite(candidate)
        ? candidate
        : control.default,
    ]
  }))
}

/** Named entry points make renderer parity explicit without duplicating it. */
export const wholeImageAdjustmentParams = photoAdjustmentRenderParams
export const maskedRetouchAdjustmentParams = photoAdjustmentRenderParams

export interface AdjustSection {
  id: string
  label: string
  controls: AdjustSliderControl[]
  /** Fields that switch the section on; absent means the sliders speak for it. */
  toggle?: { key: string; label: string }
}

/**
 * Legacy sections, kept for MIGRATED steps only: a document from the snapshot
 * editor carries one blob op with any mix of these params, and selecting that
 * row still needs a full surface. New steps are fine-grained (LEVEL_EDITS and
 * the strip) and never show this.
 */
/** Ranges mirror the snapshot editor's, so a migrated value lands where it was. */
export const ADJUST_SECTIONS: AdjustSection[] = [
  {
    id: 'levels',
    label: 'Adjust',
    controls: [
      { key: 'exposure', label: 'Exposure', min: -100, max: 100, step: 1, default: 0, primary: true },
      { key: 'brightness', label: 'Brightness', min: -100, max: 100, step: 1, default: 0 },
      { key: 'contrast', label: 'Contrast', min: -100, max: 100, step: 1, default: 0 },
      { key: 'saturation', label: 'Saturation', min: -100, max: 100, step: 1, default: 0 },
      { key: 'temperature', label: 'Temperature', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gamma', label: 'Gamma', min: 0.1, max: 3, step: 0.05, default: 1 },
    ],
  },
  {
    id: 'split-tone',
    label: 'Split tone',
    toggle: { key: 'splitToningEnabled', label: 'Split tone' },
    controls: [
      { key: 'splitToningShadowHue', label: 'Shadow hue', min: 0, max: 360, step: 1, default: 30, primary: true },
      { key: 'splitToningShadowSat', label: 'Shadow strength', min: 0, max: 100, step: 1, default: 0 },
      { key: 'splitToningHighlightHue', label: 'Highlight hue', min: 0, max: 360, step: 1, default: 200 },
      { key: 'splitToningHighlightSat', label: 'Highlight strength', min: 0, max: 100, step: 1, default: 0 },
      { key: 'splitToningBalance', label: 'Balance', min: -100, max: 100, step: 1, default: 0 },
    ],
  },
  {
    id: 'effects',
    label: 'Effects',
    controls: [
      { key: 'vignette', label: 'Vignette', min: 0, max: 100, step: 1, default: 0, primary: true },
      { key: 'clarity', label: 'Clarity', min: -100, max: 100, step: 1, default: 0 },
      { key: 'blur', label: 'Blur', min: 0, max: 40, step: 1, default: 0 },
      { key: 'sharpen', label: 'Sharpen', min: 0, max: 100, step: 1, default: 0 },
      { key: 'noise', label: 'Grain', min: 0, max: 100, step: 1, default: 0 },
      { key: 'glow', label: 'Glow', min: 0, max: 100, step: 1, default: 0 },
      { key: 'chromaticAberration', label: 'Fringing', min: 0, max: 100, step: 1, default: 0 },
      { key: 'halftone', label: 'Halftone', min: 0, max: 100, step: 1, default: 0 },
      { key: 'vhs', label: 'VHS', min: 0, max: 100, step: 1, default: 0 },
      { key: 'glitch', label: 'Glitch', min: 0, max: 100, step: 1, default: 0 },
    ],
  },
]

const CONTROLS_BY_KEY = new Map(
  ADJUST_SECTIONS.flatMap(section => section.controls.map(control => [control.key, control]))
)

export function adjustControl(key: string): AdjustSliderControl | undefined {
  return CONTROLS_BY_KEY.get(key)
}

/**
 * The Adjust family's addable edits. Each is its own step with its own small
 * control set — a user thinks "I adjusted the light", not "I opened section
 * two of the levels blob", and the row should read the same way.
 */
export interface LevelEdit {
  id: PhotoAdjustmentSection
  label: string
  icon: IconName
  controls: AdjustControl[]
  presentation?: PhotoAdjustmentGroup['presentation']
  /** Params set at creation, beyond the marker — what makes the edit DO its thing. */
  seed?: Record<string, any>
}

export const LEVEL_EDITS: LevelEdit[] = PHOTO_ADJUSTMENT_GROUPS.map(group => ({
  id: group.section,
  label: group.label,
  icon: group.icon,
  controls: group.controls,
  presentation: group.presentation,
}))

export function levelEditById(id: string): LevelEdit | undefined {
  return LEVEL_EDITS.find(edit => edit.id === id)
}

/**
 * The Autos, as addable edits: each computes slider values from the histogram
 * and lands as a normal Light step seeded with them — inspectable, adjustable
 * and deletable like anything else, not a fire-and-forget action.
 */
export const AUTO_EDITS = [
  { id: 'levels', label: 'Auto levels' },
  { id: 'contrast', label: 'Auto contrast' },
  { id: 'balance', label: 'Auto balance' },
] as const

/**
 * The strip: the snapshot editor's filter presets by category, plus the
 * discrete pixel looks that used to be the Effects dropdown. An entry with
 * `effect` is not a color matrix — clicking it makes a step carrying that one
 * effect param, whose Amount is the param itself.
 *
 * No `None` entry: the strip is not a picker, it ADDS. Removing an edit is the
 * Edits list's job (or clicking the applied entry again).
 */
export interface StripEntry {
  id: string
  label: string
  /** Present on pixel-look entries: the AdjustParams key and the value a click adds. */
  effect?: { key: string; add: number }
}

export const FILTER_CATEGORIES: Array<{ id: string; label: string; filters: StripEntry[] }> = [
  {
    id: 'color',
    label: 'Color',
    filters: [
      { id: 'chrome', label: 'Chrome' }, { id: 'vivid', label: 'Vivid' },
      { id: 'dramatic', label: 'Dramatic' }, { id: 'cold', label: 'Cold' },
      { id: 'warm', label: 'Warm' }, { id: 'pastel', label: 'Pastel' },
      { id: 'fade', label: 'Fade' }, { id: 'vintage', label: 'Vintage' },
    ],
  },
  {
    id: 'bw',
    label: 'Black & white',
    filters: [
      { id: 'mono', label: 'Mono' }, { id: 'noir', label: 'Noir' },
      { id: 'stark', label: 'Stark' }, { id: 'tri-x-400', label: 'Tri-X 400' },
      { id: 'sepia', label: 'Sepia' },
    ],
  },
  {
    id: 'film',
    label: 'Film',
    filters: [
      { id: 'portra-400', label: 'Portra 400' }, { id: 'velvia', label: 'Velvia' },
      { id: 'kodachrome', label: 'Kodachrome' }, { id: 'cinestill-800t', label: 'Cinestill' },
      { id: 'polaroid-600', label: 'Polaroid' },
    ],
  },
  {
    id: 'analog',
    label: 'Analog',
    filters: [
      { id: 'vhs', label: 'VHS', effect: { key: 'vhs', add: 60 } },
      { id: 'glitch', label: 'Glitch', effect: { key: 'glitch', add: 50 } },
      { id: 'halftone', label: 'Halftone', effect: { key: 'halftone', add: 50 } },
      { id: 'fringing', label: 'Fringing', effect: { key: 'chromaticAberration', add: 50 } },
    ],
  },
  {
    id: 'light',
    label: 'Light',
    filters: [
      { id: 'glow', label: 'Glow', effect: { key: 'glow', add: 50 } },
      { id: 'vignette', label: 'Vignette', effect: { key: 'vignette', add: 50 } },
      { id: 'grain', label: 'Grain', effect: { key: 'noise', add: 40 } },
    ],
  },
]

/** Flat, in the order the strip shows them. */
export const FILTER_STRIP = FILTER_CATEGORIES.flatMap(category => category.filters)

export const FILTER_LABELS = new Map(
  FILTER_CATEGORIES.flatMap(category => category.filters.map(f => [f.id, f.label]))
)

export function stripEntryById(id: string): StripEntry | undefined {
  return FILTER_STRIP.find(entry => entry.id === id)
}

/**
 * The pixel-look this step carries, if it is a single-effect step from the
 * strip — what gives its inspector an Amount slider instead of a blob surface.
 */
export function effectLookOf(params: Record<string, any>): StripEntry | undefined {
  return FILTER_STRIP.find(
    entry => entry.effect && params[entry.effect.key] !== undefined
  )
}

/** Groups this op has actually touched — what the row subtitle names. */
export function touchedSections(params: Record<string, any>): string[] {
  const touched = ADJUST_SECTIONS.filter(section => {
    if (section.toggle && params[section.toggle.key]) return true
    return section.controls.some(
      control => params[control.key] !== undefined && params[control.key] !== control.default
    )
  }).map(section => section.label)
  if (params.filter && params.filter !== 'none') {
    touched.unshift(FILTER_LABELS.get(params.filter) ?? 'Filter')
  }
  return touched
}

/**
 * The row's name. An adjustment step is named for what it does, not for the
 * doorway it was opened through — a step with only a filter reads `Filters`,
 * one with sliders reads `Adjust`, one with both names both.
 */
/**
 * The row's name: what this step DOES.
 *
 * Effects name themselves individually — a step is 'Halftone', or
 * 'Halftone · Grain' once there are two — because the effect is the thing the
 * user picked. Adjust controls are a group and read as one, since nobody thinks of
 * 'raised the contrast' as a separate edit from 'raised the exposure' when
 * they moved both in one sitting.
 */
export function adjustLabel(params: Record<string, any>): string {
  const parts: string[] = []
  if (params.filter && params.filter !== 'none') {
    parts.push(FILTER_LABELS.get(params.filter) ?? 'Filter')
  }
  for (const section of ADJUST_SECTIONS) {
    const touched = section.controls.filter(
      control => params[control.key] !== undefined && params[control.key] !== control.default
    )
    const toggled = section.toggle && params[section.toggle.key]
    if (!touched.length && !toggled) continue
    if (section.id === 'effects') parts.push(...touched.map(control => control.label))
    else parts.push(section.label)
  }
  return parts.length ? parts.join(' · ') : 'Adjust'
}

/** Aspect presets for the Crop family, matching the snapshot editor's set. */
/**
 * The snapshot editor's aspect list, kept as it was — `original` reads the
 * source's own ratio rather than naming a number.
 */
export const CROP_ASPECTS: Array<{ id: string; label: string; ratio: number | null }> = [
  { id: 'free', label: 'Free', ratio: null },
  { id: 'original', label: 'Original', ratio: -1 },
  { id: '16:9', label: '16:9', ratio: 16 / 9 },
  { id: '3:2', label: '3:2', ratio: 3 / 2 },
  { id: '4:3', label: '4:3', ratio: 4 / 3 },
  { id: '1:1', label: '1:1', ratio: 1 },
  { id: '3:4', label: '3:4', ratio: 3 / 4 },
  { id: '2:3', label: '2:3', ratio: 2 / 3 },
  { id: '9:16', label: '9:16', ratio: 9 / 16 },
]

/**
 * The crop rect for an aspect ratio: the largest centred window of that shape
 * that fits the frame. Centre-based, like everything else in the crop params.
 */
export function cropRectForAspect(
  ratio: number | null,
  frameWidth: number,
  frameHeight: number
): { x: number; y: number; width: number; height: number } {
  if (!ratio) return { x: 0.5, y: 0.5, width: 1, height: 1 }
  const frameRatio = frameWidth / frameHeight
  const width = ratio > frameRatio ? 1 : ratio / frameRatio
  const height = ratio > frameRatio ? frameRatio / ratio : 1
  return { x: 0.5, y: 0.5, width, height }
}
