/**
 * Gradient-domain seamless cloning for the donor-driven Patch tool.
 *
 * The selected pixels are unknowns in a Poisson system. Donor gradients are
 * the guidance field; destination pixels immediately outside the selection
 * are Dirichlet boundary conditions. Solving that system transfers texture
 * and structure from the donor while reconstructing color and illumination so
 * the result belongs to its destination instead of looking pasted on top.
 *
 * Pérez, Gangnet & Blake, "Poisson Image Editing", SIGGRAPH 2003, equations
 * 7–11. The solve uses a coarse-to-fine pyramid followed by red/black SOR at
 * each level: a standard multigrid-shaped acceleration that preserves the
 * browser implementation's deterministic, dependency-free contract.
 */

export interface SeamlessPatchOptions {
  /** Finest-level relaxation sweeps after coarse reconstruction. */
  fineIterations?: number
  /** Coarsest-level sweeps, where a tight solve is inexpensive. */
  coarseIterations?: number
  /** Per-channel convergence threshold in 8-bit color units. */
  tolerance?: number
  /** Successive over-relaxation factor. Values in (1, 2) accelerate Laplace solves. */
  relaxation?: number
}

interface RasterLevel {
  source: Uint8ClampedArray
  destination: Uint8ClampedArray
  mask: Uint8ClampedArray
  width: number
  height: number
}

interface PoissonSolution {
  red: Float32Array
  green: Float32Array
  blue: Float32Array
  domain: Uint8Array
}

const NEIGHBORS = [[-1, 0], [1, 0], [0, -1], [0, 1]] as const

function clampByte(value: number): number {
  return Math.max(0, Math.min(255, value))
}

function assertRasterLength(
  name: string,
  data: Uint8ClampedArray,
  expected: number,
): void {
  if (data.length !== expected) {
    throw new Error(`${name} has ${data.length} values; expected ${expected}`)
  }
}

function makeDomain(mask: Uint8ClampedArray, width: number, height: number): Uint8Array {
  const domain = new Uint8Array(mask.length)
  // The cropped raster edge is the outer Dirichlet boundary. applyPatch
  // normally supplies one pixel of destination padding around the selection.
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const pixel = y * width + x
      // Ignore near-zero feather tails while building the system. They remain
      // visible during final compositing but cannot explode the solve domain.
      if (mask[pixel] >= 8) domain[pixel] = 1
    }
  }
  return domain
}

function downsample(level: RasterLevel): RasterLevel {
  const width = Math.max(1, Math.ceil(level.width / 2))
  const height = Math.max(1, Math.ceil(level.height / 2))
  const source = new Uint8ClampedArray(width * height * 4)
  const destination = new Uint8ClampedArray(width * height * 4)
  const mask = new Uint8ClampedArray(width * height)

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const target = y * width + x
      let samples = 0
      let maskSum = 0
      const sourceSum = [0, 0, 0, 0]
      const destinationSum = [0, 0, 0, 0]
      for (let dy = 0; dy < 2; dy++) {
        const sy = y * 2 + dy
        if (sy >= level.height) continue
        for (let dx = 0; dx < 2; dx++) {
          const sx = x * 2 + dx
          if (sx >= level.width) continue
          const sourcePixel = sy * level.width + sx
          const rgba = sourcePixel * 4
          for (let channel = 0; channel < 4; channel++) {
            sourceSum[channel] += level.source[rgba + channel]
            destinationSum[channel] += level.destination[rgba + channel]
          }
          maskSum += level.mask[sourcePixel]
          samples++
        }
      }
      const rgba = target * 4
      for (let channel = 0; channel < 4; channel++) {
        source[rgba + channel] = Math.round(sourceSum[channel] / samples)
        destination[rgba + channel] = Math.round(destinationSum[channel] / samples)
      }
      mask[target] = Math.round(maskSum / samples)
    }
  }
  return { source, destination, mask, width, height }
}

function bilinearSample(
  channel: Float32Array,
  width: number,
  height: number,
  x: number,
  y: number,
): number {
  const x0 = Math.max(0, Math.min(width - 1, Math.floor(x)))
  const y0 = Math.max(0, Math.min(height - 1, Math.floor(y)))
  const x1 = Math.min(width - 1, x0 + 1)
  const y1 = Math.min(height - 1, y0 + 1)
  const tx = x - Math.floor(x)
  const ty = y - Math.floor(y)
  const top = channel[y0 * width + x0] * (1 - tx) + channel[y0 * width + x1] * tx
  const bottom = channel[y1 * width + x0] * (1 - tx) + channel[y1 * width + x1] * tx
  return top * (1 - ty) + bottom * ty
}

