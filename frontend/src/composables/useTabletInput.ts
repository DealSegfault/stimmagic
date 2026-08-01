/**
 * Stylus (graphics tablet) pressure, merged from two sources:
 *
 * - Real pen pointer events (Chromium/WebView2 on Windows): pressure arrives
 *   on the PointerEvent itself, recognizable by `pointerType === 'pen'`.
 * - The native `tablet-input` stream (macOS, src-tauri/src/tablet.rs):
 *   WKWebView reports tablet input as a plain mouse pointer with no usable
 *   pressure, so an NSEvent monitor forwards it and it is matched to DOM
 *   pointer events here.
 *
 * The match is per stroke, not per proximity: a pen PARKED on the tablet
 * keeps it in proximity indefinitely while the person draws with the mouse,
 * and those mouse strokes must not inherit the pen's resting pressure of
 * zero. The native stream therefore marks plain mouse strokes explicitly
 * (`mouseStroke`), and pen state only applies while the pen is actually
 * pressed (`penDown`) or actively producing samples — a parked pen produces
 * none. Hover samples cover the stroke's first dab: the native "down" emit
 * can reach JS after the DOM pointerdown it belongs to, but the pen always
 * hovers in before touching, so the stream is already fresh.
 *
 * With no pen involved, `tabletPressureFor` returns null and callers treat
 * the input as a mouse.
 */
import { isTauri } from '../apiConfig'
import { listen } from '@tauri-apps/api/event'

type TabletInputPayload =
  | {
      kind: 'point'
      phase: 'down' | 'move' | 'up' | 'hover'
      pressure: number
      tiltX: number
      tiltY: number
    }
  | { kind: 'proximity'; entering: boolean; eraser: boolean }
  | { kind: 'mouseStroke'; down: boolean }

/** How recent a native sample must be to speak for the current DOM event. */
const SAMPLE_FRESH_MS = 150

const native = {
  penDown: false,
  mouseStroke: false,
  pressure: 0,
  tiltX: 0,
  tiltY: 0,
  eraser: false,
  lastSampleAt: 0,
}

let started = false

function ensureListening(): void {
  if (started) return
  started = true
  if (!isTauri()) return
  listen<TabletInputPayload>('tablet-input', ({ payload }) => {
    if (payload.kind === 'point') {
      native.pressure = Math.max(0, Math.min(1, payload.pressure))
      native.tiltX = payload.tiltX
      native.tiltY = payload.tiltY
      native.lastSampleAt = performance.now()
      if (payload.phase === 'down') {
        native.penDown = true
        native.mouseStroke = false
      }
      if (payload.phase === 'up') {
        native.penDown = false
        native.pressure = 0
      }
    } else if (payload.kind === 'proximity') {
      native.eraser = payload.entering && payload.eraser
      if (!payload.entering) {
        native.penDown = false
        native.pressure = 0
        native.lastSampleAt = 0
      }
    } else {
      native.mouseStroke = payload.down
      if (payload.down) native.penDown = false
    }
  }).catch(() => {
    // Not fatal: strokes fall back to mouse behavior.
  })
}

/**
 * Pressure for a pointer event, in [0, 1] — or null when no stylus is
 * involved and the stroke should behave exactly as a mouse stroke.
 */
export function tabletPressureFor(event: PointerEvent): number | null {
  ensureListening()
  if (event.pointerType === 'pen') return event.pressure
  if (native.mouseStroke) return null
  if (native.penDown) return native.pressure
  if (performance.now() - native.lastSampleAt < SAMPLE_FRESH_MS) return native.pressure
  return null
}
