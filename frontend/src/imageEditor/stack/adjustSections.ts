/**
 * The control surface for Adjust, the one parametric adjustment family.
 *
 * One rule everywhere: the sub-toolbar offers what you can ADD, clicking it
 * creates a focused step, and the step's controls live in its Properties. The
 * bar offers the Autos, the eight adjustment groups (Light, Color, Detail,
 * Mixer, Point color, Grading, Effects, Stylize) and the Looks strip.
 *
 * Filters used to be a second top-level family, which was always a fiction:
 * its steps executed as the same `adjust` op through the same pipeline. What
 * it really held was two unlike things wearing one costume — picked-by-eye
 * LOOKS, and single-param effect dials that had no business being tiles. They
 * are separated here: the dials became the Effects and Stylize groups, and the
 * looks became parameter bundles. Both are now selection-aware, because both
 * are ordinary Adjust edits.
 */

import type { IconName } from '../ported/icons'
import { FILTER_PRESET_LABELS } from '../ported/filterMatrices.ts'
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
  /**
   * This control has no GPU drag preview: it renders when the drag COMMITS.
   *
   * The shader mirrors the photographic pipeline, not the effects one, so the
   * synthetic looks (vignette, glow, halftone, VHS, glitch, fringing) can only
   * appear on release. Declaring it here rather than leaving it implicit is
   * what lets the parity test hold both directions — an unflagged control must
   * reach the preview, and a flagged one must not, so adding shader support
   * forces the flag off instead of letting the list rot.
   */
  commitOnly?: true
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
  | 'effects' | 'stylize'