function bilinearSampleRgba(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  x: number,
  y: number,
  channel: number,
): number {
  const x0 = Math.max(0, Math.min(width - 1, Math.floor(x)))
  const y0 = Math.max(0, Math.min(height - 1, Math.floor(y)))
  const x1 = Math.min(width - 1, x0 + 1)
  const y1 = Math.min(height - 1, y0 + 1)
  const tx = x - Math.floor(x)
  const ty = y - Math.floor(y)
  const top = data[(y0 * width + x0) * 4 + channel] * (1 - tx)
    + data[(y0 * width + x1) * 4 + channel] * tx
  const bottom = data[(y1 * width + x0) * 4 + channel] * (1 - tx)
    + data[(y1 * width + x1) * 4 + channel] * tx
  return top * (1 - ty) + bottom * ty
}

function colorOffsetAtBoundary(level: RasterLevel, domain: Uint8Array): number[] {
  const offset = [0, 0, 0]
  let samples = 0
  for (let y = 0; y < level.height; y++) {
    for (let x = 0; x < level.width; x++) {
      const pixel = y * level.width + x
      if (!domain[pixel]) continue
      let boundary = false
      for (const [dx, dy] of NEIGHBORS) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || nx >= level.width || ny < 0 || ny >= level.height) continue
        if (!domain[ny * level.width + nx]) {
          boundary = true
          break
        }
      }
      if (!boundary) continue
      const rgba = pixel * 4
      offset[0] += level.destination[rgba] - level.source[rgba]
      offset[1] += level.destination[rgba + 1] - level.source[rgba + 1]
      offset[2] += level.destination[rgba + 2] - level.source[rgba + 2]
      samples++
    }
  }
  if (samples > 0) {
    offset[0] /= samples
    offset[1] /= samples
    offset[2] /= samples
  }
  return offset
}

function solveLevel(
  level: RasterLevel,
  options: Required<SeamlessPatchOptions>,
): PoissonSolution {
  const pixels = level.width * level.height
  const domain = makeDomain(level.mask, level.width, level.height)
  const offset = colorOffsetAtBoundary(level, domain)
  const red = new Float32Array(pixels)
  const green = new Float32Array(pixels)
  const blue = new Float32Array(pixels)

  const hasCoarserLevel = Math.max(level.width, level.height) > 48
    && Math.min(level.width, level.height) > 2
  const coarseLevel = hasCoarserLevel ? downsample(level) : null
  const coarse = coarseLevel ? solveLevel(coarseLevel, options) : null

  for (let y = 0; y < level.height; y++) {
    for (let x = 0; x < level.width; x++) {
      const pixel = y * level.width + x
      const rgba = pixel * 4
      if (!domain[pixel]) {
        red[pixel] = level.destination[rgba]
        green[pixel] = level.destination[rgba + 1]
        blue[pixel] = level.destination[rgba + 2]
        continue
      }
      if (!coarse || !coarseLevel) {
        red[pixel] = clampByte(level.source[rgba] + offset[0])
        green[pixel] = clampByte(level.source[rgba + 1] + offset[1])
        blue[pixel] = clampByte(level.source[rgba + 2] + offset[2])
        continue
      }

      const coarseX = (x + 0.5) * coarseLevel.width / level.width - 0.5
      const coarseY = (y + 0.5) * coarseLevel.height / level.height - 0.5
      const reconstructed = [
        bilinearSample(coarse.red, coarseLevel.width, coarseLevel.height, coarseX, coarseY),
        bilinearSample(coarse.green, coarseLevel.width, coarseLevel.height, coarseX, coarseY),
        bilinearSample(coarse.blue, coarseLevel.width, coarseLevel.height, coarseX, coarseY),
      ]
      // Restore fine donor detail that was absent at the coarser level. This is
      // the Laplacian-pyramid part of the initialization and prevents the fast
      // solve from buying speed by blurring texture.
      const coarseSource = [0, 1, 2].map(channel =>
        bilinearSampleRgba(
          coarseLevel.source,
          coarseLevel.width,
          coarseLevel.height,
          coarseX,
          coarseY,
          channel,
        ))
      red[pixel] = clampByte(reconstructed[0] + level.source[rgba] - coarseSource[0])
      green[pixel] = clampByte(reconstructed[1] + level.source[rgba + 1] - coarseSource[1])
      blue[pixel] = clampByte(reconstructed[2] + level.source[rgba + 2] - coarseSource[2])
    }
  }

  const degree = new Uint8Array(pixels)
  const rhsRed = new Float32Array(pixels)
  const rhsGreen = new Float32Array(pixels)
  const rhsBlue = new Float32Array(pixels)
  for (let y = 0; y < level.height; y++) {
    for (let x = 0; x < level.width; x++) {
      const pixel = y * level.width + x
      if (!domain[pixel]) continue
      const rgba = pixel * 4
      for (const [dx, dy] of NEIGHBORS) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || nx >= level.width || ny < 0 || ny >= level.height) continue
        degree[pixel]++
        const neighbor = ny * level.width + nx
        const neighborRgba = neighbor * 4
        rhsRed[pixel] += level.source[rgba] - level.source[neighborRgba]
        rhsGreen[pixel] += level.source[rgba + 1] - level.source[neighborRgba + 1]
        rhsBlue[pixel] += level.source[rgba + 2] - level.source[neighborRgba + 2]
        if (!domain[neighbor]) {
          rhsRed[pixel] += level.destination[neighborRgba]
          rhsGreen[pixel] += level.destination[neighborRgba + 1]
          rhsBlue[pixel] += level.destination[neighborRgba + 2]
        }
      }
    }
  }

  const iterations = coarse
    ? options.fineIterations
    : options.coarseIterations
  for (let iteration = 0; iteration < iterations; iteration++) {
    let maxDelta = 0
    for (let parity = 0; parity < 2; parity++) {
      for (let y = 0; y < level.height; y++) {
        for (let x = (y + parity) & 1; x < level.width; x += 2) {
          const pixel = y * level.width + x
          if (!domain[pixel] || degree[pixel] === 0) continue
          let sumRed = rhsRed[pixel]
          let sumGreen = rhsGreen[pixel]
          let sumBlue = rhsBlue[pixel]
          for (const [dx, dy] of NEIGHBORS) {
            const nx = x + dx
            const ny = y + dy
            if (nx < 0 || nx >= level.width || ny < 0 || ny >= level.height) continue
            const neighbor = ny * level.width + nx
            if (!domain[neighbor]) continue
            sumRed += red[neighbor]
            sumGreen += green[neighbor]
            sumBlue += blue[neighbor]
          }
          const oldRed = red[pixel]
          const oldGreen = green[pixel]
          const oldBlue = blue[pixel]
          red[pixel] = oldRed + options.relaxation * (sumRed / degree[pixel] - oldRed)
          green[pixel] = oldGreen + options.relaxation * (sumGreen / degree[pixel] - oldGreen)
          blue[pixel] = oldBlue + options.relaxation * (sumBlue / degree[pixel] - oldBlue)
          maxDelta = Math.max(
            maxDelta,
            Math.abs(red[pixel] - oldRed),
            Math.abs(green[pixel] - oldGreen),
            Math.abs(blue[pixel] - oldBlue),
          )
        }
      }
    }
    if (maxDelta <= options.tolerance) break
  }
  return { red, green, blue, domain }
}

