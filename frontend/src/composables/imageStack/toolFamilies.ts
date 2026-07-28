/**
 * The six tool families and their sub-tools — the MVP toolset, a superset of
 * the snapshot editor's plugins.
 *
 * Clicking a family enters a MODE and opens its sub-toolbar. It never edits the
 * stack: the step is created on the first real gesture — a paint stroke, a
 * Develop slider, placed text, an explicit Run. Empty steps cannot exist, and
 * Esc leaves a mode with nothing to undo.
 *
 * Icons are inner-SVG fragments in the same shape `taskTypeIcons` uses, so they
 * render through the same 24×24 `currentColor` wrapper as every other tool
 * glyph in the app.
 */

export type FamilyId = 'generate' | 'crop' | 'select' | 'paint' | 'develop' | 'annotate'

export interface SubTool {
  id: string
  label: string
  /** Not yet implemented; shown so the shape of the family is honest. */
  pending?: boolean
}

export interface ToolFamily {
  id: FamilyId
  label: string
  /** Keyboard shortcut, single key. */
  key: string
  icon: string
  subTools: SubTool[]
  defaultSub: string | null
}

export const FAMILY_ICONS: Record<FamilyId, string> = {
  // Sparkle: every model-backed verb lives under one family, and the family
  // name is what carries the cost meaning.
  generate:
    '<path d="M12 3l1.9 5.9L20 11l-6.1 2.1L12 19l-1.9-5.9L4 11l6.1-2.1z" fill="currentColor" stroke="none"/>'
    + '<path d="M19 3l.8 2.2L22 6l-2.2.8L19 9l-.8-2.2L16 6l2.2-.8z" fill="currentColor" stroke="none"/>',
  crop:
    '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M2 6h14a2 2 0 0 1 2 2v14"/>',
  select:
    '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="4 3"/>',
  paint:
    '<path d="M9.1 11.9l8.1-8.1a2.85 2.85 0 1 1 4 4l-8.1 8.1"/>'
    + '<path d="M7.1 14.9c-1.7 0-3 1.4-3 3 0 1.3-1.5 2-2 2 1.1 1.1 2.5 2 4 2 2.2 0 4-1.8 4-4a3 3 0 0 0-3-3z"/>',
  develop:
    '<line x1="4" y1="7" x2="20" y2="7"/><circle cx="14" cy="7" r="2.2"/>'
    + '<line x1="4" y1="12" x2="20" y2="12"/><circle cx="8" cy="12" r="2.2"/>'
    + '<line x1="4" y1="17" x2="20" y2="17"/><circle cx="16" cy="17" r="2.2"/>',
  annotate:
    '<path d="M4 7V5h16v2"/><path d="M9 19h6"/><path d="M12 5v14"/>',
}

export const TOOL_FAMILIES: ToolFamily[] = [
  {
    id: 'generate',
    label: 'Generate',
    key: 'g',
    icon: FAMILY_ICONS.generate,
    defaultSub: 'inpaint',
    subTools: [
      { id: 'inpaint', label: 'Inpaint' },
      { id: 'whole', label: 'Whole image' },
      { id: 'expand', label: 'Expand' },
      { id: 'upscale', label: 'Upscale' },
    ],
  },
  {
    id: 'crop',
    label: 'Crop',
    key: 'c',
    icon: FAMILY_ICONS.crop,
    defaultSub: null,
    subTools: [],
  },
  {
    id: 'select',
    label: 'Select',
    key: 's',
    icon: FAMILY_ICONS.select,
    defaultSub: 'rect',
    subTools: [
      { id: 'rect', label: 'Rectangle' },
      { id: 'ellipse', label: 'Ellipse' },
      { id: 'lasso', label: 'Lasso' },
      { id: 'brush', label: 'Brush' },
      { id: 'magnetic', label: 'Magnetic' },
      { id: 'wand', label: 'Wand' },
    ],
  },
  {
    id: 'paint',
    label: 'Paint',
    key: 'p',
    icon: FAMILY_ICONS.paint,
    defaultSub: null,
    subTools: [],
  },
  {
    id: 'develop',
    label: 'Develop',
    key: 'd',
    icon: FAMILY_ICONS.develop,
    defaultSub: 'light',
    subTools: [
      { id: 'light', label: 'Light' },
      { id: 'colour', label: 'Colour' },
      { id: 'film', label: 'Film' },
      { id: 'effects', label: 'Effects' },
    ],
  },
  {
    id: 'annotate',
    label: 'Annotate',
    key: 'a',
    icon: FAMILY_ICONS.annotate,
    defaultSub: 'text',
    subTools: [
      { id: 'text', label: 'Text' },
      { id: 'shape', label: 'Shape' },
      { id: 'redact', label: 'Redact' },
      { id: 'sticker', label: 'Sticker', pending: true },
      { id: 'frame', label: 'Frame', pending: true },
    ],
  },
]

