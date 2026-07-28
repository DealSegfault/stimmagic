/**
 * Executors for the op kinds that carry over from the snapshot editor.
 *
 * The pixel math is the snapshot editor's, consumed as a library from
 * `@stimma/image-editor` rather than reimplemented — a second copy of the
 * colour and effect math would drift, and the migrated documents have to look
 * identical or the migration is a lie.
 *
 * What changes is the *shape*: the snapshot editor applied these as fields on
 * one flat state object in a fixed order, and here each is a step in a stack
 * that can be toggled, reordered and scoped. The Adjust op deliberately holds
 * every touched section (Light, Colour, Film, Effects) rather than one op per
 * filter, because the user-facing unit is a adjust session, not a slider.
 */

import { featherAlpha } from './useStackCompositor'
import {
  applyColorIsolation,
  applyColorMatrix,
  applyEffects,
  applyGradientMap,
  applySplitToning,
  combineAdjustments,
  hasEffects,
  multiplyColorMatrices,
  FILTER_MATRICES,
} from '@stimma/image-editor'
// The annotation renderer is the copied one, so an Annotate step composites
// through exactly the code its gestures were authored against.
import { renderShapes } from '../../imageEditor/ported/shapes'

export interface CropParams {
  /**
   * The crop rectangle, normalised against the input.
   *
   * `x`/`y` are the crop's CENTRE, not its top-left — the convention the
   * snapshot editor's crop UI produces and its writer consumes. Kept rather
   * than converted so migration is a straight copy: a coordinate conversion is
   * exactly the kind of thing that is wrong in one place and right in another.
   * An identity crop is therefore `{ x: 0.5, y: 0.5, width: 1, height: 1 }`.
   */
  rect: { x: number; y: number; width: number; height: number }
  /** Fine straightening, radians. */
  rotation?: number
  /** Quarter turns clockwise. */
  rotation90?: 0 | 1 | 2 | 3
  flipX?: boolean
  flipY?: boolean
}

export interface AdjustParams {
  // Light + colour
  brightness?: number
  contrast?: number
  saturation?: number
  exposure?: number
  temperature?: number
  gamma?: number
  filter?: string | null
  colorMatrix?: number[] | null
  // Film
  splitToningEnabled?: boolean
  splitToningShadowHue?: number
  splitToningShadowSat?: number
  splitToningHighlightHue?: number
  splitToningHighlightSat?: number
  splitToningBalance?: number
  gradientMapEnabled?: boolean
  gradientMapShadowColor?: any
  gradientMapHighlightColor?: any
  gradientMapIntensity?: number
  colorIsolationEnabled?: boolean
  colorIsolationHue?: number
  colorIsolationRange?: number
  colorIsolationFeather?: number
  // Effects
  blur?: number
  sharpen?: number
  noise?: number
  glow?: number
  pixelate?: number
  chromaticAberration?: number
  motionBlur?: number
  motionBlurAngle?: number
  vignette?: number
  clarity?: number
  halftone?: number
  halftoneAngle?: number
  vhs?: number
  glitch?: number
  glitchBlockSize?: number
  ditherEnabled?: boolean
  ditherPalette?: string
}

function makeCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return canvas
}

/**
 * Output dimensions after a geometry op. Ops above a crop work in the cropped
 * space, so this has to be answerable without rendering.
 *
 * Quarter turns deliberately do NOT swap the output dimensions: the snapshot
 * editor rotates the drawn image inside a frame sized by the crop rectangle,
 * and a migrated document has to land on the same canvas.
 */
export function cropOutputSize(
  input: { width: number; height: number },
  params: CropParams
): { width: number; height: number } {
  return {
    width: Math.max(1, Math.round(input.width * (params.rect?.width ?? 1))),
    height: Math.max(1, Math.round(input.height * (params.rect?.height ?? 1))),
  }
}

/**
 * Crop, straighten and flip.
 *
 * The stage order mirrors the snapshot editor's writer exactly — rotation
 * (fine + quarter turns as one angle), then flips, then the crop window drawn
 * about the output centre — because a different order produces a different
 * image, and a migrated document has to match pixel for pixel.
 */
