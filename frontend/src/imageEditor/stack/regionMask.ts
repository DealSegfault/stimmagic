/**
 * Gradient masks: a region's coverage as GEOMETRY rather than as pixels.
 *
 * Everything else that makes a mask — brush, wand, lasso, the SAM3 object
 * tool — bakes alpha and uploads it. A ramp cannot work that way. Its whole
 * value is that you re-drag it after seeing the grade, and a baked ramp is a
 * one-shot selection with a soft edge. So these masks persist as parameters in
 * the region's authored frame and rasterise on demand at render time.
 *
 * The functions here are deliberately DOM-free so they can be tested directly;
 * `gradientMaskCanvas` is the only one that touches a canvas.
 */
import type { GradientMask, RegionMask, RetouchRegion } from './types.ts'

/** Softness a fresh linear ramp starts at — a visible ease, not a hard line. */
export const DEFAULT_LINEAR_SOFTNESS = 55
/** Feather a fresh ellipse starts at, as a share of its radius. */
export const DEFAULT_RADIAL_FEATHER = 60

/**
 * Shortest drag that counts as a gradient, in DISPLAY pixels — callers scale it
 * into source space. Below this a press-and-release is a misclick, not a ramp.
 */
export const MIN_GRADIENT_EXTENT = 8

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value
}

/** The same ease the adjustment pipeline uses, so falloff reads consistently. */
function smoothstep(edge0: number, edge1: number, x: number): number {
  if (edge1 <= edge0) return x < edge0 ? 0 : 1
  const t = clamp01((x - edge0) / (edge1 - edge0))
  return t * t * (3 - 2 * t)
}

/** Absent means raster: every document written before gradients existed. */
export function regionMaskOf(region: Pick<RetouchRegion, 'mask'>): RegionMask {
  return region.mask ?? { kind: 'raster' }
}

export function isGradientMask(mask: RegionMask | undefined): mask is GradientMask {
  return mask?.kind === 'linear' || mask?.kind === 'radial'
}

/** True when the region's coverage comes from geometry rather than a payload. */
export function hasGradientMask(region: Pick<RetouchRegion, 'mask'>): boolean {
  return isGradientMask(region.mask)
}

/**
 * A region contributes nothing unless it can produce coverage: drawn regions
 * need their payload, gradient regions need only their geometry.
 */
export function regionHasCoverage(
  region: Pick<RetouchRegion, 'mask' | 'mask_ref'>
): boolean {
  return isGradientMask(region.mask) ? !isDegenerate(region.mask) : !!region.mask_ref
}

/**
 * A ramp with no extent covers nothing, and an ellipse with no area covers
 * nothing. Callers refuse to commit these; the rasteriser returns empty rather
 * than guessing a direction it was never given.
 */
export function isDegenerate(mask: GradientMask): boolean {
  if (mask.kind === 'linear') {
    const dx = mask.x2 - mask.x1
    const dy = mask.y2 - mask.y1
    return Math.hypot(dx, dy) < 1
  }
  return mask.rx < 1 || mask.ry < 1
}

/**
 * Per-pixel coverage, 0..255, in the frame the geometry was authored in.
 *
 * Linear: full at `p1`, zero at `p2`, and constant along every line
 * perpendicular to that — which is what makes the transition invisible. There
 * is no falloff distance in pixels here on purpose: the ramp spans whatever
 * the person dragged.
 */
export function gradientAlpha(
  mask: GradientMask,
  width: number,
  height: number
): Uint8ClampedArray {
  const out = new Uint8ClampedArray(Math.max(0, width * height))
  if (width <= 0 || height <= 0 || isDegenerate(mask)) return out

  if (mask.kind === 'linear') {
    const dx = mask.x2 - mask.x1
    const dy = mask.y2 - mask.y1
    const len2 = dx * dx + dy * dy
    const ease = clamp01(mask.softness / 100)
    for (let y = 0, p = 0; y < height; y++) {
      for (let x = 0; x < width; x++, p++) {
        const t = clamp01(((x - mask.x1) * dx + (y - mask.y1) * dy) / len2)
        // Blend a straight ramp toward an eased one so Softness 0 stays a
        // true linear gradient rather than a subtly S-curved one.
        const ramp = smoothstep(0, 1, t) * ease + t * (1 - ease)
        out[p] = Math.round((1 - ramp) * 255)
      }
    }
    return out
  }

  const feather = Math.max(0.02, clamp01(mask.feather / 100))
  const inner = 1 - feather
  for (let y = 0, p = 0; y < height; y++) {
    for (let x = 0; x < width; x++, p++) {
      const nx = (x - mask.cx) / mask.rx
      const ny = (y - mask.cy) / mask.ry
      const d = Math.sqrt(nx * nx + ny * ny)
      const inside = 1 - smoothstep(inner, 1, d)
      out[p] = Math.round((mask.invert ? 1 - inside : inside) * 255)
    }
  }
  return out
}

