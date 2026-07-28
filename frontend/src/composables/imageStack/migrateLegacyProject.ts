/**
 * One-way conversion of a snapshot-editor project into an op stack.
 *
 * The snapshot editor's document is one flat state object: every crop, colour,
 * effect, annotation and retouch field on a single struct, applied in a fixed
 * order at render time. That order is what makes the conversion possible —
 * each stage of the old render becomes one step, bottom to top, so the stack
 * replays the same pipeline and the result is pixel-identical.
 *
 * The original sidecar is never written back. Production still reads it with
 * the snapshot editor, and cross-channel divergence is accepted by design.
 *
 * Undo history does not migrate: it is session state, and the two undo models
 * are not the same thing (full-state snapshots vs a journal of document edits).
 */

import { newOpId } from './opId.ts'
import type { ContainerOp, Op, ParametricOp } from './types.ts'

/** Fields the Adjust op carries, in the order the old writer applied them. */
const DEVELOP_FIELDS = [
  'brightness', 'contrast', 'saturation', 'exposure', 'temperature', 'gamma',
  'filter', 'colorMatrix',
  'splitToningEnabled', 'splitToningShadowHue', 'splitToningShadowSat',
  'splitToningHighlightHue', 'splitToningHighlightSat', 'splitToningBalance',
  'gradientMapEnabled', 'gradientMapShadowColor', 'gradientMapHighlightColor',
  'gradientMapIntensity',
  'colorIsolationEnabled', 'colorIsolationHue', 'colorIsolationRange',
  'colorIsolationFeather',
  'blur', 'sharpen', 'noise', 'glow', 'pixelate', 'chromaticAberration',
  'motionBlur', 'motionBlurAngle', 'vignette', 'clarity',
  'halftone', 'halftoneAngle', 'vhs', 'glitch', 'glitchBlockSize',
  'ditherEnabled', 'ditherPalette',
] as const

const DEVELOP_DEFAULTS: Record<string, any> = {
  brightness: 0, contrast: 0, saturation: 0, exposure: 0, temperature: 0, gamma: 1,
  filter: null, colorMatrix: null,
  splitToningEnabled: false, gradientMapEnabled: false, colorIsolationEnabled: false,
  blur: 0, sharpen: 0, noise: 0, glow: 0, pixelate: 0, chromaticAberration: 0,
  motionBlur: 0, motionBlurAngle: 0, vignette: 0, clarity: 0,
  halftone: 0, halftoneAngle: 0, vhs: 0, glitch: 0, glitchBlockSize: 16,
  ditherEnabled: false, ditherPalette: 'none',
}

/** Sections the row subtitle names, so "Adjust" says what it touched. */
const ADJUST_SECTIONS: Array<{ label: string; fields: string[] }> = [
  { label: 'Light', fields: ['brightness', 'contrast', 'exposure', 'gamma'] },
  { label: 'Colour', fields: ['saturation', 'temperature', 'filter', 'colorMatrix'] },
  { label: 'Film', fields: ['splitToningEnabled', 'gradientMapEnabled', 'colorIsolationEnabled'] },
  {
    label: 'Effects',
    fields: [
      'blur', 'sharpen', 'noise', 'glow', 'pixelate', 'chromaticAberration',
      'motionBlur', 'vignette', 'clarity', 'halftone', 'vhs', 'glitch', 'ditherEnabled',
    ],
  },
]

function isDefault(field: string, value: any): boolean {
  const fallback = DEVELOP_DEFAULTS[field]
  if (fallback === undefined) return value === undefined || value === null
  if (Array.isArray(fallback) || Array.isArray(value)) {
    return JSON.stringify(value ?? null) === JSON.stringify(fallback ?? null)
  }
  return (value ?? fallback) === fallback
}

function isIdentityCrop(state: any): boolean {
  // crop.x/y are the crop's CENTRE, so an untouched crop sits at 0.5, 0.5.
  const crop = state?.crop
  const untouchedRect =
    !crop ||
    (Math.abs((crop.x ?? 0.5) - 0.5) < 1e-6 && Math.abs((crop.y ?? 0.5) - 0.5) < 1e-6 &&
     Math.abs((crop.width ?? 1) - 1) < 1e-6 && Math.abs((crop.height ?? 1) - 1) < 1e-6)
  return (
    untouchedRect &&
    !state?.rotation && !state?.rotation90 && !state?.flipX && !state?.flipY
  )
}

