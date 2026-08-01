/**
 * Build a browser-loadable URL for an image-stack payload.
 *
 * Axios rewrites relative API requests to the Tauri sidecar, but <img> and
 * canvas image loaders do not go through Axios. The API base therefore has to
 * be present in the URL itself in packaged builds.
 */
export function stackPayloadUrl(
  apiBase: string,
  documentId: number | string,
  ref: string,
  profileId: string,
  revision?: number | string,
): string {
  const separator = ref.indexOf('/')
  const subdir = separator === -1 ? 'payloads' : ref.slice(0, separator)
  const name = separator === -1 ? ref : ref.slice(separator + 1)
  const params = new URLSearchParams({ subdir, profile: profileId })
  if (revision !== undefined) params.set('revision', String(revision))
  return `${apiBase.replace(/\/$/, '')}/image-stack/${documentId}/payloads/${encodeURIComponent(name)}?${params}`
}
