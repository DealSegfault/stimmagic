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

/**
 * Family glyphs. Where the snapshot editor already has the mark (crop, sliders,
 * pencil, retouch), we use ITS icon so a tool looks like itself across both
 * editors; Generate and Select are new verbs and get new marks drawn to match.
 */
export const FAMILY_ICONS: Record<FamilyId, string> = {
  // Generate and Select are new verbs, so they get new marks. The rest reuse
  // the snapshot editor's own icons via `editorIcons` below.
  generate:
    '<path d="M12 3l1.9 5.9L20 11l-6.1 2.1L12 19l-1.9-5.9L4 11l6.1-2.1z" fill="currentColor" stroke="none"/>'
    + '<path d="M19 3l.8 2.2L22 6l-2.2.8L19 9l-.8-2.2L16 6l2.2-.8z" fill="currentColor" stroke="none"/>',
  crop: '',
  select: '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="4 3"/>',
  paint: '',
  develop: '',
  annotate: '',
}

/**
 * The snapshot editor's icon ids for the families it already owns. Using ITS
 * marks means a tool looks like itself across both editors instead of two
 * near-miss drawings of the same thing.
 */
export const FAMILY_EDITOR_ICON: Partial<Record<FamilyId, string>> = {
  crop: 'crop',
  paint: 'retouch',
  develop: 'sliders',
  annotate: 'pencil',
}

/**
 * Which snapshot-editor plugin owns a family's controls. Generate is the only
 * family with no counterpart — it is the new capability.
 *
 * Select and Paint both map to the retouch plugin because that is where the
 * selection suite and the brush engines actually live; the family only decides
 * which half the user came for.
 */
export const FAMILY_PLUGIN: Partial<Record<FamilyId, string>> = {
  crop: 'crop',
  select: 'retouch',
  paint: 'retouch',
  develop: 'finetune',
  annotate: 'annotate',
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
  // Crop, Select, Paint and Annotate carry no sub-tool row of ours: their
  // plugin panel already presents the tools, and duplicating that in a strip
  // above it would be a second, worse copy of the same choice.
  { id: 'crop', label: 'Crop', key: 'c', icon: FAMILY_ICONS.crop, defaultSub: null, subTools: [] },
  { id: 'select', label: 'Select', key: 's', icon: FAMILY_ICONS.select, defaultSub: null, subTools: [] },
  { id: 'paint', label: 'Paint', key: 'p', icon: FAMILY_ICONS.paint, defaultSub: null, subTools: [] },
  {
    id: 'develop',
    label: 'Develop',
    key: 'd',
    icon: FAMILY_ICONS.develop,
    defaultSub: 'light',
    // Develop spans three of the old plugins; the sub-tool picks which panel is
    // in front, because the stack's unit is a develop session, not a plugin tab.
    subTools: [
      { id: 'light', label: 'Light' },
      { id: 'colour', label: 'Colour' },
      { id: 'film', label: 'Film' },
      { id: 'effects', label: 'Effects' },
    ],
  },
  { id: 'annotate', label: 'Annotate', key: 'a', icon: FAMILY_ICONS.annotate, defaultSub: null, subTools: [] },
]

export function familyById(id: FamilyId): ToolFamily {
  return TOOL_FAMILIES.find(family => family.id === id)!
}

/**
 * Selection combine modes, kept only because the op stack needs the vocabulary
 * when a selection becomes a region. Every other brush, engine, swatch and text
 * style now comes from the plugin panels rather than from a second list here.
 */
export const SELECTION_MODES = [
  { id: 'new', label: 'New' },
  { id: 'add', label: 'Add' },
  { id: 'subtract', label: 'Subtract' },
  { id: 'intersect', label: 'Intersect' },
] as const

export type SelectionMode = typeof SELECTION_MODES[number]['id']
