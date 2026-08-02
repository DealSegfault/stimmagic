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
 * Tame Wacom Pan/Scroll's driver-generated velocity spikes.
 *
 * The driver has already chosen an axis and converted pen displacement into
 * scrolling speed, so exact positional recovery is impossible. A modest gain
 * plus a hard per-event ceiling keeps the generic behavior controllable and
 * prevents one late vertical sample from flinging the canvas across the view.
 */
export function stabilizeWacomWheelDelta(delta: ViewportPoint): ViewportPoint {
  const stabilize = (value: number) => {
    const scaled = value * 0.12
    return Math.max(-4, Math.min(4, scaled))
  }
  return { x: stabilize(delta.x), y: stabilize(delta.y) }
}

/** Keep this much content reachable when it is pushed toward a viewport edge. */
const PAN_GRIP = 64

function panLimit(contentSpan: number, viewportSpan: number): number {
  const grip = Math.min(PAN_GRIP, contentSpan / 2)
  return Math.max(0, (viewportSpan + contentSpan) / 2 - grip)
}

/**
 * Let the image move throughout the workspace while keeping a recoverable grip
 * visible at every edge. This deliberately permits much more movement than a
 * small overscroll allowance: a hand-tool drag should feel like pushing the
 * canvas, including at fit and on the viewport's shorter axis.
 */
export function clampViewportPan(
  pan: ViewportPoint,
  zoom: number,
  content: ViewportSize,
  viewport: ViewportSize,
): ViewportPoint {
  const maxX = panLimit(content.width * zoom, viewport.width)
  const maxY = panLimit(content.height * zoom, viewport.height)
  return {
    x: Math.max(-maxX, Math.min(maxX, pan.x)),
    y: Math.max(-maxY, Math.min(maxY, pan.y)),
  }
}

/**
 * Apply one drag sample to the already-clamped pan position.
 *
 * Keeping the pointer origin out of this calculation is important at an edge:
 * movement beyond the bound is discarded, so reversing the pen moves the
 * viewport immediately instead of first retracing an invisible overshoot.
 */
export function panForDragDelta(
  pan: ViewportPoint,
  delta: ViewportPoint,
  zoom: number,
  content: ViewportSize,
  viewport: ViewportSize,
): ViewportPoint {
  return clampViewportPan(
    { x: pan.x + delta.x, y: pan.y + delta.y },
    zoom,
    content,
    viewport,
  )
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