export interface MigrationResult {
  ops: Op[]
  /** Raster layers that must be uploaded as payloads before the ops are usable. */
  rasters: Array<{ opId: string; dataUrl: string; name: string }>
  /** What was dropped, so the migration can say so rather than pretend. */
  dropped: string[]
}

/**
 * Convert a `SerializedProject` into ops, bottom to top.
 *
 * Order matches the old render: geometry first, then the retouch raster (which
 * the old writer drew under the colour work), then the adjustment family, then
 * annotations on top.
 */
export function migrateLegacyProject(project: any): MigrationResult {
  const state = project?.state ?? project
  const ops: Op[] = []
  const rasters: MigrationResult['rasters'] = []
  const dropped: string[] = []

  if (!state || typeof state !== 'object') {
    return { ops, rasters, dropped: ['The saved project could not be read.'] }
  }

  // 1. Geometry.
  if (!isIdentityCrop(state)) {
    const op: ParametricOp = {
      id: newOpId(),
      class: 'parametric',
      enabled: true,
      label: 'Crop',
      exec: { kind: 'crop' },
      params: {
        // Copied verbatim: the op keeps the snapshot editor's centre-based
        // convention so no coordinate conversion sits between the two.
        rect: {
          x: state.crop?.x ?? 0.5,
          y: state.crop?.y ?? 0.5,
          width: state.crop?.width ?? 1,
          height: state.crop?.height ?? 1,
        },
        rotation: state.rotation ?? 0,
        rotation90: state.rotation90 ?? 0,
        flipX: !!state.flipX,
        flipY: !!state.flipY,
      },
    }
    ops.push(op)
  }

  // 2. Retouch raster → a Paint layer. Strokes are not replayable, so the
  //    baked layer is imported as-is and further painting adds to it.
  const retouch = state.retouchLayerData
  if (typeof retouch === 'string' && retouch.startsWith('data:')) {
    const opId = newOpId()
    const op: ContainerOp = {
      id: opId,
      class: 'container',
      enabled: true,
      label: 'Paint',
      exec: { kind: 'paint' },
      raster_ref: `payloads/${opId}-layer.png`,
      blend: { feather_px: 0, opacity: 1 },
    }
    ops.push(op)
    rasters.push({ opId, dataUrl: retouch, name: `${opId}-layer.png` })
  } else if (retouch) {
    dropped.push('The retouch layer could not be read and was not imported.')
  }

  // 3. Every touched adjustment, as ONE Adjust step — the user-facing unit is
  //    a adjust session, not a slider.
  const adjustParams: Record<string, any> = {}
  for (const field of DEVELOP_FIELDS) {
    const value = (state as any)[field]
    if (!isDefault(field, value)) adjustParams[field] = value
  }
  if (Object.keys(adjustParams).length > 0) {
    const sections = ADJUST_SECTIONS
      .filter(section => section.fields.some(f => f in adjustParams))
      .map(section => section.label)
    ops.push({
      id: newOpId(),
      class: 'parametric',
      enabled: true,
      label: sections.length ? `Adjust — ${sections.join(' · ')}` : 'Adjust',
      exec: { kind: 'adjust' },
      params: adjustParams,
    } as ParametricOp)
  }

  // 4. Annotations, decorations, redactions and stickers all render through the
  //    same shape pipeline, so they become one vector Annotate step in the same
  //    draw order the old writer used.
  const shapes = [
    ...(state.annotations || []),
    ...(state.decorations || []),
    ...(state.redactions || []),
    ...(state.stickers || []),
  ]
  if (shapes.length) {
    ops.push({
      id: newOpId(),
      class: 'container',
      enabled: true,
      label: 'Annotate',
      exec: { kind: 'annotate' },
      params: { shapes },
    } as ContainerOp)
  }

  // Things the stack has no equivalent for. Named rather than silently lost.
  if (state.frame && state.frame.type && state.frame.type !== 'none') {
    dropped.push('The frame was not imported — frames are not a stack step.')
  }
  if (state.backgroundImage || state.backgroundColor) {
    dropped.push('The background was not imported.')
  }
  if (state.targetSize) {
    dropped.push('The export size was not imported.')
  }

  return { ops, rasters, dropped }
}
