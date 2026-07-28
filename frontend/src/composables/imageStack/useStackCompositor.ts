/**
 * Canvas 2D compositor for the op stack.
 *
 * Main thread, no WebGL, no wasm. The old editor already does full-frame
 * Canvas 2D pixel work acceptably on target hardware, target assets are
 * marketing-scale rather than gigapixel, and the Mac webview is WKWebView,
 * which cannot be version-pinned — Canvas 2D is its most conservative fully
 * supported surface.
 *
 * Two WKWebView-driven rules hold throughout:
 *  - never use canvas `filter:` for the mask feather (unreliable there); the
 *    blur is our own separable box pass over the mask alpha;
 *  - feature-detect anything newer and always keep the main-thread path.
 *
 * Replay is content-hash keyed: `hash(i+1) = H(hash(i), canonical(op(i)))`, so
 * any edit invalidates exactly the ops at and above it and everything below is
 * a cache hit. Disabled ops hash as identity, which is why toggling one off is
 * instant. Reordering swaps hash inputs the same way — there is no special
 * dirty logic anywhere.
 */

import type { Op, StackDocument } from './types'
import { pickedCandidate } from './types'
import { canonicalOp, stackHashes } from './stackHashes'
export { canonicalOp, stackHashes }
import {
  applyAnnotations,
  applyCrop,
  applyAdjust,
  applyRasterLayer,
  applyThroughRegion,
  cropOutputSize,
  adjustIsIdentity,
} from './opExecutors'

export interface CompositeStage {
  /** Input hash for this op — the cache key of the composite BELOW it. */
  inputHash: string
  op: Op
}

/**
 * Blur a mask's alpha with a separable box pass, repeated three times, which
 * approximates a Gaussian closely enough for a feather and stays fast on a
 * plain typed array. Deliberately not canvas `filter: blur()`.
 */
export function featherAlpha(
  alpha: Uint8ClampedArray,
  width: number,
  height: number,
  radius: number
): Uint8ClampedArray {
  if (radius <= 0) return alpha
  let src = alpha
  let dst = new Uint8ClampedArray(alpha.length)
  const r = Math.max(1, Math.round(radius))
  for (let pass = 0; pass < 3; pass++) {
    // Horizontal
    for (let y = 0; y < height; y++) {
      const row = y * width
      let sum = 0
      for (let x = -r; x <= r; x++) sum += src[row + Math.min(width - 1, Math.max(0, x))]
      for (let x = 0; x < width; x++) {
        dst[row + x] = sum / (2 * r + 1)
        const out = row + Math.min(width - 1, Math.max(0, x - r))
        const inp = row + Math.min(width - 1, Math.max(0, x + r + 1))
        sum += src[inp] - src[out]
      }
    }
    ;[src, dst] = [dst, src]
    // Vertical
    for (let x = 0; x < width; x++) {
      let sum = 0
      for (let y = -r; y <= r; y++) sum += src[Math.min(height - 1, Math.max(0, y)) * width + x]
      for (let y = 0; y < height; y++) {
        dst[y * width + x] = sum / (2 * r + 1)
        const out = Math.min(height - 1, Math.max(0, y - r)) * width + x
        const inp = Math.min(height - 1, Math.max(0, y + r + 1)) * width + x
        sum += src[inp] - src[out]
      }
    }
    ;[src, dst] = [dst, src]
  }
  return src
}

function makeCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return canvas
}

/**
 * Composite a generative patch over its input through a feathered mask.
 *
 * This is the VAE-roundtrip correction, and it is the whole reason the patch op
 * class exists: only the pixels inside the mask come from the model. Everything
 * outside is the input, untouched, however much the model repainted it.
 */
