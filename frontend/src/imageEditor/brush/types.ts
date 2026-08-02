export type BrushPointerKind = 'pen' | 'mouse'

/** One device sample in image-pixel coordinates. */
export interface BrushInputSample {
  x: number
  y: number
  time: number
  pressure: number
  tiltX: number
  tiltY: number
  rotation: number
  tangentialPressure: number
  pointer: BrushPointerKind
  eraser: boolean
  /** Derived by the stroke processor, in image pixels per second. */
  velocity: number
  /** Derived direction of travel, in degrees. */
  direction: number
  /** Distance travelled since the beginning of this stroke. */
  distance: number
}

export type DynamicInput =
  | 'pressure'
  | 'speed'
  | 'tilt'
  | 'direction'
  | 'distance'
  | 'random'

export type DynamicTarget =
  | 'size'
  | 'opacity'
  | 'flow'
  | 'rotation'
  | 'aspect'
  | 'scatter'

export interface CurvePoint {
  x: number
  y: number
}

/** Maps one normalized input to a target value between min and max. */
export interface BrushDynamicMapping {
  input: DynamicInput
  target: DynamicTarget
  curve?: CurvePoint[]
  min: number
  max: number
}

export interface ProceduralBrushTip {
  kind: 'ellipse'
  aspect: number
  rotation: number
}

/**
 * Bitmap tips are part of the durable vocabulary now. Rendering imported
 * assets is enabled once the preset asset store has a stable content URL.
 */
export interface BitmapBrushTip {
  kind: 'bitmap'
  assetId: string
  aspect: number
  rotation: number
}

export type BrushTip = ProceduralBrushTip | BitmapBrushTip

export type BrushStabilization =
  | { mode: 'raw' }
  | { mode: 'smooth'; amount: number }
  | { mode: 'stabilized'; radius: number; smoothing: number }

export interface BrushPresetDefinition {
  formatVersion: 1
  id: string
  name: string
  category: 'Basics' | 'Ink' | 'Pencil' | 'Marker' | 'Airbrush' | 'Texture' | 'Eraser'
  base: {
    size: number
    hardness: number
    opacity: number
    flow: number
    spacing: number
  }
  tip: BrushTip
  dynamics: BrushDynamicMapping[]
  stabilization: BrushStabilization
  previewSeed: number
  eraser?: boolean
}

export interface ResolvedBrushDab {
  x: number
  y: number
  size: number
  hardness: number
  opacity: number
  flow: number
  aspect: number
  rotation: number
  tipAssetId?: string
}

export interface PressureCalibration {
  minimum: number
  maximum: number
  curve: CurvePoint[]
}
