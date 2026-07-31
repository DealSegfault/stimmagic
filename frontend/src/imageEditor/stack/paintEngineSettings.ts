import type { BrushSettings } from '../ported/geometry'

export type PaintRange = 'shadows' | 'midtones' | 'highlights'

export interface PaintColor {
  r: number
  g: number
  b: number
  a: number
}

/**
 * Sticky input conditions for one Paint engine.
 *
 * These are tool preferences, not layer data: they describe what the next
 * gesture will do. Keeping a complete record per engine means a soft, low-flow
 * Dodge brush does not turn into the Heal or Clone brush when the chips change.
 */
export interface PaintEngineSettings {
  brush: BrushSettings
  color: PaintColor
  exposure: number
  range: PaintRange
  strength: number
  saturate: boolean
}

const DEFAULT_COLOR: PaintColor = { r: 201, g: 162, b: 118, a: 1 }

function brush(
  size: number,
  hardness: number,
  opacity = 100,
  flow = 100,
  spacing = 25,
): BrushSettings {
  return { size, hardness, opacity, flow, spacing }
}

/**
 * Conservative starting points for pixel-reading Paint engines.
 *
 * The effect engines intentionally begin soft and low-strength. A person can
 * turn them up for a dramatic pass; the default should survive several passes
 * over the same area without immediately clipping or looking painted on.
 */
const DEFAULTS: Record<string, PaintEngineSettings> = {
  paint: {
    brush: brush(26, 60),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  fill: {
    brush: brush(26, 100),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  blur: {
    brush: brush(50, 20),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  sharpen: {
    brush: brush(50, 20),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 15,
    saturate: true,
  },
  dodge: {
    brush: brush(50, 20),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  burn: {
    brush: brush(50, 20),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  sponge: {
    brush: brush(50, 20),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  heal: {
    brush: brush(32, 40),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  patch: {
    brush: brush(32, 100),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  clone: {
    brush: brush(32, 40),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function clamp(value: unknown, min: number, max: number, fallback: number): number {
  return Math.min(max, Math.max(min, finiteNumber(value, fallback)))
}

/** Read persisted settings defensively; old or corrupt preferences fall back narrowly. */
export function paintEngineSettings(
  engineId: string,
  stored?: Partial<PaintEngineSettings> | null,
): PaintEngineSettings {
  const fallback = DEFAULTS[engineId] ?? DEFAULTS.paint
  const storedBrush = stored?.brush
  const storedColor = stored?.color
  const range = stored?.range

  return {
    brush: {
      size: clamp(storedBrush?.size, 1, 100, fallback.brush.size),
      hardness: clamp(storedBrush?.hardness, 0, 100, fallback.brush.hardness),
      opacity: clamp(storedBrush?.opacity, 0, 100, fallback.brush.opacity),
      flow: clamp(storedBrush?.flow, 0, 100, fallback.brush.flow),
      spacing: clamp(storedBrush?.spacing, 1, 100, fallback.brush.spacing),
    },
    color: {
      r: clamp(storedColor?.r, 0, 255, fallback.color.r),
      g: clamp(storedColor?.g, 0, 255, fallback.color.g),
      b: clamp(storedColor?.b, 0, 255, fallback.color.b),
      a: clamp(storedColor?.a, 0, 1, fallback.color.a),
    },
    exposure: clamp(stored?.exposure, 1, 100, fallback.exposure),
    range: range === 'shadows' || range === 'midtones' || range === 'highlights'
      ? range
      : fallback.range,
    strength: clamp(stored?.strength, 1, 100, fallback.strength),
    saturate: typeof stored?.saturate === 'boolean' ? stored.saturate : fallback.saturate,
  }
}