export function compositePatch(
  input: CanvasImageSource,
  patch: CanvasImageSource,
  mask: CanvasImageSource,
  width: number,
  height: number,
  options: { origin?: [number, number]; featherPx?: number; opacity?: number } = {}
): HTMLCanvasElement {
  const { origin = [0, 0], featherPx = 6, opacity = 1 } = options

  // 1. The mask's alpha, feathered. Masks arrive as white-on-black.
  const maskCanvas = makeCanvas(width, height)
  const maskCtx = maskCanvas.getContext('2d', { willReadFrequently: true })!
  maskCtx.drawImage(mask, 0, 0, width, height)
  const maskData = maskCtx.getImageData(0, 0, width, height)
  const luminance = new Uint8ClampedArray(width * height)
  for (let i = 0, p = 0; i < maskData.data.length; i += 4, p++) {
    luminance[p] = maskData.data[i]
  }
  const feathered = featherAlpha(luminance, width, height, featherPx)

  // 2. The patch, positioned in its input space, with the feathered mask as
  //    its alpha channel.
  const patchCanvas = makeCanvas(width, height)
  const patchCtx = patchCanvas.getContext('2d', { willReadFrequently: true })!
  patchCtx.drawImage(patch, origin[0], origin[1])
  const patchData = patchCtx.getImageData(0, 0, width, height)
  for (let i = 0, p = 0; i < patchData.data.length; i += 4, p++) {
    patchData.data[i + 3] = Math.round(patchData.data[i + 3] * (feathered[p] / 255))
  }
  patchCtx.putImageData(patchData, 0, 0)

  // 3. Draw over the input.
  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!
  ctx.drawImage(input, 0, 0, width, height)
  ctx.globalAlpha = opacity
  ctx.drawImage(patchCanvas, 0, 0)
  ctx.globalAlpha = 1
  return out
}

/** Draw a whole-image result, which replaces the composite outright. */
export function compositeWhole(
  result: CanvasImageSource,
  width: number,
  height: number,
  opacity = 1
): HTMLCanvasElement {
  const out = makeCanvas(width, height)
  const ctx = out.getContext('2d')!
  ctx.globalAlpha = opacity
  ctx.drawImage(result, 0, 0, width, height)
  return out
}

/**
 * Bounding box of a mask's non-black pixels, grown by `margin`.
 * Used to crop a model output down to the patch that is actually kept.
 */
export function maskBounds(
  mask: CanvasImageSource,
  width: number,
  height: number,
  margin = 0
): { x: number; y: number; width: number; height: number } | null {
  const canvas = makeCanvas(width, height)
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(mask, 0, 0, width, height)
  const { data } = ctx.getImageData(0, 0, width, height)

  let minX = width, minY = height, maxX = -1, maxY = -1
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4] > 8) {
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
    }
  }
  if (maxX < 0) return null

  minX = Math.max(0, minX - margin)
  minY = Math.max(0, minY - margin)
  maxX = Math.min(width - 1, maxX + margin)
  maxY = Math.min(height - 1, maxY + margin)
  return { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 }
}

/**
 * Crop a model output to the mask's bounds. Only this region is ever kept, so
 * storing the full frame would be storing pixels the composite discards.
 */
export function extractPatch(
  output: CanvasImageSource,
  bounds: { x: number; y: number; width: number; height: number }
): HTMLCanvasElement {
  const canvas = makeCanvas(bounds.width, bounds.height)
  canvas.getContext('2d')!.drawImage(
    output,
    bounds.x, bounds.y, bounds.width, bounds.height,
    0, 0, bounds.width, bounds.height
  )
  return canvas
}

export function canvasToBlob(canvas: HTMLCanvasElement, type = 'image/png'): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => (blob ? resolve(blob) : reject(new Error('canvas encode failed'))), type)
  })
}

export interface CompositorDeps {
  /** Resolve a payload ref to something drawable. */
  loadPayload: (ref: string) => Promise<CanvasImageSource>
  /** Resolve the base revision's pixels. */
  loadBase: () => Promise<CanvasImageSource>
}

/**
 * Replays a stack into a composite, caching intermediates by input hash.
 *
 * Bounded LRU over ImageBitmaps: an unbounded cache on a 30-step stack of
 * 8MP frames is hundreds of megabytes, and the common editing motion (append at
 * top, adjust the top op) only ever needs the one entry below the edit.
 */
export class StackCompositor {
  private cache = new Map<string, HTMLCanvasElement>()
  /** Ops that could not be applied on the last render, for the UI to report. */
  readonly failedOpIds = new Set<string>()
  private maxEntries: number

  constructor(private deps: CompositorDeps, maxEntries = 12) {
    this.maxEntries = maxEntries
  }

  clear() {
    this.cache.clear()
  }

  /** Drop cached composites at and above a given input hash. */
  invalidateFrom(hash: string) {
    this.cache.delete(hash)
  }

  private remember(key: string, canvas: HTMLCanvasElement) {
    // Map preserves insertion order, so the first key is the oldest.
    if (this.cache.size >= this.maxEntries) {
      const oldest = this.cache.keys().next().value
      if (oldest !== undefined) this.cache.delete(oldest)
    }
    this.cache.set(key, canvas)
  }

  /**
   * The composite an op at `index` applies to — everything strictly below it.
   * Resampling a step needs this, not the head: a step re-samples against what
   * it actually sits on.
   */
  async renderUpTo(doc: StackDocument, index: number): Promise<HTMLCanvasElement> {
    return this.render({ ...doc, edits: doc.edits.slice(0, index) })
  }

