/**
 * Grow or contract the alpha channel of a selection mask by an exact number
 * of source pixels. A separable monotonic-window filter keeps the operation
 * linear in image size even on large AI selections.
 */

function filterLine(
  source: Uint8Array,
  target: Uint8Array,
  length: number,
  radius: number,
  offset: number,
  stride: number,
  erode: boolean,
  deque: Int32Array,
): void {
  const valueAt = (index: number) =>
    index < 0 || index >= length ? 0 : source[offset + index * stride]
  let head = 0
  let tail = 0

  for (let index = -radius; index < length + radius; index++) {
    const value = valueAt(index)
    while (tail > head) {
      const previous = valueAt(deque[tail - 1])
      if (erode ? previous < value : previous > value) break
      tail--
    }
    deque[tail++] = index

    const windowStart = index - radius * 2
    while (tail > head && deque[head] < windowStart) head++

    const outputIndex = index - radius
    if (outputIndex >= 0 && outputIndex < length) {
      target[offset + outputIndex * stride] = valueAt(deque[head])
    }
  }
}

export function morphSelectionPixels(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  deltaPx: number,
): void {
  const radius = Math.abs(Math.round(deltaPx))
  if (!radius || width <= 0 || height <= 0) return
  const erode = deltaPx < 0
  const alpha = new Uint8Array(width * height)
  for (let index = 0; index < alpha.length; index++) {
    alpha[index] = pixels[index * 4 + 3]
  }

  const horizontal = new Uint8Array(alpha.length)
  const deque = new Int32Array(Math.max(width, height) + radius * 2 + 1)
  for (let y = 0; y < height; y++) {
    filterLine(alpha, horizontal, width, radius, y * width, 1, erode, deque)
  }
  const result = new Uint8Array(alpha.length)
  for (let x = 0; x < width; x++) {
    filterLine(horizontal, result, height, radius, x, width, erode, deque)
  }

  for (let index = 0; index < result.length; index++) {
    const pixel = index * 4
    pixels[pixel] = 255
    pixels[pixel + 1] = 255
    pixels[pixel + 2] = 255
    pixels[pixel + 3] = result[index]
  }
}
