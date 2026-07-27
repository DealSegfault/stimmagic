/**
 * The Develop family's control surface.
 *
 * Develop is the single home for the whole parametric adjustment family —
 * finetune, grade, filters, effects. One Develop *step* holds every section the
 * user touched, because the user-facing unit is a develop session, not a
 * slider; the row subtitle names the sections rather than the fields.
 *
 * The sub-toolbar shows one primary control per section; the rest live in the
 * selected row's inspector. Nobody gets forty knobs in a 42px row, and nobody
 * loses them either.
 */

export interface DevelopControl {
  key: string
  label: string
  min: number
  max: number
  step: number
  default: number
  /** Shown inline in the sub-toolbar rather than only in the inspector. */
  primary?: boolean
}

export interface DevelopSection {
  id: string
  label: string
  controls: DevelopControl[]
  /** Fields that switch the section on; absent means the sliders speak for it. */
  toggle?: { key: string; label: string }
}

/** Ranges mirror the snapshot editor's, so a migrated value lands where it was. */
export const DEVELOP_SECTIONS: DevelopSection[] = [
  {
    id: 'light',
    label: 'Light',
    controls: [
      { key: 'exposure', label: 'Exposure', min: -100, max: 100, step: 1, default: 0, primary: true },
      { key: 'brightness', label: 'Brightness', min: -100, max: 100, step: 1, default: 0 },
      { key: 'contrast', label: 'Contrast', min: -100, max: 100, step: 1, default: 0 },
      { key: 'gamma', label: 'Gamma', min: 0.1, max: 3, step: 0.05, default: 1 },
    ],
  },
  {
    id: 'colour',
    label: 'Colour',
    controls: [
      { key: 'saturation', label: 'Saturation', min: -100, max: 100, step: 1, default: 0, primary: true },
      { key: 'temperature', label: 'Temperature', min: -100, max: 100, step: 1, default: 0 },
    ],
  },
  {
    id: 'film',
    label: 'Film',
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
  DEVELOP_SECTIONS.flatMap(section => section.controls.map(control => [control.key, control]))
)

export function developControl(key: string): DevelopControl | undefined {
  return CONTROLS_BY_KEY.get(key)
}

/** Sections this op has actually touched — what the row subtitle names. */
export function touchedSections(params: Record<string, any>): string[] {
  return DEVELOP_SECTIONS.filter(section => {
    if (section.toggle && params[section.toggle.key]) return true
    return section.controls.some(
      control => params[control.key] !== undefined && params[control.key] !== control.default
    )
  }).map(section => section.label)
}

export function developLabel(params: Record<string, any>): string {
  const sections = touchedSections(params)
  return sections.length ? `Develop — ${sections.join(' · ')}` : 'Develop'
}

/** Aspect presets for the Crop family, matching the snapshot editor's set. */
export const CROP_ASPECTS: Array<{ id: string; label: string; ratio: number | null }> = [
  { id: 'free', label: 'Free', ratio: null },
  { id: '1:1', label: '1:1', ratio: 1 },
  { id: '4:5', label: '4:5', ratio: 4 / 5 },
  { id: '3:2', label: '3:2', ratio: 3 / 2 },
  { id: '16:9', label: '16:9', ratio: 16 / 9 },
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
