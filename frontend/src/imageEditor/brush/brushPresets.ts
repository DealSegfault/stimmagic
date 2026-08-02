import type { BrushSettings } from '../ported/geometry'
import type { BrushPresetDefinition } from './types'

const pressureCurve = [
  { x: 0, y: 0 },
  { x: 0.2, y: 0.12 },
  { x: 0.72, y: 0.78 },
  { x: 1, y: 1 },
]

const firmPressureCurve = [
  { x: 0, y: 0 },
  { x: 0.45, y: 0.18 },
  { x: 0.8, y: 0.72 },
  { x: 1, y: 1 },
]

function preset(
  definition: Omit<BrushPresetDefinition, 'formatVersion' | 'previewSeed'>,
): BrushPresetDefinition {
  let hash = 2166136261
  for (const character of definition.id) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return { formatVersion: 1, previewSeed: hash >>> 0, ...definition }
}

export const BRUSH_PRESETS: readonly BrushPresetDefinition[] = [
  preset({
    id: 'stimma.basic.opaque-round', name: 'Opaque round', category: 'Basics',
    base: { size: 26, hardness: 92, opacity: 100, flow: 100, spacing: 18 },
    tip: { kind: 'ellipse', aspect: 1, rotation: 0 },
    dynamics: [{ input: 'pressure', target: 'size', min: 0.15, max: 1, curve: pressureCurve }],
    stabilization: { mode: 'smooth', amount: 0.15 },
  }),
  preset({
    id: 'stimma.basic.soft-round', name: 'Soft round', category: 'Basics',
    base: { size: 54, hardness: 18, opacity: 100, flow: 34, spacing: 12 },
    tip: { kind: 'ellipse', aspect: 1, rotation: 0 },
    dynamics: [{ input: 'pressure', target: 'flow', min: 0.05, max: 1, curve: pressureCurve }],
    stabilization: { mode: 'smooth', amount: 0.2 },
  }),
  preset({
    id: 'stimma.ink.clean-taper', name: 'Clean taper', category: 'Ink',
    base: { size: 18, hardness: 100, opacity: 100, flow: 100, spacing: 10 },
    tip: { kind: 'ellipse', aspect: 0.78, rotation: 0 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.08, max: 1, curve: pressureCurve },
      { input: 'pressure', target: 'flow', min: 0.25, max: 1, curve: pressureCurve },
      { input: 'direction', target: 'rotation', min: 0, max: 360 },
    ],
    stabilization: { mode: 'stabilized', radius: 2.5, smoothing: 0.18 },
  }),
  preset({
    id: 'stimma.ink.dry-nib', name: 'Dry nib', category: 'Ink',
    base: { size: 24, hardness: 88, opacity: 100, flow: 72, spacing: 17 },
    tip: { kind: 'bitmap', assetId: 'builtin:dry-nib', aspect: 0.28, rotation: 28 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.35, max: 1, curve: firmPressureCurve },
      { input: 'pressure', target: 'flow', min: 0.08, max: 1, curve: firmPressureCurve },
      { input: 'random', target: 'flow', min: 0.45, max: 1 },
    ],
    stabilization: { mode: 'smooth', amount: 0.16 },
  }),
  preset({
    id: 'stimma.pencil.mechanical', name: 'Mechanical pencil', category: 'Pencil',
    base: { size: 7, hardness: 76, opacity: 82, flow: 42, spacing: 12 },
    tip: { kind: 'bitmap', assetId: 'builtin:graphite-fine', aspect: 0.82, rotation: 0 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.55, max: 1, curve: pressureCurve },
      { input: 'pressure', target: 'flow', min: 0.08, max: 1, curve: firmPressureCurve },
      { input: 'random', target: 'scatter', min: 0, max: 0.045 },
    ],
    stabilization: { mode: 'smooth', amount: 0.12 },
  }),
  preset({
    id: 'stimma.pencil.broad', name: 'Broad pencil', category: 'Pencil',
    base: { size: 34, hardness: 54, opacity: 74, flow: 30, spacing: 10 },
    tip: { kind: 'bitmap', assetId: 'builtin:graphite-broad', aspect: 0.22, rotation: 22 },
    dynamics: [
      { input: 'pressure', target: 'flow', min: 0.06, max: 1, curve: pressureCurve },
      { input: 'random', target: 'scatter', min: 0.01, max: 0.06 },
    ],
    stabilization: { mode: 'smooth', amount: 0.1 },
  }),
  preset({
    id: 'stimma.marker.chisel', name: 'Chisel marker', category: 'Marker',
    base: { size: 42, hardness: 94, opacity: 72, flow: 38, spacing: 8 },
    tip: { kind: 'ellipse', aspect: 0.24, rotation: 38 },
    dynamics: [
      { input: 'pressure', target: 'flow', min: 0.35, max: 1, curve: pressureCurve },
    ],
    stabilization: { mode: 'smooth', amount: 0.2 },
  }),
  preset({
    id: 'stimma.marker.round', name: 'Round marker', category: 'Marker',
    base: { size: 30, hardness: 82, opacity: 62, flow: 28, spacing: 8 },
    tip: { kind: 'ellipse', aspect: 0.9, rotation: 0 },
    dynamics: [{ input: 'pressure', target: 'flow', min: 0.28, max: 1, curve: pressureCurve }],
    stabilization: { mode: 'smooth', amount: 0.22 },
  }),
  preset({
    id: 'stimma.airbrush.soft', name: 'Soft airbrush', category: 'Airbrush',
    base: { size: 86, hardness: 4, opacity: 72, flow: 16, spacing: 7 },
    tip: { kind: 'ellipse', aspect: 1, rotation: 0 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.62, max: 1, curve: pressureCurve },
      { input: 'pressure', target: 'flow', min: 0.03, max: 1, curve: pressureCurve },
    ],
    stabilization: { mode: 'smooth', amount: 0.3 },
  }),
  preset({
    id: 'stimma.texture.chalk', name: 'Chalk', category: 'Texture',
    base: { size: 38, hardness: 66, opacity: 82, flow: 38, spacing: 19 },
    tip: { kind: 'bitmap', assetId: 'builtin:chalk', aspect: 0.7, rotation: 0 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.55, max: 1, curve: pressureCurve },
      { input: 'pressure', target: 'flow', min: 0.08, max: 1, curve: firmPressureCurve },
      { input: 'random', target: 'flow', min: 0.28, max: 1 },
      { input: 'random', target: 'scatter', min: 0.02, max: 0.16 },
      { input: 'random', target: 'rotation', min: 0, max: 360 },
    ],
    stabilization: { mode: 'smooth', amount: 0.08 },
  }),
  preset({
    id: 'stimma.texture.spatter', name: 'Spatter', category: 'Texture',
    base: { size: 22, hardness: 90, opacity: 88, flow: 54, spacing: 48 },
    tip: { kind: 'bitmap', assetId: 'builtin:spatter', aspect: 0.72, rotation: 0 },
    dynamics: [
      { input: 'pressure', target: 'size', min: 0.28, max: 1.2, curve: pressureCurve },
      { input: 'random', target: 'size', min: 0.28, max: 1.35 },
      { input: 'random', target: 'scatter', min: 0.12, max: 0.8 },
      { input: 'random', target: 'rotation', min: 0, max: 360 },
    ],
    stabilization: { mode: 'raw' },
  }),
  preset({
    id: 'stimma.eraser.precision', name: 'Precision eraser', category: 'Eraser',
    base: { size: 28, hardness: 94, opacity: 100, flow: 100, spacing: 12 },
    tip: { kind: 'ellipse', aspect: 1, rotation: 0 },
    dynamics: [{ input: 'pressure', target: 'size', min: 0.22, max: 1, curve: pressureCurve }],
    stabilization: { mode: 'smooth', amount: 0.12 }, eraser: true,
  }),
  preset({
    id: 'stimma.eraser.soft', name: 'Soft eraser', category: 'Eraser',
    base: { size: 64, hardness: 16, opacity: 100, flow: 48, spacing: 9 },
    tip: { kind: 'ellipse', aspect: 1, rotation: 0 },
    dynamics: [{ input: 'pressure', target: 'flow', min: 0.06, max: 1, curve: pressureCurve }],
    stabilization: { mode: 'smooth', amount: 0.2 }, eraser: true,
  }),
]