export function familyById(id: FamilyId): ToolFamily {
  return TOOL_FAMILIES.find(family => family.id === id)!
}

/**
 * Paint engines as chips, Krita-style. Heal, Clone, Dodge, Burn and Blur are
 * ENGINES, not separate tools — the thing the user picks is a brush, and what
 * differs is how it lays down pixels.
 *
 * The pixel-reading engines (heal, clone, dodge, burn, blur) sample the
 * composite below, which is why their layers carry an advisory hash like
 * patches do.
 */
export interface PaintEngine {
  id: string
  label: string
  hardness: number
  flow: number
  /** Reads the composite below rather than laying down the colour. */
  readsPixels?: boolean
  /** Not yet implemented. */
  pending?: boolean
}

export const PAINT_ENGINES: PaintEngine[] = [
  // The tip — soft, hard, ink, airbrush — is chosen in the brush picker that
  // hangs off the toolbar, so there is one Brush engine rather than one chip
  // per shape. What is listed here is what the engine DOES, which is the part
  // the picker cannot express.
  { id: 'paint', label: 'Brush', hardness: 0.6, flow: 1 },
  { id: 'fill', label: 'Fill', hardness: 1, flow: 1 },
  { id: 'blur', label: 'Blur', hardness: 0.3, flow: 0.6, readsPixels: true },
  { id: 'sharpen', label: 'Sharpen', hardness: 0.3, flow: 0.6, readsPixels: true },
  { id: 'dodge', label: 'Dodge', hardness: 0.3, flow: 0.4, readsPixels: true },
  { id: 'burn', label: 'Burn', hardness: 0.3, flow: 0.4, readsPixels: true },
  { id: 'sponge', label: 'Sponge', hardness: 0.3, flow: 0.4, readsPixels: true },
  { id: 'heal', label: 'Heal', hardness: 0.4, flow: 1, readsPixels: true },
  { id: 'clone', label: 'Clone', hardness: 0.4, flow: 1, readsPixels: true },
]

export const PAINT_SWATCHES = [
  '#ffffff', '#000000', '#c9a276', '#5d4128', '#b0342c', '#2a4a6b', '#3f7a4f',
]

/** Combine modes for Select — how a new selection meets the existing one. */
export const SELECTION_MODES = [
  { id: 'new', label: 'New' },
  { id: 'add', label: 'Add' },
  { id: 'subtract', label: 'Subtract' },
  { id: 'intersect', label: 'Intersect' },
] as const

export type SelectionMode = typeof SELECTION_MODES[number]['id']

/** Text style presets, parity with the annotate plugin's text effects. */
export const TEXT_STYLES = [
  { id: 'pill', label: 'Pill' },
  { id: 'plain', label: 'Plain' },
  { id: 'outline', label: 'Outline' },
  { id: 'neon', label: 'Neon' },
] as const

export const SHAPE_KINDS = [
  { id: 'rectangle', label: 'Rectangle' },
  { id: 'ellipse', label: 'Ellipse' },
  { id: 'line', label: 'Line' },
] as const