export type PhotoAdjustmentSection =
  | 'tone' | 'tint' | 'detail'
  | 'mixer' | 'point' | 'grade'
  | 'effects' | 'stylize'

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
  /**
   * This group ADDS something to the picture rather than correcting what is
   * there. The Adjust bar keeps the two apart with a separator: the
   * photographic groups are what a photographer reaches for, and the creative
   * ones are the same neighbourhood as the Looks strip.
   */
  creative?: true
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
      { key: 'vibrance', label: 'Vibrance', min: -100, max: 100, step: 1, default: 0 },
      { key: 'saturation', label: 'Saturation', min: -100, max: 100, step: 1, default: 0 },
      // Tinting the whole frame one hue is a color edit, so it belongs to the
      // Color group rather than to a strip tile of its own. Hue reads as dead
      // weight until Colorize is up, which is why Amount leads.
      { key: 'colorizeAmount', label: 'Colorize', min: 0, max: 100, step: 1, default: 0 },
      { key: 'colorizeHue', label: 'Colorize hue', min: 0, max: 360, step: 1, default: 0 },
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
      { key: 'defringe', label: 'Defringe', min: 0, max: 100, step: 1, default: 0 },
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
  /**
   * Photographic finishing. These were filter-strip tiles, which is what made
   * them unreachable from a selection: the strip never consulted one, and the
   * step it made carried no `section`, so the inspector's "Limit to selection"
   * could not appear either. As a group they are ordinary Adjust edits.
   *
   * Vignette and Glow are FRAME-relative — scoped to a selection they still
   * darken (or bloom) from the frame's edges and merely show through the mask.
   * Blur and Grain are local and behave as drawn.
   */
  {
    id: 'effects',
    section: 'effects',
    label: 'Effects',
    icon: 'effects',
    creative: true,
    controls: [
      { key: 'vignette', label: 'Vignette', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
      { key: 'glow', label: 'Glow', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
      { key: 'blur', label: 'Blur', min: 0, max: 40, step: 1, default: 0 },
      { key: 'noise', label: 'Grain', min: 0, max: 100, step: 1, default: 0 },
      { key: 'grainSize', label: 'Grain size', min: 0, max: 100, step: 1, default: 0 },
      { key: 'grainRoughness', label: 'Grain roughness', min: 0, max: 100, step: 1, default: 50 },
    ],
  },
  /**
   * The deliberately synthetic looks — same machinery as Effects, kept as
   * their own group so a film emulation never sits beside a glitch dial again.
   * Halftone and Glitch carry a second dial each: the thing you reach for once
   * the effect is up is its scale, not its strength.
   */
  {
    id: 'stylize',
    section: 'stylize',
    label: 'Stylize',
    icon: 'stylize',
    creative: true,
    controls: [
      { key: 'halftone', label: 'Halftone', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
      { key: 'halftoneAngle', label: 'Halftone angle', min: 0, max: 180, step: 1, default: 0, commitOnly: true },
      { key: 'vhs', label: 'VHS', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
      { key: 'glitch', label: 'Glitch', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
      { key: 'glitchBlockSize', label: 'Glitch block', min: 4, max: 64, step: 1, default: 16, commitOnly: true },
      // Adds fringing; Detail's `defringe` removes it. Two dials, opposite jobs.
      { key: 'chromaticAberration', label: 'Fringing', min: 0, max: 100, step: 1, default: 0, commitOnly: true },
    ],
  },
]

export function photoAdjustmentGroup(id: string): PhotoAdjustmentGroup | undefined {
  return PHOTO_ADJUSTMENT_GROUPS.find(group => group.id === id || group.section === id)
}

/**
 * Brightness and gamma exist ONLY on migrated snapshot-editor blob steps (the
 * ADJUST_SECTIONS surface); no group offers them. They stay in the projection
 * because blob steps render and GPU-preview through it like everything else.
 */
const LEGACY_BLOB_CONTROLS: AdjustSliderControl[] = [
  { key: 'brightness', label: 'Brightness', min: -100, max: 100, step: 1, default: 0 },
  { key: 'gamma', label: 'Gamma', min: 0.1, max: 3, step: 0.05, default: 1 },
]

export const PHOTO_ADJUSTMENT_CONTROLS = [
  ...PHOTO_ADJUSTMENT_GROUPS.flatMap(group => group.controls),
  ...LEGACY_BLOB_CONTROLS,
]

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

/** Group dials first, so a legacy section's own definition wins on clash. */
const CONTROLS_BY_KEY = new Map([
  ...PHOTO_ADJUSTMENT_GROUPS.flatMap(
    group => group.controls
      .filter(isAdjustSlider)
      .map(control => [control.key, control] as [string, AdjustSliderControl])
  ),
  ...ADJUST_SECTIONS.flatMap(
    section => section.controls.map(
      control => [control.key, control] as [string, AdjustSliderControl]
    )
  ),
])

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
  /** Adds rather than corrects; the bar separates these. */
  creative?: true
  /** Params set at creation, beyond the marker — what makes the edit DO its thing. */
  seed?: Record<string, any>
}

export const LEVEL_EDITS: LevelEdit[] = PHOTO_ADJUSTMENT_GROUPS.map(group => ({
  id: group.section,
  label: group.label,
  icon: group.icon,
  controls: group.controls,
  presentation: group.presentation,
  creative: group.creative,
}))

/** The two runs the Adjust bar shows either side of a separator. */
export const PHOTOGRAPHIC_LEVEL_EDITS = LEVEL_EDITS.filter(edit => !edit.creative)
export const CREATIVE_LEVEL_EDITS = LEVEL_EDITS.filter(edit => edit.creative)

export function levelEditById(id: string): LevelEdit | undefined {
  return LEVEL_EDITS.find(edit => edit.id === id)
}

/**
 * The Autos, as addable edits: each computes slider values from the histogram
 * and lands as a normal Light step seeded with them — inspectable, adjustable
 * and deletable like anything else, not a fire-and-forget action.
 */
export const AUTO_EDITS: Array<{
  id: 'levels' | 'contrast' | 'balance'
  label: string
  icon: IconName
}> = [
  // They sit together behind one Auto chip, so each needs a glyph that says
  // which one it is: what it reads (the histogram), what it moves (contrast),
  // what it corrects (temperature). One shared wand made the list unreadable.
  { id: 'levels', label: 'Auto levels', icon: 'histogram' },
  { id: 'contrast', label: 'Auto contrast', icon: 'contrast' },
  { id: 'balance', label: 'Auto balance', icon: 'thermometer' },
]

/**
 * The Looks strip: starting points, expressed in the editor's own vocabulary.
 *
 * A look is a BUNDLE of ordinary adjustment params, not a private color
 * matrix. Everything follows from that: it scopes to a selection like any
 * other Adjust edit, its step stays editable afterwards on the real dials, and
 * the numbers can be read and argued with instead of being twenty opaque
 * matrix coefficients. The legacy matrices survive in `filterMatrices.ts` for
 * documents that already carry a `filter` param; nothing new writes one.
 *
 * There is deliberately no Amount slider. A look is where you START, and the
 * way to get less of it is to move the dials it set — which is the whole point
 * of authoring them in the real schema.
 *
 * No `None` entry: the strip is not a picker, it ADDS. Removing a look is the
 * Edits list's job (or clicking the applied tile again).
 */
export interface Look {
  id: string
  label: string
  /** Adjustment keys, exactly as a step or a region's settings carry them. */
  params: Record<string, number>
}

export const LOOK_CATEGORIES: Array<{ id: string; label: string; looks: Look[] }> = [
  {
    id: 'color',
    label: 'Color',
    looks: [
      {
        id: 'chrome',
        label: 'Chrome',
        params: { contrast: 18, vibrance: 22, whites: 8, blacks: -12, clarity: 10 },
      },
      {
        id: 'vivid',
        label: 'Vivid',
        params: { saturation: 30, vibrance: 15, contrast: 10 },
      },
      {
        id: 'dramatic',
        label: 'Dramatic',
        // Deep, not clipped. Contrast alone is a straight gain about mid-grey
        // with no shoulder, so it clips the ends on its own; the shadow dials
        // are kept light enough that the tonal ramp stays close to the matrix
        // this look replaces instead of flattening the low end to black.
        params: {
          saturation: 22, contrast: 18, shadows: -6, blacks: -4, clarity: 20,
        },
      },
      {
        id: 'cold',
        label: 'Cold',
        params: {
          temperature: -28, tint: -6, vibrance: 8,
          gradeShadowHue: 210, gradeShadowSat: 18,
        },
      },
      {
        id: 'warm',
        label: 'Warm',
        params: {
          temperature: 28, tint: 6, vibrance: 8,
          gradeHighlightHue: 40, gradeHighlightSat: 15,
        },
      },
      {
        id: 'pastel',
        label: 'Pastel',
        params: {
          exposure: 12, contrast: -18, highlights: -10, blacks: 22,
          saturation: -12, clarity: -12,
        },
      },
      {
        id: 'fade',
        label: 'Fade',
        params: {
          blacks: 32, contrast: -22, highlights: -8, saturation: -18,
          gradeShadowHue: 200, gradeShadowSat: 12,
        },
      },
      {
        id: 'vintage',
        label: 'Vintage',
        params: {
          blacks: 25, contrast: -12, saturation: -20, temperature: 15,
          gradeShadowHue: 60, gradeShadowSat: 20,
          gradeHighlightHue: 35, gradeHighlightSat: 15,
        },
      },
    ],
  },
  {
    id: 'bw',
    label: 'Black & white',
    // Saturation -100 is a true BT.709 luminance conversion, and it runs in
    // the matrix pass ahead of the photographic one — so Sepia's colorize
    // tints a grey frame rather than fighting the original hues.
    looks: [
      { id: 'mono', label: 'Mono', params: { saturation: -100 } },
      {
        id: 'noir',
        label: 'Noir',
        // Low-key: the highlights come DOWN as well as the shadows, which is
        // what separates noir from plain high-contrast black and white.
        params: {
          saturation: -100, contrast: 18, highlights: -10, shadows: -6,
          blacks: -6, clarity: 15,
        },
      },
      {
        id: 'stark',
        label: 'Stark',
        // The extreme of the three, and meant to be: blown highlights and a
        // lifted midtone, close to the matrix it replaces.
        params: {
          saturation: -100, contrast: 45, exposure: 6, whites: 25, blacks: -20,
          clarity: 25,
        },
      },
      {
        id: 'tri-x-400',
        label: 'Tri-X 400',
        // The one thing a Tri-X frame actually has that a grey-mix does not.
        params: {
          saturation: -100, contrast: 20, shadows: 8, blacks: -10,
          noise: 22, grainSize: 45, grainRoughness: 60,
        },
      },
      {
        id: 'sepia',
        label: 'Sepia',
        params: {
          saturation: -100, contrast: 8, colorizeHue: 32, colorizeAmount: 55,
        },
      },
    ],
  },
  {
    id: 'film',
    label: 'Film',
    // Emulations, not measurements: each is the stock's reputation written as
    // dials — the matrices they replace were no more faithful and could not be
    // edited afterwards.
    looks: [
      {
        id: 'portra-400',
        label: 'Portra 400',
        params: {
          temperature: 12, tint: 4, contrast: -8, highlights: -12, blacks: 18,
          vibrance: -8, saturation: -5,
          [mixerKey('Sat', 'Green')]: -25, [mixerKey('Sat', 'Yellow')]: -12,
          [mixerKey('Hue', 'Orange')]: 6,
          gradeShadowHue: 200, gradeShadowSat: 8,
          gradeHighlightHue: 40, gradeHighlightSat: 12,
        },
      },
      {
        id: 'velvia',
        label: 'Velvia',
        params: {
          saturation: 25, vibrance: 15, contrast: 22, shadows: -12, blacks: -20,
          clarity: 12,
          [mixerKey('Sat', 'Green')]: 20, [mixerKey('Sat', 'Blue')]: 25,
          [mixerKey('Lum', 'Blue')]: -10,
        },
      },
      {
        id: 'kodachrome',
        label: 'Kodachrome',
        params: {
          contrast: 18, saturation: 10, blacks: -12,
          [mixerKey('Sat', 'Red')]: 25, [mixerKey('Sat', 'Orange')]: 15,
          [mixerKey('Hue', 'Red')]: -5, [mixerKey('Sat', 'Blue')]: 10,
          gradeShadowHue: 195, gradeShadowSat: 18,
          gradeHighlightHue: 45, gradeHighlightSat: 12,
        },
      },
      {
        id: 'cinestill-800t',
        label: 'Cinestill',
        // Tungsten balance plus the halation the stock is bought for.
        params: {
          temperature: -22, tint: 6, blacks: 12, saturation: 5, glow: 25,
          gradeShadowHue: 25, gradeShadowSat: 15,
          gradeHighlightHue: 185, gradeHighlightSat: 20,
        },
      },
      {
        id: 'polaroid-600',
        label: 'Polaroid',
        params: {
          exposure: 6, contrast: -20, highlights: -10, blacks: 30,
          saturation: -12,
          gradeShadowHue: 190, gradeShadowSat: 18,
          gradeHighlightHue: 55, gradeHighlightSat: 18,
        },
      },
    ],
  },
]

/** Flat, in the order the strip shows them. */
export const LOOKS = LOOK_CATEGORIES.flatMap(category => category.looks)

export function lookById(id: string): Look | undefined {
  return LOOKS.find(look => look.id === id)
}

/** The groups a look (or any params object) actually moves off default. */
export function touchedGroups(
  values: Record<string, any> | null | undefined,
): PhotoAdjustmentGroup[] {
  if (!values) return []
  return PHOTO_ADJUSTMENT_GROUPS.filter(group => group.controls.some(control => {
    const value = values[control.key]
    if (value === undefined) return false
    if (control.kind === 'curve') {
      return JSON.stringify(value) !== JSON.stringify(control.default)
    }
    return value !== control.default
  }))
}

/**
 * Read compatibility only: the strip's old single-effect tiles.
 *
 * Those params are group sliders now, so nothing new writes a step shaped like
 * this. A document that already holds one keeps its Amount-and-supporting
 * inspector rather than falling through to the legacy everything-surface.
 */
export interface LegacyEffectLook {
  id: string
  label: string
  effect: { key: string }
  supporting?: AdjustSliderControl[]
  seedKeys?: string[]
}

const GRAIN_SUPPORTING: AdjustSliderControl[] = [
  { key: 'grainSize', label: 'Size', min: 0, max: 100, step: 1, default: 0 },
  { key: 'grainRoughness', label: 'Roughness', min: 0, max: 100, step: 1, default: 50 },
]

const LEGACY_EFFECT_LOOKS: LegacyEffectLook[] = [
  {
    id: 'colorize',
    label: 'Colorize',
    effect: { key: 'colorizeAmount' },
    supporting: [{ key: 'colorizeHue', label: 'Hue', min: 0, max: 360, step: 1, default: 0 }],
    seedKeys: ['colorizeHue'],
  },
  { id: 'vhs', label: 'VHS', effect: { key: 'vhs' } },
  { id: 'glitch', label: 'Glitch', effect: { key: 'glitch' } },
  { id: 'halftone', label: 'Halftone', effect: { key: 'halftone' } },
  { id: 'fringing', label: 'Fringing', effect: { key: 'chromaticAberration' } },
  { id: 'glow', label: 'Glow', effect: { key: 'glow' } },
  { id: 'vignette', label: 'Vignette', effect: { key: 'vignette' } },
  { id: 'grain', label: 'Grain', effect: { key: 'noise' }, supporting: GRAIN_SUPPORTING },
  { id: 'blur', label: 'Blur', effect: { key: 'blur' } },
]

export function effectLookOf(params: Record<string, any>): LegacyEffectLook | undefined {
  return LEGACY_EFFECT_LOOKS.find(entry => params[entry.effect.key] !== undefined)
}

/**
 * The legacy strip look this step IS: its effect key is present and it carries
 * nothing beyond that look's own surface. A migrated blob that happens to
 * include the key carries other params too and must never match.
 */
export function effectLookStepOf(params: Record<string, any>): LegacyEffectLook | undefined {
  const look = effectLookOf(params)
  if (!look) return undefined
  const allowed = new Set([
    look.effect.key,
    ...(look.supporting ?? []).map(control => control.key),
    ...(look.seedKeys ?? []),
  ])
  return Object.keys(params).every(key => allowed.has(key)) ? look : undefined
}

/** Names for the `filter` presets, for documents that still carry one. */
export const LEGACY_FILTER_LABELS = new Map(
  FILTER_PRESET_LABELS.map(preset => [preset.id, preset.label]),
)

/** Groups this op has actually touched — what the row subtitle names. */
export function touchedSections(params: Record<string, any>): string[] {
  const touched = ADJUST_SECTIONS.filter(section => {
    if (section.toggle && params[section.toggle.key]) return true
    return section.controls.some(
      control => params[control.key] !== undefined && params[control.key] !== control.default
    )
  }).map(section => section.label)
  if (params.filter && params.filter !== 'none') {
    touched.unshift(LEGACY_FILTER_LABELS.get(params.filter) ?? 'Filter')
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
    parts.push(LEGACY_FILTER_LABELS.get(params.filter) ?? 'Filter')
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
