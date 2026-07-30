/**
 * Sticky tool picks — which tool is armed, not what it produced.
 *
 * A pick is a PREFERENCE, not part of the document: reaching for Patch, or the
 * lasso, or a particular inpaint provider says how this person works, and it
 * outlives both the image it was picked on and the window it was picked in.
 * The palette's recents already work this way; the rest of the toolbar didn't,
 * so every reload dropped the user back on Brush.
 *
 * What is NOT here: anything a step owns (a crop, a stroke, a shape) and the
 * transient landing states between gestures — `sub = null` after a one-shot
 * annotation is where the tool went, not what the user picked.
 *
 * One profile-scoped record rather than a key per pick, so two profiles never
 * inherit each other's provider and a read is one parse.
 */

import { makeProfileKey } from '../../utils/storageKeys'
import type { PaintEngineSettings } from './paintEngineSettings'

export interface ToolPrefs {
  /**
   * The open tool family. This is the pick the toolbar SHOWS as selected, so
   * without it the other picks are invisible on return: the editor came back
   * with nothing armed and the remembered engine sat behind a family the user
   * had to re-enter by hand.
   */
  family?: string | null
  /** Rail selection tool, restored for the `s` shortcut and first arm. */
  selectTool?: string
  /** Paint family engine chip — Brush, Patch, Clone… */
  paintEngineId?: string
  /** Brush and engine controls, remembered independently for each Paint engine. */
  paintEngines?: Record<string, Partial<PaintEngineSettings>>
  /** Brush used to author region-based Retouch repairs. */
  retouchBrush?: Partial<PaintEngineSettings['brush']>
  /** @deprecated Read only as a migration fallback for Expand/Repaint. */
  inpaintToolId?: string
  /** Catalog tool used to fill an expanded canvas border. */
  expandToolId?: string
  /** Catalog tool used by Retouch → Repaint (`inpaint-image`). */
  repaintToolId?: string
  /** @deprecated Read only as a migration fallback for Remove. */
  eraseToolId?: string
  /** Catalog tool used by Retouch → Remove (`erase-image` or inpaint fallback). */
  removeToolId?: string
  /** Sticky model prompts, separate because Expand and Repaint are different jobs. */
  expandPrompt?: string
  repaintPrompt?: string
  /** Most recently submitted Repaint prompts, newest first. */
  recentRepaintPrompts?: string[]
  /** Last real sub-tool pick per family, keyed by family id. */
  sub?: Record<string, string>
}

const KEY = () => makeProfileKey('imageEditor', 'toolPrefs')

/**
 * Cached against the key it was read under: switching profiles mid-session
 * changes the key, and serving the old profile's picks would be the leak this
 * scoping exists to prevent.
 */
let cachedKey: string | null = null
let cached: ToolPrefs = {}

export function readToolPrefs(): ToolPrefs {
  const key = KEY()
  if (cachedKey === key) return cached
  let parsed: ToolPrefs = {}
  try {
    const stored = localStorage.getItem(key)
    if (stored) {
      const value = JSON.parse(stored)
      if (value && typeof value === 'object') parsed = value as ToolPrefs
    }
  } catch { /* unreadable or corrupt — start from defaults */ }
  cachedKey = key
  cached = parsed
  return cached
}

export function writeToolPrefs(patch: Partial<ToolPrefs>): void {
  const key = KEY()
  const next = { ...readToolPrefs(), ...patch }
  cachedKey = key
  cached = next
  try {
    localStorage.setItem(key, JSON.stringify(next))
  } catch { /* storage full or unavailable — the pick just doesn't persist */ }
}

/** Remember a family's sub-tool. Null/undefined picks are landing states, not picks. */
export function rememberSubTool(familyId: string, subId: string | null): void {
  if (!subId) return
  writeToolPrefs({ sub: { ...readToolPrefs().sub, [familyId]: subId } })
}

export function rememberedSubTool(familyId: string): string | undefined {
  const value = readToolPrefs().sub?.[familyId]
  return familyId === 'retouch' && value === 'erase' ? 'remove' : value
}

/**
 * A remembered pick is only honoured while it still names something that
 * exists — engines get renamed, tools get uninstalled, and a toolbar showing a
 * tool that isn't in its own list is worse than the default.
 */
export function rememberedIfValid(
  value: string | undefined,
  isValid: (id: string) => boolean,
): string | undefined {
  return value && isValid(value) ? value : undefined
}
