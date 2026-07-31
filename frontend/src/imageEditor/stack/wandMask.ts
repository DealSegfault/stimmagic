import { featherAlpha } from './featherAlpha.ts'

export interface WandMaskOptions {
  /** Color-and-opacity similarity threshold on a 0-100 scale. */
  threshold: number
  /** How much of the accepted region is fully opaque. 100 is a hard mask. */
  spread: number
  /** Positive values grow the mask; negative values shrink it. */
  growPx: number
  /** Soft-edge radius applied after growing or shrinking. */
  featherPx: number
  /** Smooth a hard edge when feathering is disabled. */
  antialias: boolean
}

const SRGB_TO_LINEAR = new Float64Array(256)
for (let value = 0; value < 256; value++) {
  const encoded = value / 255
  SRGB_TO_LINEAR[value] = encoded <= 0.04045
    ? encoded / 12.92
    : ((encoded + 0.055) / 1.055) ** 2.4
}

/**
 * Convert canvas sRGB into CIELAB using the D50 profile connection space used
 * by ICC/LittleCMS. 
 * browser canvas is sRGB, so this is the corresponding fixed transform.
 */
export function srgbToLab(
  red: number,
  green: number,
  blue: number,
): readonly [number, number, number] {
  const r = SRGB_TO_LINEAR[red]
  const g = SRGB_TO_LINEAR[green]
  const b = SRGB_TO_LINEAR[blue]

  // Bradford-adapted sRGB D65 -> XYZ D50 matrix.
  const x = (0.4360747 * r + 0.3850649 * g + 0.1430804 * b) / 0.96422
  const y = 0.2225045 * r + 0.7168786 * g + 0.0606169 * b
  const z = (0.0139322 * r + 0.0971045 * g + 0.7141733 * b) / 0.82521
  const epsilon = 216 / 24389
  const kappa = 24389 / 27
  const pivot = (value: number) => value > epsilon
    ? Math.cbrt(value)
    : (kappa * value + 16) / 116
  const fx = pivot(x)
  const fy = pivot(y)
  const fz = pivot(z)
  return [
    116 * fy - 16,
    500 * (fx - fy),
    200 * (fy - fz),
  ]
}

function labAlphaDifference(
  pixels: Uint8ClampedArray,
  offset: number,
  targetLab: readonly [number, number, number],
  targetAlpha: number,
): number {
  const alpha = pixels[offset + 3]
  if (alpha === 0 || targetAlpha === 0) {
    return Math.round(Math.abs(alpha - targetAlpha) * 100 / 255)
  }

  const lab = srgbToLab(pixels[offset], pixels[offset + 1], pixels[offset + 2])
  const dL = lab[0] - targetLab[0]
  const da = lab[1] - targetLab[1]
  const db = lab[2] - targetLab[2]
  const dAlpha = (alpha - targetAlpha) * 100 / 255
  return Math.min(255, Math.floor(Math.hypot(dL, da, db, dAlpha)))
}

export function rgbaDifference(
  pixels: Uint8ClampedArray,
  offset: number,
  target: readonly [number, number, number, number],
): number {
  return labAlphaDifference(
    pixels,
    offset,
    srgbToLab(target[0], target[1], target[2]),
    target[3],
  )
}

function opacityForDifference(difference: number, threshold: number, spread: number): number {
  if (difference > threshold) return 0
  const softness = 100 - spread
  if (softness <= 0 || threshold <= 0) return 255

  // Soft selection policy: the inner portion is fully
  // opaque and the remainder falls off according to color similarity.
  return Math.min(
    255,
    Math.max(0, (threshold - difference) * 255 * 100 / (threshold * softness)),
  )
}

function slideExtreme(
  source: Uint8ClampedArray,
  target: Uint8ClampedArray,
  lineStart: number,
  length: number,
  stride: number,
  radius: number,
  grow: boolean,
): void {
  const indices = new Int32Array(length + radius * 2 + 1)
  const values = new Uint8ClampedArray(indices.length)
  let head = 0
  let tail = 0

  for (let position = -radius; position < length + radius; position++) {
    const value = position >= 0 && position < length
      ? source[lineStart + position * stride]
      : 0

    while (tail > head && (grow
      ? values[tail - 1] <= value
      : values[tail - 1] >= value)) {
      tail--
    }
    indices[tail] = position
    values[tail] = value
    tail++

    const firstAllowed = position - radius * 2
    while (tail > head && indices[head] < firstAllowed) head++

    const center = position - radius
    if (center >= 0 && center < length) {
      target[lineStart + center * stride] = values[head]
    }
  }
}

