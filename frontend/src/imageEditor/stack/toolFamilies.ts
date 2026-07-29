/**
 * The six tool families and their sub-tools — the MVP toolset, a superset of
 * the snapshot editor's plugins.
 *
 * Clicking a family enters a MODE and opens its sub-toolbar. It never edits the
 * stack: the step is created on the first real gesture — a paint stroke, a
 * Levels slider, placed text, an explicit Run. Empty steps cannot exist, and
 * Esc leaves a mode with nothing to undo.
 *
 * Icons are inner-SVG fragments in the same shape `taskTypeIcons` uses, so they
 * render through the same 24×24 `currentColor` wrapper as every other tool
 * glyph in the app.
 */

import type { IconName } from '../ported/icons'

export type FamilyId =
  | 'generate' | 'crop' | 'paint'
  | 'levels' | 'filters'
  | 'annotate'

export interface SubTool {
  id: string
  label: string
  /** A glyph from the ported registry; the label becomes its tooltip. */
  icon?: IconName
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

export const FAMILY_ICONS: Record<FamilyId | 'select', string> = {
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
  // Sliders for Levels, a stack of frames for Filters — the two doorways read
  // as two different jobs at a glance.
  levels:
    '<line x1="4" y1="7" x2="20" y2="7"/><circle cx="14" cy="7" r="2.2"/>'
    + '<line x1="4" y1="12" x2="20" y2="12"/><circle cx="8" cy="12" r="2.2"/>'
    + '<line x1="4" y1="17" x2="20" y2="17"/><circle cx="16" cy="17" r="2.2"/>',
  filters:
    '<rect x="3" y="3" width="13" height="13" rx="2"/>'
    + '<path d="M8 21h11a2 2 0 0 0 2-2V8"/>',
  annotate:
    '<path d="M4 7V5h16v2"/><path d="M9 19h6"/><path d="M12 5v14"/>',
}

export const TOOL_FAMILIES: ToolFamily[] = [
  {
    id: 'generate',
    label: 'Generate',
    key: 'g',
    icon: FAMILY_ICONS.generate,
    // Both sub-tools are masked patches, and that is the whole family: a
    // generative step that replaced the entire composite would occlude the
    // stack below it, which makes it a new base rather than a step. Whole
    // image is gone; Upscale moved to the output stage, which produces a saved
    // version instead of a row.
    defaultSub: 'inpaint',
    subTools: [
      { id: 'inpaint', label: 'Inpaint' },
      { id: 'expand', label: 'Expand' },
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
    id: 'paint',
    label: 'Retouch',
    key: 'p',
    icon: FAMILY_ICONS.paint,
    defaultSub: null,
    subTools: [],
  },
  // Levels and Filters are two doorways into the same adjust pipeline. Levels
  // offers the dial edits (Tone, Detail, Tint, the Autos); Filters offers the
  // strip of picked-by-eye looks, including the pixel looks that used to be a
  // separate Effects family. Every entry in both is an ADD: click, get a
  // focused step, edit it in Properties.
  {
    id: 'levels',
    label: 'Levels',
    key: 'l',
    icon: FAMILY_ICONS.levels,
    defaultSub: null,
    subTools: [],
  },
  {
    id: 'filters',
    label: 'Filters',
    key: 'f',
    icon: FAMILY_ICONS.filters,
    defaultSub: null,
    subTools: [],
  },
  {
    id: 'annotate',
    label: 'Annotate',
    key: 'a',
    icon: FAMILY_ICONS.annotate,
    // No 'select' sub-tool: object selection is the workspace's IDLE state
    // (and the island's pointer), not an annotate mode. Inside the family,
    // `sub = null` is select — where every drawing tool lands after its
    // one-shot creation.
    defaultSub: 'arrow',
    subTools: [
      { id: 'arrow', label: 'Arrow', icon: 'arrowUpRight' },
      { id: 'draw', label: 'Draw', icon: 'pencil' },
      { id: 'rectangle', label: 'Rectangle', icon: 'square' },
      { id: 'ellipse', label: 'Ellipse', icon: 'circle' },
      { id: 'line', label: 'Line', icon: 'slash' },
      { id: 'text', label: 'Text', icon: 'type' },
      { id: 'redact', label: 'Redact', icon: 'redact' },
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
  icon: IconName
  /** Reads the composite below rather than laying down the color. */
  readsPixels?: boolean
  /** Not yet implemented. */
  pending?: boolean
}

export const PAINT_ENGINES: PaintEngine[] = [
  // The tip — soft, hard, ink, airbrush — is chosen in the brush picker that
  // hangs off the toolbar, so there is one Brush engine rather than one chip
  // per shape. What is listed here is what the engine DOES, which is the part
  // the picker cannot express.
  { id: 'paint', label: 'Brush', icon: 'paintbrush' },
  { id: 'fill', label: 'Fill', icon: 'fill' },
  { id: 'blur', label: 'Blur', icon: 'droplet', readsPixels: true },
  { id: 'sharpen', label: 'Sharpen', icon: 'focus', readsPixels: true },
  { id: 'dodge', label: 'Dodge', icon: 'sun', readsPixels: true },
  { id: 'burn', label: 'Burn', icon: 'moon', readsPixels: true },
  { id: 'sponge', label: 'Sponge', icon: 'sponge', readsPixels: true },
  { id: 'heal', label: 'Heal', icon: 'bandage', readsPixels: true },
  // Patch is selection-driven, not stroke-driven: select the flaw, drag it
  // over clean pixels. Picking it with no selection arms the lasso.
  { id: 'patch', label: 'Patch', icon: 'patch', readsPixels: true },
  { id: 'clone', label: 'Clone', icon: 'stamp', readsPixels: true },
]

export const PAINT_SWATCHES = [
  '#ffffff', '#000000', '#c9a276', '#5d4128', '#b0342c', '#2a4a6b', '#3f7a4f',
]

/**
 * The selection tools, on the rail at the left of the canvas — not a family.
 *
 * Selection is workspace state, not a mode: it cuts across every family (an
 * inpaint mask, a paint clip, an adjustment's region), so its tools live in
 * chrome that is always reachable rather than behind a mode that would have to
 * end the one you are in. Arming one SUSPENDS the open family — the pointer
 * belongs to the selection until it is disarmed, and the family's session, step
 * and controls all survive underneath.
 */
export type SelectToolId = 'rect' | 'ellipse' | 'lasso' | 'magnetic' | 'wand' | 'brush'

export const SELECT_TOOLS: Array<{ id: SelectToolId; label: string; icon: IconName }> = [
  { id: 'rect', label: 'Rectangle', icon: 'squareDashed' },
  { id: 'ellipse', label: 'Ellipse', icon: 'circleDashed' },
  { id: 'lasso', label: 'Lasso', icon: 'lasso' },
  { id: 'magnetic', label: 'Magnetic', icon: 'magnetLasso' },
  { id: 'wand', label: 'Wand', icon: 'wand' },
  // Painting a selection is how most inpaint masks get made, which is why the
  // brush is a selection tool rather than a Generate-only surface.
  { id: 'brush', label: 'Brush', icon: 'paintbrush' },
]

/** Combine modes for Select — how a new selection meets the existing one. */
export const SELECTION_MODES = [
  { id: 'new', label: 'New', icon: 'selectionNew' },
  { id: 'add', label: 'Add', icon: 'selectionAdd' },
  { id: 'subtract', label: 'Subtract', icon: 'selectionSubtract' },
  { id: 'intersect', label: 'Intersect', icon: 'selectionIntersect' },
] as const

export type SelectionMode = typeof SELECTION_MODES[number]['id']

/**
 * Text style presets live in textStyles.ts, next to the property mapping they
 * stand for — the toolbar and the inspector both need that mapping, and a bare
 * list of labels here let the two drift apart.
 */
export { TEXT_STYLES } from './textStyles'

export const SHAPE_KINDS = [
  { id: 'rectangle', label: 'Rectangle', icon: 'square' },
  { id: 'ellipse', label: 'Ellipse', icon: 'circle' },
  { id: 'line', label: 'Line', icon: 'slash' },
] as const