/**
 * Reconstruct one source-aligned patch inside `mask`.
 *
 * `source` and `destination` are equally sized RGBA rasters. `mask` is one
 * alpha byte per pixel. Outside-mask pixels are returned byte-for-byte from
 * the destination. Fractional selection alpha is applied only after the solve;
 * a normal hard selection therefore has full coverage without a pasted seam.
 */
export function seamlessPatch(
  source: Uint8ClampedArray,
  destination: Uint8ClampedArray,
  mask: Uint8ClampedArray,
  width: number,
  height: number,
  options: SeamlessPatchOptions = {},
): Uint8ClampedArray {
  const pixels = width * height
  assertRasterLength('source', source, pixels * 4)
  assertRasterLength('destination', destination, pixels * 4)
  assertRasterLength('mask', mask, pixels)
  const output = new Uint8ClampedArray(destination)
  if (width <= 0 || height <= 0 || pixels === 0) return output

  const normalizedOptions: Required<SeamlessPatchOptions> = {
    fineIterations: Math.max(1, Math.round(options.fineIterations ?? 14)),
    coarseIterations: Math.max(1, Math.round(options.coarseIterations ?? 100)),
    tolerance: Math.max(0, options.tolerance ?? 0.05),
    relaxation: Math.max(1, Math.min(1.95, options.relaxation ?? 1.72)),
  }
  const level = { source, destination, mask, width, height }
  const solved = solveLevel(level, normalizedOptions)

  for (let pixel = 0; pixel < pixels; pixel++) {
    const selectionAlpha = mask[pixel] / 255
    if (selectionAlpha <= 0) continue
    const rgba = pixel * 4
    const solvedRed = solved.domain[pixel] ? clampByte(solved.red[pixel]) : destination[rgba]
    const solvedGreen = solved.domain[pixel] ? clampByte(solved.green[pixel]) : destination[rgba + 1]
    const solvedBlue = solved.domain[pixel] ? clampByte(solved.blue[pixel]) : destination[rgba + 2]
    output[rgba] = Math.round(
      solvedRed * selectionAlpha + destination[rgba] * (1 - selectionAlpha),
    )
    output[rgba + 1] = Math.round(
      solvedGreen * selectionAlpha + destination[rgba + 1] * (1 - selectionAlpha),
    )
    output[rgba + 2] = Math.round(
      solvedBlue * selectionAlpha + destination[rgba + 2] * (1 - selectionAlpha),
    )
    output[rgba + 3] = Math.round(
      source[rgba + 3] * selectionAlpha
      + destination[rgba + 3] * (1 - selectionAlpha),
    )
  }
  return output
}
