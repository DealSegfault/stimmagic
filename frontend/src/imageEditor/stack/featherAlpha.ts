/**
 * Blur a mask alpha channel with a separable box pass repeated three times.
 *
 * CanvasRenderingContext2D.filter is unreliable in WKWebView, so every v2 mask
 * feather uses this deterministic typed-array path instead.
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
      for (let x = -r; x <= r; x++) {
        sum += src[row + Math.min(width - 1, Math.max(0, x))]
      }
      for (let x = 0; x < width; x++) {
        dst[row + x] = sum / (2 * r + 1)
        const out = row + Math.min(width - 1, Math.max(0, x - r))
        const input = row + Math.min(width - 1, Math.max(0, x + r + 1))
        sum += src[input] - src[out]
      }
    }
    ;[src, dst] = [dst, src]

    // Vertical
    for (let x = 0; x < width; x++) {
      let sum = 0
      for (let y = -r; y <= r; y++) {
        sum += src[Math.min(height - 1, Math.max(0, y)) * width + x]
      }
      for (let y = 0; y < height; y++) {
        dst[y * width + x] = sum / (2 * r + 1)
        const out = Math.min(height - 1, Math.max(0, y - r)) * width + x
        const input = Math.min(height - 1, Math.max(0, y + r + 1)) * width + x
        sum += src[input] - src[out]
      }
    }
    ;[src, dst] = [dst, src]
  }
  return src
}
