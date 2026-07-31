/**
 * Mask expand/contract for the model-backed region edits.
 *
 * A crisp selection is right for grading and wrong for generation: Remove and
 * Repaint models need the mask to reach PAST the object's edge or they leave
 * its outline behind. Expansion therefore happens at SUBMIT time, on the op's
 * own mask copy — the selection the user sees never changes.
 *
 * The percent semantic matches the inpaint MaskEditor's expand/contract step:
 * radius = percent/100 × avg(dimension) × 0.1, so the same number produces the
 * same growth in both places.
 */

/** The MaskEditor's default expand step, shared so the two stay in sync. */
export const DEFAULT_MASK_EXPAND_PERCENT = 15

/**
 * Morphologically grow (percent > 0) or shrink (percent < 0) the white region
 * of a white-on-black mask canvas, in place. Separable box max/min, so cost is
 * O(pixels × radius).
 */
export function expandMaskCanvas(canvas: HTMLCanvasElement, percent: number): void {
  if (!percent) return
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return
  const { width, height } = canvas
  const radius = Math.max(1, Math.round((Math.abs(percent) / 100) * ((width + height) / 2) * 0.1))
  const erode = percent < 0

  const imageData = ctx.getImageData(0, 0, width, height)
  const data = imageData.data

  // The mask is white-on-opaque-black; the red channel carries the value.
  const value = new Uint8Array(width * height)
  for (let i = 0; i < value.length; i++) value[i] = data[i * 4]

  const pick = erode
    ? (a: number, b: number) => Math.min(a, b)
    : (a: number, b: number) => Math.max(a, b)
  const edge = erode ? 0 : undefined // beyond-canvas reads erode as background

  const temp = new Uint8Array(width * height)
  for (let y = 0; y < height; y++) {
    const row = y * width
    for (let x = 0; x < width; x++) {
      let acc = value[row + x]
      const x0 = x - radius
      const x1 = x + radius
      if (edge !== undefined && (x0 < 0 || x1 >= width)) acc = pick(acc, edge)
      for (let nx = Math.max(0, x0); nx <= Math.min(width - 1, x1); nx++) {
        acc = pick(acc, value[row + nx])
      }
      temp[row + x] = acc
    }
  }
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      let acc = temp[y * width + x]
      const y0 = y - radius
      const y1 = y + radius
      if (edge !== undefined && (y0 < 0 || y1 >= height)) acc = pick(acc, edge)
      for (let ny = Math.max(0, y0); ny <= Math.min(height - 1, y1); ny++) {
        acc = pick(acc, temp[ny * width + x])
      }
      const level = acc > 127 ? 255 : 0
      const i = (y * width + x) * 4
      data[i] = level
      data[i + 1] = level
      data[i + 2] = level
      data[i + 3] = 255
    }
  }
  ctx.putImageData(imageData, 0, 0)
}