/**
 * The white-on-black canvas the compositor expects. It reads the red channel
 * as coverage, so all three channels carry it and alpha stays opaque — the
 * same shape a drawn mask payload has.
 */
export function gradientMaskCanvas(
  mask: GradientMask,
  width: number,
  height: number
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, width)
  canvas.height = Math.max(1, height)
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(canvas.width, canvas.height)
  const alpha = gradientAlpha(mask, canvas.width, canvas.height)
  for (let p = 0, i = 0; p < alpha.length; p++, i += 4) {
    image.data[i] = alpha[p]
    image.data[i + 1] = alpha[p]
    image.data[i + 2] = alpha[p]
    image.data[i + 3] = 255
  }
  ctx.putImageData(image, 0, 0)
  return canvas
}

/**
 * A drag becomes a ramp: press where the effect should be strongest, release
 * where it should have died out entirely.
 */
export function linearMaskFromDrag(
  from: { x: number; y: number },
  to: { x: number; y: number },
  softness = DEFAULT_LINEAR_SOFTNESS
): GradientMask {
  return {
    kind: 'linear',
    x1: from.x,
    y1: from.y,
    x2: to.x,
    y2: to.y,
    softness,
  }
}

/**
 * A drag becomes an ellipse centred on the press, because that is where the
 * subject is — dragging out from a corner would put the subject in the corner.
 */
export function radialMaskFromDrag(
  from: { x: number; y: number },
  to: { x: number; y: number },
  options: { feather?: number; invert?: boolean } = {}
): GradientMask {
  return {
    kind: 'radial',
    cx: from.x,
    cy: from.y,
    rx: Math.abs(to.x - from.x),
    ry: Math.abs(to.y - from.y),
    feather: options.feather ?? DEFAULT_RADIAL_FEATHER,
    invert: options.invert ?? false,
  }
}

/**
 * Carry gradient geometry through a frame change — the same job `rewritePayload`
 * does for pixels, minus the resampling, which is the quiet advantage of storing
 * parameters: a ramp survives crop/un-crop round trips exactly.
 *
 * Crop geometry is translate-and-scale, so scaling the radii by the matrix's
 * own axis scales is exact for every affine this pipeline produces. A rotation
 * would shear an ellipse, which this shape cannot express; the axis scales stay
 * the honest approximation rather than a silent lie about the geometry.
 */
export function transformGradientMask(
  mask: GradientMask,
  matrix: [number, number, number, number, number, number]
): GradientMask {
  const [a, b, c, d, e, f] = matrix
  const point = (x: number, y: number) => ({ x: a * x + c * y + e, y: b * x + d * y + f })
  if (mask.kind === 'linear') {
    const p1 = point(mask.x1, mask.y1)
    const p2 = point(mask.x2, mask.y2)
    return { ...mask, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y }
  }
  const centre = point(mask.cx, mask.cy)
  const scaleX = Math.hypot(a, b)
  const scaleY = Math.hypot(c, d)
  return {
    ...mask,
    cx: centre.x,
    cy: centre.y,
    rx: Math.max(1, mask.rx * scaleX),
    ry: Math.max(1, mask.ry * scaleY),
  }
}

/** The gesture that made a gradient, if this select tool makes one. */
export function gradientToolKind(tool: string | null): 'linear' | 'radial' | null {
  return tool === 'linear' || tool === 'radial' ? tool : null
}

/**
 * The one slider a gradient brings to the island's fixed slot. Linear ramps
 * ease; ellipses feather. They are the same idea and deliberately not the same
 * number, because 100% feather on an ellipse still has an edge and 100%
 * softness on a ramp does not.
 */
export function gradientSliderOf(mask: GradientMask): { label: string; value: number } {
  return mask.kind === 'linear'
    ? { label: 'Softness', value: mask.softness }
    : { label: 'Feather', value: mask.feather }
}

export function withGradientSlider(mask: GradientMask, value: number): GradientMask {
  return mask.kind === 'linear'
    ? { ...mask, softness: value }
    : { ...mask, feather: value }
}
