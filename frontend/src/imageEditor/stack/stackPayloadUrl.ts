/**
 * Build a browser-loadable URL for an image-stack payload.
 *
 * Axios rewrites relative API requests to the Tauri sidecar and adds profile
 * headers, but <img> and canvas image loaders do neither. Packaged URLs must
 * therefore include the API base and the profile middleware's query auth.
 */
export function stackPayloadUrl(
  apiBase: string,
  documentId: number | string,
  ref: string,
  profileId: string,
  revision?: number | string,
  pin?: string | null,
): string {
  const separator = ref.indexOf('/')
  const subdir = separator === -1 ? 'payloads' : ref.slice(0, separator)
  const name = separator === -1 ? ref : ref.slice(separator + 1)
  const params = new URLSearchParams({ subdir, profile: profileId })
  if (revision !== undefined) params.set('revision', String(revision))
  if (pin) params.set('pin', pin)
  return `${apiBase.replace(/\/$/, '')}/image-stack/${documentId}/payloads/${encodeURIComponent(name)}?${params}`
}
