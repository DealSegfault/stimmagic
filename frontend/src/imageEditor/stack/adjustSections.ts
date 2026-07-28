/**
 * The control surface for the parametric adjustment families: Levels, Filters
 * and Effects — the snapshot editor's own names, kept.
 *
 * They share one op kind because the pixel pipeline is one pipeline and its
 * order is fixed (base adjustments, then filter, then split tone, then
 * effects); splitting it into three ops would let the user reorder it into an
 * order the maths does not have. What the three families give is three
 * doorways into it, and the row is labelled by whichever groups were touched.
 *
 * The sub-toolbar shows one primary control per group; the rest live in the
 * selected row's inspector. Nobody gets forty knobs in a 42px row, and nobody
 * loses them either.
 */

/** Which family a group belongs to — the doorway that shows it. */
export type AdjustFamily = 'levels' | 'filters' | 'effects'

export interface AdjustControl {
  key: string
  label: string
  min: number
  max: number
  step: number
  default: number
  /** Shown inline in the sub-toolbar rather than only in the inspector. */
  primary?: boolean
}

export interface AdjustSection {
  family: AdjustFamily
  id: string
  label: string
  controls: AdjustControl[]
  /** Fields that switch the section on; absent means the sliders speak for it. */
  toggle?: { key: string; label: string }
}

/** Ranges mirror the snapshot editor's, so a migrated value lands where it was. */
export const ADJUST_SECTIONS: AdjustSection[] = [
  {
    family: 'levels',
    id: 'levels',
    label: 'Levels',
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
    family: 'levels',
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
    family: 'effects',
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

export function adjustControl(key: string): AdjustControl | undefined {
  return CONTROLS_BY_KEY.get(key)
}

export function sectionsForFamily(family: AdjustFamily): AdjustSection[] {
  return ADJUST_SECTIONS.filter(section => section.family === family)
}

/**
 * The snapshot editor's filter presets, by category, so the grid reads the way
 * its Filters panel did.
 */
export const FILTER_CATEGORIES: Array<{ id: string; label: string; filters: Array<{ id: string; label: string }> }> = [
  { id: 'none', label: '', filters: [{ id: 'none', label: 'None' }] },
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
]

/** Flat, in the order the strip shows them. */
export const FILTER_STRIP = FILTER_CATEGORIES.flatMap(category => category.filters)

export const FILTER_LABELS = new Map(
  FILTER_CATEGORIES.flatMap(category => category.filters.map(f => [f.id, f.label]))
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
    touched.unshift(FILTER_LABELS.get(params.filter) ?? 'Filter')
  }
  return touched
}

/**
 * The row's name. An adjustment step is named for what it does, not for the
 * doorway it was opened through — a step with only a filter reads `Filters`,
 * one with sliders reads `Levels`, one with both names both.
 */
export function adjustLabel(params: Record<string, any>): string {
  const sections = touchedSections(params)
  if (!sections.length) return 'Adjust'
  return sections.join(' · ')
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
