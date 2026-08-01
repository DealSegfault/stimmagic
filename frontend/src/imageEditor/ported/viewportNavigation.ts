export interface ViewportPoint {
  x: number
  y: number
}

export interface ViewportSize {
  width: number
  height: number
}

export interface WheelModifiers {
  ctrlKey: boolean
  metaKey: boolean
}

/** Lightroom-style zoom is explicit; plain wheel/two-finger input is pan. */
export function isZoomWheelGesture(input: WheelModifiers): boolean {
  return input.ctrlKey || input.metaKey
}

/**
 * Normalize Lightroom-style pan input into CSS pixels. Shift turns a vertical
 * mouse wheel into horizontal movement; a trackpad's native two-axis deltas
 * pass through untouched.
 */
export function wheelPanDelta(
  delta: ViewportPoint,
  deltaMode: number,
  viewport: ViewportSize,
  shiftKey = false,
): ViewportPoint {
  const horizontal = shiftKey && delta.x === 0 ? delta.y : delta.x
  const vertical = shiftKey && delta.x === 0 ? 0 : delta.y
  if (deltaMode === 1) {
    return { x: horizontal * 16, y: vertical * 16 }
  }
  if (deltaMode === 2) {
    return { x: horizontal * viewport.width, y: vertical * viewport.height }
  }
  return { x: horizontal, y: vertical }
}

/**
 * Keep a zoomed image centred on axes where it is smaller than the viewport,
 * and keep its edges flush with the viewport on axes where it is larger.
 */
export function clampViewportPan(
  pan: ViewportPoint,
  zoom: number,
  content: ViewportSize,
  viewport: ViewportSize,
): ViewportPoint {
  if (zoom <= 1) return { x: 0, y: 0 }

  const maxX = Math.max(0, (content.width * zoom - viewport.width) / 2)
  const maxY = Math.max(0, (content.height * zoom - viewport.height) / 2)
  return {
    x: Math.max(-maxX, Math.min(maxX, pan.x)),
    y: Math.max(-maxY, Math.min(maxY, pan.y)),
  }
}

/** Preserve the image point under the cursor while changing zoom. */
export function panForZoomAtPoint(
  pan: ViewportPoint,
  currentZoom: number,
  nextZoom: number,
  pointFromViewportCenter: ViewportPoint,
): ViewportPoint {
  const factor = nextZoom / currentZoom
  return {
    x: pointFromViewportCenter.x - (pointFromViewportCenter.x - pan.x) * factor,
    y: pointFromViewportCenter.y - (pointFromViewportCenter.y - pan.y) * factor,
  }
}

/** Translate wheel scroll offsets into canvas movement in both axes. */
export function panForWheelDelta(
  pan: ViewportPoint,
  delta: ViewportPoint,
): ViewportPoint {
  return {
    x: pan.x - delta.x,
    y: pan.y - delta.y,
  }
}
