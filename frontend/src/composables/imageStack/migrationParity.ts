/**
 * Golden parity harness for the snapshot-editor migration.
 *
 * Renders one legacy state through BOTH pipelines — the snapshot editor's own
 * writer, and the migrated op stack — and reports how far apart they are. The
 * canary flip depends on this: unit tests prove the field mapping, but only
 * rendering both proves the result, because the risk is order and inclusion (a
 * stage applied in the wrong place, or quietly left out), not the colour math,
 * which both paths share by construction.
 *
 * Lives in src/ rather than in the test so the spec and any ad-hoc runner
 * exercise the same code. Browser-only: it needs a real Canvas 2D.
 */

import { useImageWriter } from '@stimma/image-editor'
import { applyAnnotations, applyCrop, applyDevelop } from './opExecutors'
import { migrateLegacyProject } from './migrateLegacyProject'

export interface ParityReport {
  /** Largest per-channel difference across the frame. */
  maxDelta: number
  /** Percentage of pixels differing by more than a rounding step. */
  overPct: number
  opKinds: string[]
  /** Set when the migrated output is not even the same size. */
  dimsMismatch?: [number, number, number, number]
  /** Both renders, when asked for — a failing parity check should be lookable-at. */
  images?: { source: string; legacy: string; migrated: string }
}

/** Every field the snapshot editor's writer reads, at its default. */
export function defaultLegacyState(width: number, height: number): Record<string, any> {
  return {
    src: null,
    imageSize: { width, height },
    crop: { x: 0.5, y: 0.5, width: 1, height: 1 },
    rotation: 0, rotation90: 0, flipX: false, flipY: false,
    brightness: 0, contrast: 0, saturation: 0, exposure: 0, temperature: 0, gamma: 1,
    filter: null, colorMatrix: null,
    splitToningEnabled: false, gradientMapEnabled: false, colorIsolationEnabled: false,
    blur: 0, sharpen: 0, noise: 0, glow: 0, pixelate: 0, chromaticAberration: 0,
    motionBlur: 0, motionBlurAngle: 0, vignette: 0, clarity: 0,
    halftone: 0, halftoneAngle: 0, vhs: 0, glitch: 0, glitchBlockSize: 16,
    ditherEnabled: false, ditherPalette: 'none',
    annotations: [], decorations: [], redactions: [], stickers: [],
    retouchLayerData: null, frame: null, backgroundColor: null,
    backgroundImage: null, targetSize: null,
  }
}

/**
 * A deterministic, detail-dense source: colour ramps across all three channels
 * plus fine lines, so a missing or misordered stage shows up instead of hiding
 * in a flat field.
 */
export function parityFixture(width = 256, height = 192): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')!
  const data = ctx.createImageData(width, height)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      data.data[i] = (x * 255) / width
      data.data[i + 1] = (y * 255) / height
      data.data[i + 2] = ((x + y) * 255) / (width + height)
      data.data[i + 3] = 255
    }
  }
  ctx.putImageData(data, 0, 0)
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1
  for (let x = 0; x < width; x += 16) {
    ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, height); ctx.stroke()
  }
  for (let y = 0; y < height; y += 16) {
    ctx.beginPath(); ctx.moveTo(0, y + 0.5); ctx.lineTo(width, y + 0.5); ctx.stroke()
  }
  return canvas
}

function canvasFrom(image: HTMLImageElement): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  canvas.getContext('2d')!.drawImage(image, 0, 0)
  return canvas
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('parity fixture failed to decode'))
    image.src = src
  })
}

/** Replay a migrated stack over the fixture, executor by executor. */
function replayStack(source: HTMLCanvasElement, ops: any[]): HTMLCanvasElement {
  let current = source
  for (const op of ops) {
    const kind = op.exec?.kind
    if (kind === 'crop') {
      current = applyCrop(current, current.width, current.height, op.params)
    } else if (kind === 'develop') {
      current = applyDevelop(current, current.width, current.height, op.params)
    } else if (kind === 'annotate') {
      current = applyAnnotations(current, current.width, current.height, op.params.shapes, current)
    }
  }
  return current
}