export function applyCrop(
  input: CanvasImageSource,
  inputWidth: number,
  inputHeight: number,
  params: CropParams
): HTMLCanvasElement {
  const rect = params.rect ?? { x: 0.5, y: 0.5, width: 1, height: 1 }
  const { width, height } = cropOutputSize(
    { width: inputWidth, height: inputHeight },
    params
  )

  const sourceWidth = rect.width * inputWidth
  const sourceHeight = rect.height * inputHeight
  // Centre-based rect: the top-left of the crop window is the centre minus
  // half its size.
  const sourceX = (rect.x - rect.width / 2) * inputWidth
  const sourceY = (rect.y - rect.height / 2) * inputHeight

  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!

  ctx.save()
  ctx.translate(width / 2, height / 2)
  const rotation = (params.rotation ?? 0) + ((params.rotation90 ?? 0) * Math.PI) / 2
  if (rotation !== 0) ctx.rotate(rotation)
  if (params.flipX || params.flipY) {
    ctx.scale(params.flipX ? -1 : 1, params.flipY ? -1 : 1)
  }

  // A quarter turn swaps which axis the drawn image spans, while the frame
  // stays as the crop sized it.
  let drawWidth = width
  let drawHeight = height
  if (params.rotation90 === 1 || params.rotation90 === 3) {
    drawWidth = height
    drawHeight = width
  }

  ctx.drawImage(
    input,
    sourceX, sourceY, sourceWidth, sourceHeight,
    -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight
  )
  ctx.restore()
  return out
}

/** Whether a Adjust op would change any pixel — a no-op still costs a copy. */
export function adjustIsIdentity(params: AdjustParams): boolean {
  const zeroish = (v: number | undefined) => !v
  return (
    zeroish(params.brightness) && zeroish(params.contrast) && zeroish(params.saturation) &&
    zeroish(params.exposure) && zeroish(params.temperature) &&
    (params.gamma === undefined || params.gamma === 1) &&
    !params.filter && !params.colorMatrix &&
    !params.splitToningEnabled && !params.gradientMapEnabled && !params.colorIsolationEnabled &&
    !hasEffects(effectsStateFrom(params))
  )
}

function effectsStateFrom(params: AdjustParams) {
  return {
    blur: params.blur ?? 0,
    sharpen: params.sharpen ?? 0,
    noise: params.noise ?? 0,
    glow: params.glow ?? 0,
    pixelate: params.pixelate ?? 0,
    chromaticAberration: params.chromaticAberration ?? 0,
    motionBlur: params.motionBlur ?? 0,
    motionBlurAngle: params.motionBlurAngle ?? 0,
    vignette: params.vignette ?? 0,
    clarity: params.clarity ?? 0,
    halftone: params.halftone ?? 0,
    halftoneAngle: params.halftoneAngle ?? 0,
    vhs: params.vhs ?? 0,
    glitch: params.glitch ?? 0,
    glitchBlockSize: params.glitchBlockSize ?? 16,
    ditherEnabled: params.ditherEnabled ?? false,
    ditherPalette: (params.ditherPalette === 'none' ? '8bit' : params.ditherPalette) ?? '8bit',
  } as any
}

/**
 * The whole parametric adjustment family, in the snapshot editor's order:
 * base adjustments → filter preset → explicit matrix → split tone → gradient
 * map → colour isolation → effects.
 */
export function applyAdjust(
  input: CanvasImageSource,
  width: number,
  height: number,
  params: AdjustParams
): HTMLCanvasElement {
  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(input, 0, 0, width, height)

  const adjustments = {
    brightness: params.brightness ?? 0,
    contrast: params.contrast ?? 0,
    saturation: params.saturation ?? 0,
    exposure: params.exposure ?? 0,
    temperature: params.temperature ?? 0,
    gamma: params.gamma ?? 1,
  }
  const hasAdjustments =
    adjustments.brightness !== 0 || adjustments.contrast !== 0 ||
    adjustments.saturation !== 0 || adjustments.exposure !== 0 ||
    adjustments.temperature !== 0 || adjustments.gamma !== 1

  if (hasAdjustments) {
    const data = ctx.getImageData(0, 0, width, height)
    applyColorMatrix(data, combineAdjustments(adjustments))
    ctx.putImageData(data, 0, 0)
  }

  if (params.filter && (FILTER_MATRICES as any)[params.filter]) {
    const identity = combineAdjustments({
      brightness: 0, contrast: 0, saturation: 0, exposure: 0, temperature: 0, gamma: 1,
    })
    const matrix = multiplyColorMatrices((FILTER_MATRICES as any)[params.filter], identity)
    const data = ctx.getImageData(0, 0, width, height)
    applyColorMatrix(data, matrix)
    ctx.putImageData(data, 0, 0)
  }

  if (params.colorMatrix) {
    const data = ctx.getImageData(0, 0, width, height)
    applyColorMatrix(data, params.colorMatrix)
    ctx.putImageData(data, 0, 0)
  }

  if (params.splitToningEnabled) {
    const data = ctx.getImageData(0, 0, width, height)
    applySplitToning(
      data,
      params.splitToningShadowHue ?? 30,
      params.splitToningShadowSat ?? 0,
      params.splitToningHighlightHue ?? 200,
      params.splitToningHighlightSat ?? 0,
      params.splitToningBalance ?? 0
    )
    ctx.putImageData(data, 0, 0)
  }

  if (params.gradientMapEnabled && params.gradientMapShadowColor && params.gradientMapHighlightColor) {
    const data = ctx.getImageData(0, 0, width, height)
    applyGradientMap(
      data,
      params.gradientMapShadowColor,
      params.gradientMapHighlightColor,
      params.gradientMapIntensity ?? 100
    )
    ctx.putImageData(data, 0, 0)
  }

  if (params.colorIsolationEnabled) {
    const data = ctx.getImageData(0, 0, width, height)
    applyColorIsolation(
      data,
      params.colorIsolationHue ?? 0,
      params.colorIsolationRange ?? 30,
      params.colorIsolationFeather ?? 20
    )
    ctx.putImageData(data, 0, 0)
  }

  const effects = effectsStateFrom(params)
  if (hasEffects(effects)) {
    const result = applyEffects(out, effects)
    ctx.clearRect(0, 0, width, height)
    ctx.drawImage(result, 0, 0)
  }

  return out
}

