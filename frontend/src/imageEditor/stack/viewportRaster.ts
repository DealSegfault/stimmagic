/**
 * Raster policy for editor chrome whose CSS box may be zoomed far beyond the
 * fitted viewport. Zoom is presentation, not a request for more backing-store
 * pixels: reallocating an overlay at the zoomed size makes its cost grow with
 * the square of the zoom factor.
 */

export function overlayBackingSize(
  fittedWidth: number,
  fittedHeight: number,
  devicePixelRatio: number,
): { width: number; height: number } {
  const density = Math.max(1, Math.min(devicePixelRatio || 1, 2))
  return {
    width: Math.max(1, Math.round(fittedWidth * density)),
    height: Math.max(1, Math.round(fittedHeight * density)),
  }
}

/** Source pixels covered by one brush pixel at the fitted (100%) view. */
export function fittedBrushScale(
  sourceWidth: number,
  zoomedDisplayWidth: number,
  viewZoom: number,
): number {
  return sourceWidth / Math.max(1, zoomedDisplayWidth / Math.max(viewZoom, 0.0001))
}

/** A fitted-view brush measurement as it appears in the zoomed CSS box. */
export function zoomedBrushSize(size: number, viewZoom: number): number {
  return size * viewZoom
}
