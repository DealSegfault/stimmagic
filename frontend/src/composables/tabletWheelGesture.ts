export interface TabletWheelGestureState {
  lastPointAt: number
  latched: boolean
}

// Wacom stops sending tablet-point samples while Pan/Scroll owns the pen and
// emits wheel events instead. Allow the first wheel event to claim the gesture
// shortly after a pen sample; once claimed, keep it claimed until tablet input
// resumes or the pen leaves proximity.
const WHEEL_GESTURE_SEED_MS = 2_000

export function createTabletWheelGestureState(): TabletWheelGestureState {
  return { lastPointAt: Number.NEGATIVE_INFINITY, latched: false }
}

export function noteTabletPointForWheelGesture(
  state: TabletWheelGestureState,
  phase: 'down' | 'move' | 'up' | 'hover',
  now: number,
): void {
  if (phase === 'up') {
    state.lastPointAt = Number.NEGATIVE_INFINITY
    state.latched = false
    return
  }
  state.lastPointAt = now
  if (phase === 'down' || phase === 'hover') {
    state.latched = false
  }
}

export function releaseTabletWheelGesture(state: TabletWheelGestureState): void {
  state.latched = false
}

export function claimTabletWheelGesture(
  state: TabletWheelGestureState,
  now: number,
  penInProximity: boolean,
  mouseStroke: boolean,
): boolean {
  if (!penInProximity || mouseStroke) {
    state.latched = false
    return false
  }
  if (state.latched) return true
  if (now - state.lastPointAt > WHEEL_GESTURE_SEED_MS) return false
  state.latched = true
  return true
}
