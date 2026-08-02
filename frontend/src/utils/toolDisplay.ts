/**
 * Human names for the tool ids carried by media provenance.
 *
 * Display identity is separate from execution availability: a tool can be
 * disconnected, renamed, or retired while old media still names it, so a
 * lineage label may never depend on the tool being connected right now.
 *
 * Mirrors `backend/tool_display.py` — the built-in table and the
 * last-segment fallback are the same rules, so a facet, a browser row, and a
 * lineage node all read the same name for the same id.
 */

/** Tools with no provider registration to read a name from. */
export const BUILTIN_TOOL_DISPLAY_NAMES: Record<string, string> = {
  'builtin:stimma:image-editor': 'Image Editor',
  'builtin:darkroom-film-stock': 'Film Stock',
  'builtin:darkroom-develop': 'Develop',
  'builtin:darkroom-color-grade': 'Color Grade',
  'builtin:darkroom-lens': 'Lens & Optics',
}

export interface ToolLikeRecord {
  full_tool_id?: string
  tool_id?: string
  name?: string
}

/** Title-case the identifying segment, the same floor the backend takes. */
export function humanizeToolId(toolId: string): string {
  const slug = String(toolId).split(':').pop() || ''
  const name = slug
    .split(/[-_]+/)
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
  return name || String(toolId)
}

/**
 * The name to show for a tool id: built-in table, then the tools cache, then
 * the humanized id. `tools` is whatever `useProvidersApi().cachedTools` holds;
 * an empty list is fine and just falls through.
 */
export function toolDisplayName(
  toolId: string | null | undefined,
  tools: ToolLikeRecord[] = [],
): string {
  if (!toolId) return ''
  const builtin = BUILTIN_TOOL_DISPLAY_NAMES[toolId]
  if (builtin) return builtin
  const match = tools.find(
    tool => tool.full_tool_id === toolId || tool.tool_id === toolId,
  )
  if (match?.name) return match.name
  return humanizeToolId(toolId)
}
