import type { PaintRange } from './paintEngineSettings'

export interface RetouchBrushAdjustmentSettings {
  exposure: number
  range: PaintRange
  strength: number
  saturate: boolean
}

/**
 * Project a Retouch brush's toolbar settings onto the exact adjustment schema
 * used by its persisted parametric region.
 *
 * Keeping this mapping outside the canvas and view prevents the live stroke
 * and the released result from quietly becoming two different effects again.
 */
export function retouchBrushAdjustmentParams(
  tool: string,
  settings: RetouchBrushAdjustmentSettings,
): Record<string, number> | null {
  switch (tool) {
    case 'dodge':
    case 'burn': {
      const amount = tool === 'dodge' ? settings.exposure : -settings.exposure
      const key = settings.range === 'shadows'
        ? 'shadows'
        : settings.range === 'highlights' ? 'highlights' : 'exposure'
      return { [key]: amount }
    }
    case 'sponge':
      return { saturation: settings.saturate ? settings.strength : -settings.strength }
    // Strength is 1–100; the adjustment renderer's blur scale is 0–40.
    case 'blur':
      return { blur: Math.max(1, Math.round(settings.strength * 0.4)) }
    case 'sharpen':
      return { sharpen: settings.strength }
    default:
      return null
  }
}