/**
 * A raster layer (Paint, or an imported retouch layer) drawn over its input.
 * A layer IS a step: several Paint rows are several layers, each at its own
 * stack position with its own opacity.
 */
export function applyRasterLayer(
  input: CanvasImageSource,
  layer: CanvasImageSource,
  width: number,
  height: number,
  opacity = 1
): HTMLCanvasElement {
  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!
  ctx.drawImage(input, 0, 0, width, height)
  ctx.globalAlpha = opacity
  ctx.drawImage(layer, 0, 0, width, height)
  ctx.globalAlpha = 1
  return out
}

/**
 * Vector annotations. Parametric-class physics: the shapes are params, so
 * re-rendering at any size is free and re-entering the op is lossless.
 */
export function applyAnnotations(
  input: CanvasImageSource,
  width: number,
  height: number,
  shapes: any[],
  sourceForRedaction?: HTMLCanvasElement
): HTMLCanvasElement {
  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!
  ctx.drawImage(input, 0, 0, width, height)
  if (shapes?.length) {
    renderShapes(ctx, shapes as any, { width, height }, sourceForRedaction as any)
  }
  return out
}

/**
 * Restrict an op's effect to a region.
 *
 * The region is a mask like any other; limiting an adjustment is compositing
 * its result back over the input through that mask. Copy-at-creation, never a
 * live link — the op references only its own payloads.
 */
export function applyThroughRegion(
  input: CanvasImageSource,
  result: CanvasImageSource,
  regionMask: CanvasImageSource,
  width: number,
  height: number,
  options: { featherPx?: number; invert?: boolean } = {}
): HTMLCanvasElement {
  const { featherPx = 0, invert = false } = options

  const maskCanvas = makeCanvas(width, height)
  const maskCtx = maskCanvas.getContext('2d', { willReadFrequently: true })!
  maskCtx.drawImage(regionMask, 0, 0, width, height)
  const maskData = maskCtx.getImageData(0, 0, width, height)

  const layer = makeCanvas(width, height)
  const layerCtx = layer.getContext('2d', { willReadFrequently: true })!
  layerCtx.drawImage(result, 0, 0, width, height)
  const layerData = layerCtx.getImageData(0, 0, width, height)

  for (let i = 0; i < layerData.data.length; i += 4) {
    const coverage = invert ? 255 - maskData.data[i] : maskData.data[i]
    layerData.data[i + 3] = Math.round(layerData.data[i + 3] * (coverage / 255))
  }
  layerCtx.putImageData(layerData, 0, 0)

  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!
  ctx.drawImage(input, 0, 0, width, height)
  ctx.drawImage(featherPx > 0 ? featherEdges(layer, featherPx) : layer, 0, 0)
  return out
}

/** Soften a layer's alpha edge. Own pixel math, not canvas `filter:`. */
function featherEdges(layer: HTMLCanvasElement, radius: number): HTMLCanvasElement {
  const { width, height } = layer
  const ctx = layer.getContext('2d', { willReadFrequently: true })!
  const data = ctx.getImageData(0, 0, width, height)
  const alpha = new Uint8ClampedArray(width * height)
  for (let i = 0, p = 0; i < data.data.length; i += 4, p++) alpha[p] = data.data[i + 3]

  // The compositor's separable box blur, so a feather looks the same wherever
  // it appears.
  const blurred = featherAlpha(alpha, width, height, radius)
  for (let i = 0, p = 0; i < data.data.length; i += 4, p++) data.data[i + 3] = blurred[p]
  ctx.putImageData(data, 0, 0)
  return layer
}