const PRESET_BY_ID = new Map(BRUSH_PRESETS.map(definition => [definition.id, definition]))

export function brushPreset(id: string | undefined, eraser = false): BrushPresetDefinition {
  const found = id ? PRESET_BY_ID.get(id) : undefined
  if (found && !!found.eraser === eraser) return found
  return eraser
    ? PRESET_BY_ID.get('stimma.eraser.precision')!
    : PRESET_BY_ID.get('stimma.basic.opaque-round')!
}

export function settingsForPreset(definition: BrushPresetDefinition): BrushSettings {
  return {
    ...definition.base,
    presetId: definition.id,
    pressureSize: definition.dynamics.some(mapping => mapping.input === 'pressure' && mapping.target === 'size'),
    pressureOpacity: definition.dynamics.some(mapping => mapping.input === 'pressure' && mapping.target === 'flow'),
  }
}

export function isBrushPresetDefinition(value: unknown): value is BrushPresetDefinition {
  if (!value || typeof value !== 'object') return false
  const preset = value as Partial<BrushPresetDefinition>
  return preset.formatVersion === 1
    && typeof preset.id === 'string'
    && typeof preset.name === 'string'
    && !!preset.base
    && !!preset.tip
    && Array.isArray(preset.dynamics)
    && !!preset.stabilization
}
