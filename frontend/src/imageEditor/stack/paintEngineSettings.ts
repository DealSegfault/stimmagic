import type { BrushSettings } from '../ported/geometry'
import type { GradientPaint } from '../ported/shapeTypes'

export type PaintRange = 'shadows' | 'midtones' | 'highlights'
export type PaintGradientType = 'linear' | 'radial' | 'angle' | 'reflected' | 'diamond'

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
  /** Spectrum and geometry used by the Gradient tool's next drag. */
  gradient: GradientPaint
  gradientType: PaintGradientType
  gradientReverse: boolean
  exposure: number
  range: PaintRange
  strength: number
  saturate: boolean
}

const DEFAULT_COLOR: PaintColor = { r: 201, g: 162, b: 118, a: 1 }
const DEFAULT_GRADIENT: GradientPaint = {
  type: 'gradient',
  colors: [
    { r: 201, g: 162, b: 118, a: 1 },
    { r: 174, g: 118, b: 201, a: 1 },
  ],
  // The canvas drag owns the direction; horizontal is the neutral preview.
  direction: 'horizontal',
}

/**
 * Stylus dynamics default to pressure→flow for every engine: dodging harder
 * dodges more, painting harder lays down more paint. Pressure→size is a
 * hand-lettering behavior, so only Paint starts with it on. Both are plain
 * brush toggles from there.
 */
function brush(
  size: number,
  hardness: number,
  opacity = 100,
  flow = 100,
  spacing = 25,
  pressureSize = false,
  presetId?: string,
): BrushSettings {
  return {
    size, hardness, opacity, flow, spacing, pressureSize, pressureOpacity: true,
    ...(presetId ? { presetId } : {}),
  }
}

/**
 * Conservative starting points for pixel-reading Paint engines.
 *
 * The effect engines intentionally begin soft and low-strength. A person can
 * turn them up for a dramatic pass; the default should survive several passes
 * over the same area without immediately clipping or looking painted on.
 */
type PaintEngineDefaults = Omit<
  PaintEngineSettings,
  'gradient' | 'gradientType' | 'gradientReverse'
>

const DEFAULTS: Record<string, PaintEngineDefaults> = {
  paint: {
    brush: brush(26, 92, 100, 100, 18, true, 'stimma.basic.opaque-round'),
    color: DEFAULT_COLOR,
    exposure: 10,
    range: 'midtones',
    strength: 20,
    saturate: true,
  },
  erase: {
    brush: brush(28, 94, 100, 100, 12, true, 'stimma.eraser.precision'),
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
  gradient: {
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

function gradientPaint(value: GradientPaint | undefined): GradientPaint {
  const raw = value?.type === 'gradient' && Array.isArray(value.colors)
    ? value.colors
    : []
  const colors = raw.slice(0, 8).map(color => ({
    r: clamp(color?.r, 0, 255, DEFAULT_COLOR.r),
    g: clamp(color?.g, 0, 255, DEFAULT_COLOR.g),
    b: clamp(color?.b, 0, 255, DEFAULT_COLOR.b),
    a: clamp(color?.a, 0, 1, DEFAULT_COLOR.a),
  }))
  return {
    type: 'gradient',
    colors: colors.length >= 2
      ? colors
      : DEFAULT_GRADIENT.colors.map(color => ({ ...color })),
    direction: 'horizontal',
  }
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
  const gradientType = stored?.gradientType

  return {
    brush: {
      size: clamp(storedBrush?.size, 1, 100, fallback.brush.size),
      hardness: clamp(storedBrush?.hardness, 0, 100, fallback.brush.hardness),
      opacity: clamp(storedBrush?.opacity, 0, 100, fallback.brush.opacity),
      flow: clamp(storedBrush?.flow, 0, 100, fallback.brush.flow),
      spacing: clamp(storedBrush?.spacing, 1, 100, fallback.brush.spacing),
      pressureSize: typeof storedBrush?.pressureSize === 'boolean'
        ? storedBrush.pressureSize
        : fallback.brush.pressureSize,
      pressureOpacity: typeof storedBrush?.pressureOpacity === 'boolean'
        ? storedBrush.pressureOpacity
        : fallback.brush.pressureOpacity,
      ...(typeof storedBrush?.presetId === 'string'
        ? { presetId: storedBrush.presetId }
        : !storedBrush && fallback.brush.presetId
          ? { presetId: fallback.brush.presetId }
          : {}),
    },
    color: {
      r: clamp(storedColor?.r, 0, 255, fallback.color.r),
      g: clamp(storedColor?.g, 0, 255, fallback.color.g),
      b: clamp(storedColor?.b, 0, 255, fallback.color.b),
      a: clamp(storedColor?.a, 0, 1, fallback.color.a),
    },
    gradient: gradientPaint(stored?.gradient),
    gradientType: gradientType === 'linear'
      || gradientType === 'radial'
      || gradientType === 'angle'
      || gradientType === 'reflected'
      || gradientType === 'diamond'
      ? gradientType
      : 'linear',
    gradientReverse: typeof stored?.gradientReverse === 'boolean'
      ? stored.gradientReverse
      : false,
    exposure: clamp(stored?.exposure, 1, 100, fallback.exposure),
    range: range === 'shadows' || range === 'midtones' || range === 'highlights'
      ? range
      : fallback.range,
    strength: clamp(stored?.strength, 1, 100, fallback.strength),
    saturate: typeof stored?.saturate === 'boolean' ? stored.saturate : fallback.saturate,
  }
}
