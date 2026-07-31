import { featherAlpha } from './featherAlpha.ts'

/**
 * Resolve the compositing alpha for a cutout (Remove background) step.
 *
 * The matte MULTIPLIES the input's alpha rather than replacing it: pixels the
 * base image already had transparent stay transparent, and a soft model matte
 * keeps its softness. Opacity backs the cut off toward the original — at 0 the
 * step is a no-op, which is what an opacity slider must mean on a row whose
 * whole contribution is removal.
 */
export function cutoutAlpha(
  inputAlpha: Uint8ClampedArray,
  matteAlpha: Uint8ClampedArray,
  width: number,
  height: number,
  featherPx: number,
  opacity: number,
): Uint8ClampedArray {
  const matte = featherPx > 0
    ? featherAlpha(matteAlpha, width, height, featherPx)
    : matteAlpha
  const strength = Math.max(0, Math.min(1, opacity))
  const output = new Uint8ClampedArray(inputAlpha.length)
  for (let pixel = 0; pixel < output.length; pixel++) {
    const keep = 1 - strength + (strength * matte[pixel]) / 255
    output[pixel] = inputAlpha[pixel] * keep
  }
  return output
}
