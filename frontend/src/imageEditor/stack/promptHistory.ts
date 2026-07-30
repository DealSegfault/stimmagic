/** Add one submitted prompt to a bounded, newest-first MRU list. */
export function addRecentPrompt(
  current: string[] | undefined,
  prompt: string,
  limit = 12,
): string[] {
  const value = prompt.trim()
  if (!value) return current ?? []
  const key = value.toLocaleLowerCase()
  return [
    value,
    ...(current ?? []).filter(item => item.trim().toLocaleLowerCase() !== key),
  ].slice(0, limit)
}