  async render(doc: StackDocument): Promise<HTMLCanvasElement> {
    const { inputs, head } = stackHashes(doc)
    const cachedHead = this.cache.get(head)
    if (cachedHead) return cachedHead
    this.failedOpIds.clear()

    const width = doc.canvas.width
    const height = doc.canvas.height

    // Start from the deepest cached point rather than the base.
    let startIndex = 0
    let current: HTMLCanvasElement | null = null
    for (let i = doc.edits.length - 1; i >= 0; i--) {
      const cached = this.cache.get(inputs[i])
      if (cached) {
        current = cached
        startIndex = i
        break
      }
    }
    if (!current) {
      const base = await this.deps.loadBase()
      current = makeCanvas(width, height)
      current.getContext('2d')!.drawImage(base, 0, 0, width, height)
      if (doc.edits.length) this.remember(inputs[0], current)
    }

    for (let i = startIndex; i < doc.edits.length; i++) {
      const op = doc.edits[i]
      // A geometry op resizes the frame, and every op above it works in the
      // new space — which is why the working size is carried forward rather
      // than read from the document.
      //
      // An op whose payload cannot be loaded contributes nothing rather than
      // failing the render: one unreadable mask must not blank the canvas and
      // hide every other step's work.
      try {
        current = await this.applyOp(current, op, current.width, current.height)
      } catch (error) {
        this.failedOpIds.add(op.id)
        console.warn(`[imageStack] step "${op.label}" could not be applied`, error)
      }
      const nextHash = i + 1 < inputs.length ? inputs[i + 1] : head
      this.remember(nextHash, current)
    }
    this.cache.set(head, current)
    return current
  }

  private async applyOp(
    input: HTMLCanvasElement,
    op: Op,
    width: number,
    height: number
  ): Promise<HTMLCanvasElement> {
    if (!op.enabled) return input

    const picked = pickedCandidate(op)
    const anyOp = op as any

    if (op.class === 'patch') {
      // No pick yet — the op is staged, and a staged op contributes nothing.
      if (!picked?.patch_ref || !anyOp.mask_ref) return input
      const [patch, mask] = await Promise.all([
        this.deps.loadPayload(picked.patch_ref),
        this.deps.loadPayload(anyOp.mask_ref),
      ])
      return compositePatch(input, patch, mask, width, height, {
        origin: picked.patch_origin || [0, 0],
        featherPx: anyOp.blend?.feather_px ?? 6,
        opacity: anyOp.blend?.opacity ?? 1,
      })
    }

    if (op.class === 'whole') {
      if (!picked?.patch_ref) return input
      const result = await this.deps.loadPayload(picked.patch_ref)
      return compositeWhole(result, width, height, anyOp.blend?.opacity ?? 1)
    }

    if (op.class === 'parametric') {
      const kind = anyOp.exec?.kind
      if (kind === 'crop') {
        // Geometry is never scoped to a region: cropping part of an image is
        // not a thing, and a region would have no space to be expressed in.
        return applyCrop(input, input.width, input.height, anyOp.params || {})
      }
      if (kind === 'adjust') {
        if (adjustIsIdentity(anyOp.params || {})) return input
        const result = applyAdjust(input, width, height, anyOp.params || {})
        return this.scopeToRegion(input, result, op, width, height)
      }
      return input
    }

    if (op.class === 'container') {
      const kind = anyOp.exec?.kind
      if (kind === 'annotate') {
        const result = applyAnnotations(input, width, height, anyOp.params?.shapes || [], input)
        return this.scopeToRegion(input, result, op, width, height)
      }
      if (!anyOp.raster_ref) return input
      const layer = await this.deps.loadPayload(anyOp.raster_ref)
      const result = applyRasterLayer(input, layer, width, height, anyOp.blend?.opacity ?? 1)
      return this.scopeToRegion(input, result, op, width, height)
    }

    // An op kind this build does not know is a no-op rather than an error: a
    // document written by a newer build must still open and render.
    return input
  }

  /** Limit an op's effect to its region, when it has one. */
  private async scopeToRegion(
    input: HTMLCanvasElement,
    result: HTMLCanvasElement,
    op: Op,
    width: number,
    height: number
  ): Promise<HTMLCanvasElement> {
    if (!op.region?.mask_ref) return result
    const mask = await this.deps.loadPayload(op.region.mask_ref)
    return applyThroughRegion(input, result, mask, width, height, {
      featherPx: op.region.feather_px,
      invert: op.region.invert,
    })
  }
}
