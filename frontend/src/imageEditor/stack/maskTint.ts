/**
 * Draw a white-on-black mask as a coloured tint over the artwork.
 *
 * The naive version — draw the mask at low alpha, then `source-in` a fill — is
 * wrong, and wrong in a way that looks plausible: masks are fully OPAQUE
 * (white where selected, black elsewhere), so `source-in` matches every pixel
 * and floods the whole frame with the tint. What the eye needs is the mask's
 * LUMINANCE as the alpha channel, which is what this does.
 */

/** Resolve a CSS custom property holding `R G B` channels. */
export function tokenRgb(name: string, fallback: [number, number, number]): [number, number, number] {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const parts = raw.split(/[\s,]+/).map(Number).filter(n => Number.isFinite(n))
  return parts.length === 3 ? (parts as [number, number, number]) : fallback
}

export function drawMaskTint(
  ctx: CanvasRenderingContext2D,
  mask: CanvasImageSource,
  width: number,
  height: number,
  colour: [number, number, number],
  strength = 0.45
) {
  if (width < 1 || height < 1) return

  const scratch = document.createElement('canvas')
  scratch.width = width
  scratch.height = height
  const scratchCtx = scratch.getContext('2d', { willReadFrequently: true })!
  scratchCtx.drawImage(mask, 0, 0, width, height)

  const data = scratchCtx.getImageData(0, 0, width, height)
  const [r, g, b] = colour
  for (let i = 0; i < data.data.length; i += 4) {
    // Red channel stands in for luminance: masks are greyscale by contract.
    const coverage = data.data[i]
    data.data[i] = r
    data.data[i + 1] = g
    data.data[i + 2] = b
    data.data[i + 3] = Math.round(coverage * strength)
  }
  scratchCtx.putImageData(data, 0, 0)
  ctx.drawImage(scratch, 0, 0)
}