/**
 * Fast grayscale grow/shrink. 
 */
export function resizeMaskAlpha(
  alpha: Uint8ClampedArray,
  width: number,
  height: number,
  amount: number,
): Uint8ClampedArray {
  const radius = Math.abs(Math.round(amount))
  if (radius === 0) return alpha

  const grow = amount > 0
  const horizontal = new Uint8ClampedArray(alpha.length)
  const result = new Uint8ClampedArray(alpha.length)
  for (let y = 0; y < height; y++) {
    slideExtreme(alpha, horizontal, y * width, width, 1, radius, grow)
  }
  for (let x = 0; x < width; x++) {
    slideExtreme(horizontal, result, x, height, width, radius, grow)
  }
  return result
}

/**
 * One-pixel edge smoothing. Unlike feathering this touches only neighborhoods
 * that cross the selection boundary, leaving flat interiors unchanged.
 */
export function antialiasMaskAlpha(
  alpha: Uint8ClampedArray,
  width: number,
  height: number,
): Uint8ClampedArray {
  const result = alpha.slice()
  const weights = [1, 2, 1, 2, 4, 2, 1, 2, 1]

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let min = 255
      let max = 0
      let sum = 0
      let weightIndex = 0
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++, weightIndex++) {
          const nx = x + dx
          const ny = y + dy
          const value = nx >= 0 && nx < width && ny >= 0 && ny < height
            ? alpha[ny * width + nx]
            : 0
          min = Math.min(min, value)
          max = Math.max(max, value)
          sum += value * weights[weightIndex]
        }
      }
      if (min !== max) result[y * width + x] = Math.round(sum / 16)
    }
  }
  return result
}

export function createWandMaskAlpha(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  startX: number,
  startY: number,
  options: WandMaskOptions,
): Uint8ClampedArray {
  const alpha = new Uint8ClampedArray(width * height)
  const x = Math.floor(startX)
  const y = Math.floor(startY)
  if (width <= 0 || height <= 0 || x < 0 || x >= width || y < 0 || y >= height) {
    return alpha
  }

  const startOffset = (y * width + x) * 4
  const target = [
    pixels[startOffset],
    pixels[startOffset + 1],
    pixels[startOffset + 2],
    pixels[startOffset + 3],
  ] as const
  const targetLab = srgbToLab(target[0], target[1], target[2])
  const threshold = Math.max(0, Math.min(100, options.threshold))
  const spread = Math.max(0, Math.min(100, options.spread))

  const visited = new Uint8Array(width * height)
  const stack = new Int32Array(width * height)
  let length = 0
  const startIndex = y * width + x
  visited[startIndex] = 1
  stack[length++] = startIndex

  while (length > 0) {
    const index = stack[--length]
    const pixelOffset = index * 4
    let difference: number
    if (threshold === 1) {
      const bothTransparent = target[3] === 0 && pixels[pixelOffset + 3] === 0
      const exactMatch = target[0] === pixels[pixelOffset]
        && target[1] === pixels[pixelOffset + 1]
        && target[2] === pixels[pixelOffset + 2]
        && target[3] === pixels[pixelOffset + 3]
      difference = bothTransparent || exactMatch ? 0 : 255
    } else {
      difference = labAlphaDifference(pixels, pixelOffset, targetLab, target[3])
    }
    if (difference > threshold) continue

    alpha[index] = opacityForDifference(difference, threshold, spread)
    const px = index % width
    const py = Math.floor(index / width)

    if (px > 0 && !visited[index - 1]) {
      visited[index - 1] = 1
      stack[length++] = index - 1
    }
    if (px + 1 < width && !visited[index + 1]) {
      visited[index + 1] = 1
      stack[length++] = index + 1
    }
    if (py > 0 && !visited[index - width]) {
      visited[index - width] = 1
      stack[length++] = index - width
    }
    if (py + 1 < height && !visited[index + width]) {
      visited[index + width] = 1
      stack[length++] = index + width
    }
  }

  let refined = resizeMaskAlpha(alpha, width, height, options.growPx)
  if (options.featherPx > 0) {
    refined = featherAlpha(refined, width, height, options.featherPx)
  } else if (options.antialias) {
    refined = antialiasMaskAlpha(refined, width, height)
  }
  return refined
}