export async function compareMigrationParity(
  familyState: Record<string, any>,
  size: { width: number; height: number } = { width: 256, height: 192 },
  options: { includeImages?: boolean } = {}
): Promise<ParityReport> {
  const source = parityFixture(size.width, size.height)
  const image = await loadImage(source.toDataURL())
  const state = { ...defaultLegacyState(size.width, size.height), ...familyState }

  const writer = useImageWriter()
  // The writer returns { dest: Blob, imageSize }.
  const legacy = await writer.process(state as any, image, { format: 'image/png' } as any)
  const legacyUrl = URL.createObjectURL(legacy.dest)
  const legacyImage = await loadImage(legacyUrl)
  URL.revokeObjectURL(legacyUrl)

  const { ops } = migrateLegacyProject({ state })
  const migrated = replayStack(source, ops)
  const opKinds = ops.map((op: any) => op.exec.kind)

  const images = options.includeImages
    ? {
        source: source.toDataURL(),
        legacy: canvasFrom(legacyImage).toDataURL(),
        migrated: migrated.toDataURL(),
      }
    : undefined

  if (
    migrated.width !== legacyImage.naturalWidth ||
    migrated.height !== legacyImage.naturalHeight
  ) {
    return {
      maxDelta: 255,
      overPct: 100,
      opKinds,
      images,
      dimsMismatch: [
        migrated.width, migrated.height,
        legacyImage.naturalWidth, legacyImage.naturalHeight,
      ],
    }
  }

  const reference = document.createElement('canvas')
  reference.width = migrated.width
  reference.height = migrated.height
  reference.getContext('2d')!.drawImage(legacyImage, 0, 0)

  const a = reference.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, reference.width, reference.height).data
  const b = migrated.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, migrated.width, migrated.height).data

  let maxDelta = 0
  let over = 0
  for (let i = 0; i < a.length; i += 4) {
    let pixelOver = false
    for (let c = 0; c < 3; c++) {
      const delta = Math.abs(a[i + c] - b[i + c])
      if (delta > maxDelta) maxDelta = delta
      if (delta > 2) pixelOver = true
    }
    if (pixelOver) over++
  }

  return { maxDelta, overPct: (over / (a.length / 4)) * 100, opKinds, images }
}

/**
 * The field families from the migration mapping table, each exercised alone so
 * a failure names which family broke, plus one combined case.
 */
export const PARITY_FAMILIES: Array<{ name: string; state: Record<string, any> }> = [
  { name: 'light', state: { brightness: 25, contrast: 15, exposure: -10, gamma: 1.2 } },
  { name: 'colour', state: { saturation: -30, temperature: 20 } },
  { name: 'filter-preset', state: { filter: 'vintage' } },
  { name: 'effects-tonal', state: { vignette: 45, clarity: 30 } },
  { name: 'effects-spatial', state: { blur: 4, sharpen: 20 } },
  {
    name: 'film-split-tone',
    state: {
      splitToningEnabled: true, splitToningShadowHue: 210, splitToningShadowSat: 40,
      splitToningHighlightHue: 40, splitToningHighlightSat: 30, splitToningBalance: 10,
    },
  },
  {
    name: 'film-colour-isolation',
    state: {
      colorIsolationEnabled: true, colorIsolationHue: 10,
      colorIsolationRange: 30, colorIsolationFeather: 20,
    },
  },
  { name: 'geometry-crop', state: { crop: { x: 0.45, y: 0.55, width: 0.7, height: 0.75 } } },
  { name: 'geometry-flip', state: { flipX: true } },
  { name: 'geometry-quarter-turn', state: { rotation90: 1 } },
  { name: 'geometry-straighten', state: { rotation: 0.06 } },
  {
    name: 'combined',
    state: {
      crop: { x: 0.5, y: 0.52, width: 0.9, height: 0.9 },
      brightness: 12, saturation: -15, vignette: 30,
    },
  },
]
