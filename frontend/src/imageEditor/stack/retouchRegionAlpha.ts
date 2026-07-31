import { featherAlpha } from './featherAlpha.ts'

/**
 * Resolve the compositing alpha for a Retouch result cache and its live mask.
 *
 * `min` is the compatibility bridge: legacy caches already carry mask alpha,
 * while newer result caches may be opaque under the independent mask.
 */
export function retouchRegionAlpha(
  resultAlpha: Uint8ClampedArray,
  maskAlpha: Uint8ClampedArray,
  width: number,
  height: number,
  featherPx: number,
): Uint8ClampedArray {
  const feathered = featherAlpha(maskAlpha, width, height, featherPx)
  const output = new Uint8ClampedArray(resultAlpha.length)
  for (let pixel = 0; pixel < output.length; pixel++) {
    output[pixel] = Math.min(resultAlpha[pixel], feathered[pixel])
  }
  return output
}
