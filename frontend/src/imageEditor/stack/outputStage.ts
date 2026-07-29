/**
 * The output stage: the document's terminal scale, applied once at save.
 *
 * Not a row, deliberately. An upscale reads the whole composite and replaces
 * it, which is exactly the shape that cannot live in the stack — a step that
 * occludes everything below it is a new base, not a layer. Running it at the
 * save boundary makes it the one operation allowed to change the base, at the
 * one moment a base change is legitimate, and leaves every row in the Edits
 * list a live parameter.
 *
 * Order at save is raster → upscale → vectors. Annotations are rendered AFTER
 * the scale, at the final resolution, so text comes out crisp instead of
 * enlarged. That is the whole reason the stage knows about vectors at all.
 */

import type { OutputStage } from './types'

/** Lanczos window. 3 is the usual quality/ringing compromise for photos. */
const LANCZOS_A = 3

function sinc(x: number): number {
  if (x === 0) return 1
  const p = Math.PI * x
  return Math.sin(p) / p
}

function lanczos(x: number): number {
  const t = Math.abs(x)
  if (t >= LANCZOS_A) return 0
  return sinc(t) * sinc(t / LANCZOS_A)
}

/**
 * Precomputed contributions for one axis: for each destination pixel, the
 * source indices that feed it and their normalized weights.
 *
 * Separable, so a 2D resample is two 1D passes rather than a kernel per pixel.
 *
 * Exported for the tests: it is the whole numerical content of the resampler,
 * and it is the only part of it that can be checked without a real canvas.
 */
export function contributions(srcSize: number, dstSize: number) {
  const scale = dstSize / srcSize
  // Upsampling samples the kernel at its natural width; downsampling has to
  // widen it to cover every source pixel that lands in a destination one, or
  // the result aliases.
  const support = scale >= 1 ? LANCZOS_A : LANCZOS_A / scale
  const rows: Array<{ start: number; weights: Float32Array }> = []

  for (let d = 0; d < dstSize; d++) {
    const center = (d + 0.5) / scale - 0.5
    const start = Math.max(0, Math.ceil(center - support))
    const end = Math.min(srcSize - 1, Math.floor(center + support))
    const weights = new Float32Array(Math.max(0, end - start + 1))

    let total = 0
    for (let s = start; s <= end; s++) {
      const w = lanczos(scale >= 1 ? s - center : (s - center) * scale)
      weights[s - start] = w
      total += w
    }
    // A pathological window (every weight zero) would black the row out;
    // falling back to the nearest source pixel keeps it honest.
    if (total === 0) {
      const nearest = Math.min(srcSize - 1, Math.max(0, Math.round(center)))
      rows.push({ start: nearest, weights: Float32Array.from([1]) })
      continue
    }
    for (let i = 0; i < weights.length; i++) weights[i] /= total
    rows.push({ start, weights })
  }
  return rows
}

/**
 * Lanczos-3 resample. Own implementation rather than `drawImage`, whose scaling
 * quality is not specified and differs across the engines this app ships on —
 * and the Mac webview is WKWebView, which cannot be version-pinned.
 */
export function resampleLanczos(
  source: HTMLCanvasElement,
  width: number,
  height: number
): HTMLCanvasElement {
  const srcW = source.width
  const srcH = source.height
  const src = source.getContext('2d', { willReadFrequently: true })!
    .getImageData(0, 0, srcW, srcH).data

  // Horizontal pass into an intermediate of the destination width.
  const horizontal = new Float32Array(width * srcH * 4)
  const xs = contributions(srcW, width)
  for (let y = 0; y < srcH; y++) {
    const srcRow = y * srcW * 4
    const dstRow = y * width * 4
    for (let x = 0; x < width; x++) {
      const { start, weights } = xs[x]
      let r = 0, g = 0, b = 0, a = 0
      for (let i = 0; i < weights.length; i++) {
        const p = srcRow + (start + i) * 4
        const w = weights[i]
        r += src[p] * w
        g += src[p + 1] * w
        b += src[p + 2] * w
        a += src[p + 3] * w
      }
      const q = dstRow + x * 4
      horizontal[q] = r
      horizontal[q + 1] = g
      horizontal[q + 2] = b
      horizontal[q + 3] = a
    }
  }

  // Vertical pass into the final image.
  const out = document.createElement('canvas')
  out.width = width
  out.height = height
  const image = new ImageData(width, height)
  const ys = contributions(srcH, height)
  for (let y = 0; y < height; y++) {
    const { start, weights } = ys[y]
    const dstRow = y * width * 4
    for (let x = 0; x < width; x++) {
      let r = 0, g = 0, b = 0, a = 0
      for (let i = 0; i < weights.length; i++) {
        const p = (start + i) * width * 4 + x * 4
        const w = weights[i]
        r += horizontal[p] * w
        g += horizontal[p + 1] * w
        b += horizontal[p + 2] * w
        a += horizontal[p + 3] * w
      }
      const q = dstRow + x * 4
      image.data[q] = r
      image.data[q + 1] = g
      image.data[q + 2] = b
      image.data[q + 3] = a
    }
  }
  out.getContext('2d')!.putImageData(image, 0, 0)
  return out
}

export function outputOf(output: OutputStage | undefined | null): OutputStage {
  return {
    enabled: !!output?.enabled,
    method: output?.method === 'resample' ? 'resample' : 'photo',
    tool_id: output?.tool_id ?? null,
    params: output?.params ?? {},
  }
}

/** Whether the picker is in short-edge mode for this stage. */
function isPixelMode(output: OutputStage): boolean {
  return (output.params.resolutionMode ?? 'relative') === 'pixels'
}

/**
 * The short edge the tool is asked for.
 *
 * Mirrors ToolView's own `finalResolution` exactly, including its defaults: the
 * payload builder always sends `resolution` and treats `scale_factor` as UI
 * state, so a second rule here would mean the editor and ToolView asking the
 * same tool for different things.
 */
export function finalResolutionFor(
  output: OutputStage | undefined | null,
  width: number,
  height: number
): number {
  const stage = outputOf(output)
  if (!isPixelMode(stage) && width && height) {
    return Math.round(Math.min(width, height) * (stage.params.scaleFactor || 2))
  }
  return stage.params.targetResolution || 1080
}

/**
 * The dimensions a save would write.
 *
 * Derived from the composite's ACTUAL size rather than from the document's
 * canvas, because Expand changes that size mid-stack. Short-edge mode preserves
 * the aspect ratio, which is the contract the picker states on screen.
 */
export function outputDimensions(
  output: OutputStage | undefined | null,
  width: number,
  height: number
): { width: number; height: number } {
  const stage = outputOf(output)
  if (!stage.enabled || !width || !height) return { width, height }

  const scale = isPixelMode(stage)
    ? (stage.params.targetResolution || 1080) / Math.min(width, height)
    : (stage.params.scaleFactor || 2)
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

/**
 * How the stage reads on the save button — the factor when it is a factor, the
 * short edge when the tool works that way. Empty when the stage is off.
 */
export function outputLabel(output: OutputStage | undefined | null): string {
  const stage = outputOf(output)
  if (!stage.enabled) return ''
  return isPixelMode(stage)
    ? `${stage.params.targetResolution || 1080}px`
    : `${stage.params.scaleFactor || 2}\u00d7`
}
