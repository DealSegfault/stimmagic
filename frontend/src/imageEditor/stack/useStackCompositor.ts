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
import {
  coTransform, geometryBelow, isIdentity, multiply, rewritePayload,
} from './geometryTransform'
import type { Affine } from './geometryTransform'
export { canonicalOp, stackHashes }
import {
  applyAnnotations,
  applyCrop,
  applyAdjust,
  applyRasterLayer,
  cropOutputSize,
  adjustIsIdentity,
} from './opExecutors'
import { featherAlpha } from './featherAlpha'
import { retouchRegionAlpha } from './retouchRegionAlpha'
import { maskedRetouchAdjustmentParams } from './adjustSections'

export interface CompositeStage {
  /** Input hash for this op — the cache key of the composite BELOW it. */
  inputHash: string
  op: Op
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

/**
 * Composite a cached Retouch result through its independently editable mask.
 *
 * Old documents stored identical alpha in both payloads, so `min` preserves
 * their pixels exactly at Feather 0. Newer results may be opaque under the
 * mask; in that case the mask alone supplies the region shape.
 */
export function compositeRetouchRegion(
  input: CanvasImageSource,
  result: CanvasImageSource,
  mask: CanvasImageSource,
  width: number,
  height: number,
  options: { featherPx?: number; opacity?: number } = {},
): HTMLCanvasElement {
  const { featherPx = 0, opacity = 1 } = options
  const resultCanvas = makeCanvas(width, height)
  const resultCtx = resultCanvas.getContext('2d', { willReadFrequently: true })!
  resultCtx.drawImage(result, 0, 0, width, height)
  const resultData = resultCtx.getImageData(0, 0, width, height)

  const maskCanvas = makeCanvas(width, height)
  const maskCtx = maskCanvas.getContext('2d', { willReadFrequently: true })!
  maskCtx.drawImage(mask, 0, 0, width, height)
  const maskData = maskCtx.getImageData(0, 0, width, height)
  const maskAlpha = new Uint8ClampedArray(width * height)
  const resultAlpha = new Uint8ClampedArray(width * height)
  for (let i = 3, pixel = 0; i < maskData.data.length; i += 4, pixel++) {
    maskAlpha[pixel] = maskData.data[i]
    resultAlpha[pixel] = resultData.data[i]
  }
  const compositingAlpha = retouchRegionAlpha(
    resultAlpha,
    maskAlpha,
    width,
    height,
    featherPx,
  )
  for (let i = 3, pixel = 0; i < resultData.data.length; i += 4, pixel++) {
    resultData.data[i] = compositingAlpha[pixel]
  }
  resultCtx.putImageData(resultData, 0, 0)

  const output = makeCanvas(width, height)
  const outputCtx = output.getContext('2d')!
  outputCtx.drawImage(input, 0, 0, width, height)
  outputCtx.globalAlpha = opacity
  outputCtx.drawImage(resultCanvas, 0, 0)
  outputCtx.globalAlpha = 1
  return output
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
  /**
   * Resolve a payload ref to something drawable. `revision` changes whenever
   * mutable paint pixels are rewritten under the same ref.
   */
  loadPayload: (ref: string, revision?: number) => Promise<CanvasImageSource>
  /** Resolve the base revision's pixels. */
  loadBase: () => Promise<CanvasImageSource>
  /**
   * The image as of each step, for the row previews — emitted during the
   * replay, where each intermediate composite already exists. Computing these
   * separately would mean replaying the stack once per row.
   *
   * Only steps the render actually recomputed are emitted: a render that
   * resumes from a cached intermediate leaves the ones below it untouched, and
   * their previews are unchanged by definition.
   */
  onStepPreview?: (opId: string, preview: string) => void
}

/** Longest edge of a row preview, in device-independent pixels. */
const STEP_PREVIEW_PX = 72

/**
 * A row-preview-sized snapshot of a composite, cropped square from the center
 * so a column of them reads as a column regardless of each frame's aspect.
 */
function squarePreview(source: HTMLCanvasElement): string {
  const size = Math.min(source.width, source.height)
  const canvas = makeCanvas(STEP_PREVIEW_PX, STEP_PREVIEW_PX)
  canvas.getContext('2d')!.drawImage(
    source,
    (source.width - size) / 2, (source.height - size) / 2, size, size,
    0, 0, STEP_PREVIEW_PX, STEP_PREVIEW_PX
  )
  // JPEG: the composite is opaque (it starts from the base), and a lossless
  // 72px tile per step would hold megabytes of data URL on a long stack.
  return canvas.toDataURL('image/jpeg', 0.72)
}

/**
 * Replays a stack into a composite, caching intermediates by input hash.
 *
 * Bounded LRU over ImageBitmaps: an unbounded cache on a 30-step stack of
 * 8MP frames is hundreds of megabytes, and the common editing motion (append at
 * top, adjust the top op) only ever needs the one entry below the edit.
 */
/** A stable 32-bit seed from an op id — same step, same grain, every render. */
function seedFrom(id: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

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

  /**
   * Seed an exact materialized stage, typically the persisted cold-open head.
   *
   * Restoring the head deliberately avoids replaying every source-resolution
   * edit, so its intermediate composites do not exist yet. Use the head's
   * real image as an immediate fallback for those rows instead of leaving a
   * column of empty thumbnail wells. Any later replay replaces the fallback
   * with that step's exact preview through the normal callback.
   */
  prime(hash: string, canvas: HTMLCanvasElement, fallbackPreviewOpIds: string[] = []) {
    this.remember(hash, canvas)
    if (!fallbackPreviewOpIds.length) return
    const preview = squarePreview(canvas)
    for (const opId of fallbackPreviewOpIds) {
      this.deps.onStepPreview?.(opId, preview)
    }
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
        current = await this.applyOp(current, op, current.width, current.height, doc, i)
      } catch (error) {
        this.failedOpIds.add(op.id)
        console.warn(`[imageStack] step "${op.label}" could not be applied`, error)
      }
      const nextHash = i + 1 < inputs.length ? inputs[i + 1] : head
      this.remember(nextHash, current)
      this.deps.onStepPreview?.(op.id, squarePreview(current))
    }
    this.cache.set(head, current)
    return current
  }

  /**
   * A payload, carried from the frame it was MADE in into the frame it is
   * being USED in.
   *
   * Every spatial payload — a mask, a paint layer, a region — records the
   * geometry that was below it when it was created (`payload_frame`). That
   * recording is the anchor: it makes the payload's pixels addressable in the
   * ORIGINAL image's coordinates, `M_created⁻¹`, and from there they can be
   * carried into whatever the geometry is now, `M_now ∘ M_created⁻¹`. Without
   * an anchor there is nothing to translate through: a crop removed after the
   * payload was made leaves it sitting at coordinates that meant something in
   * a frame that no longer exists.
   *
   * Derived at composite time rather than baked, so removing a crop and
   * putting it back lands the payload exactly where it started instead of
   * resampling it twice.
   */
  private async loadAnchored(
    ref: string,
    doc: StackDocument,
    index: number,
    width: number,
    height: number
  ): Promise<CanvasImageSource> {
    const op = doc.edits[index] as any
    const payload = await this.deps.loadPayload(ref, op?._revision ?? 0)
    const created = op?.payload_frame
    if (!created) return payload

    const now = geometryBelow(doc, index)
    const matrix = coTransform(created.matrix as Affine, now.matrix)
    if (!matrix || isIdentity(matrix)) return payload
    return rewritePayload(payload, matrix, width, height)
  }

  /** Rebuild one compact Retouch payload in its full authored frame, then anchor it. */
  private async loadRetouchPayload(
    ref: string,
    region: any,
    doc: StackDocument,
    index: number,
    width: number,
    height: number,
  ): Promise<CanvasImageSource> {
    const payload = await this.deps.loadPayload(ref, 0)
    const created = region.payload_frame
    const [x, y] = region.payload_origin ?? [0, 0]
    const placePayload: Affine = [1, 0, 0, 1, x, y]
    const previewScale = Number((doc as any)._preview_scale ?? 1)
    const baseScale: Affine = [previewScale, 0, 0, previewScale, 0, 0]
    if (!created) {
      const positioned = multiply(baseScale, placePayload)
      return isIdentity(positioned)
        ? payload
        : rewritePayload(payload, positioned, width, height)
    }

    const now = geometryBelow(doc, index)
    // Preview documents keep authored payload coordinates but render against
    // a smaller base. Include that base-space scale in the new transform.
    const nowFromAuthoredBase = multiply(now.matrix, baseScale)
    const carry = coTransform(created.matrix as Affine, nowFromAuthoredBase)
    if (!carry) return payload
    const positioned = multiply(carry, placePayload)
    return isIdentity(positioned)
      ? payload
      : rewritePayload(payload, positioned, width, height)
  }

  private async applyOp(
    input: HTMLCanvasElement,
    op: Op,
    width: number,
    height: number,
    doc: StackDocument,
    index: number
  ): Promise<HTMLCanvasElement> {
    if (!op.enabled) return input

    const picked = pickedCandidate(op)
    const anyOp = op as any

    if (op.class === 'patch') {
      // No pick yet — the op is staged, and a staged op contributes nothing.
      if (!picked?.patch_ref || !anyOp.mask_ref) return input
      // The patch was generated FOR this mask in the same frame, so the two
      // travel together.
      const [patch, mask] = await Promise.all([
        this.loadAnchored(picked.patch_ref, doc, index, width, height),
        this.loadAnchored(anyOp.mask_ref, doc, index, width, height),
      ])
      return compositePatch(input, patch, mask, width, height, {
        origin: picked.patch_origin || [0, 0],
        featherPx: anyOp.blend?.feather_px ?? 6,
        opacity: anyOp.blend?.opacity ?? 1,
      })
    }

    if (op.class === 'parametric') {
      const kind = anyOp.exec?.kind
      if (kind === 'crop') {
        return applyCrop(input, input.width, input.height, anyOp.params || {})
      }
      if (kind === 'adjust') {
        if (adjustIsIdentity(anyOp.params || {})) return input
        // The op's id seeds its noise, so a step's grain belongs to that step
        // and survives every re-render of everything around it.
        return applyAdjust(input, width, height, anyOp.params || {}, seedFrom(op.id))
      }
      return input
    }

    if (op.class === 'container') {
      const kind = anyOp.exec?.kind
      if (kind === 'annotate') {
        return applyAnnotations(input, width, height, anyOp.params?.shapes || [], input)
      }
      if (kind === 'retouch-regions') {
        let output = input
        for (const region of anyOp.regions ?? []) {
          if (!region.enabled || !region.mask_ref) continue
          const mask = await this.loadRetouchPayload(
            region.mask_ref,
            region,
            doc,
            index,
            width,
            height,
          )
          // A local adjustment is parametric: it derives fresh pixels from
          // the composite beneath it on every render, then the retained mask
          // limits those pixels to the authored region. Unlike Heal/Clone it
          // never bakes a result cache or becomes stale.
          if (
            region.kind === 'adjust'
            || region.kind === 'light'
            || region.kind === 'color'
            || region.kind === 'detail'
          ) {
            const settings = region.settings ?? {}
            const adjusted = applyAdjust(
              output,
              width,
              height,
              maskedRetouchAdjustmentParams(settings),
              seedFrom(region.id),
            )
            output = compositeRetouchRegion(
              output,
              adjusted,
              mask,
              width,
              height,
              {
                featherPx: settings.feather_px ?? 0,
                opacity: settings.opacity ?? 1,
              },
            )
            continue
          }
          if (!region.result_ref) continue
          const result = await this.loadRetouchPayload(
            region.result_ref,
            region,
            doc,
            index,
            width,
            height,
          )
          output = compositeRetouchRegion(
            output,
            result,
            mask,
            width,
            height,
            {
              featherPx: region.settings?.feather_px ?? 0,
              opacity: region.settings?.opacity ?? 1,
            },
          )
        }
        return output
      }
      if (!anyOp.raster_ref) return input
      const layer = await this.loadAnchored(anyOp.raster_ref, doc, index, width, height)
      return applyRasterLayer(input, layer, width, height, anyOp.blend?.opacity ?? 1)
    }

    // An op kind this build does not know is a no-op rather than an error: a
    // document written by a newer build must still open and render.
    return input
  }
}
