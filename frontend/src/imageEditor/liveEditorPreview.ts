import { shallowRef } from 'vue'

/**
 * Client-side thumbnails for Assets with an open image editor.
 *
 * Persisted thumbnails deliberately lag behind the editor's mutable stack.
 * This small bridge lets every Asset projection show the editor's latest
 * composite immediately, while leaving normal media URLs and cache behavior
 * untouched for Assets that are not being edited.
 */
const previews = shallowRef(new Map<string, string>())

export function editorLivePreview(assetId: string | number | null | undefined): string | undefined {
  if (assetId == null) return undefined
  return previews.value.get(String(assetId))
}

export function publishEditorLivePreview(assetId: string | number, source: HTMLCanvasElement): void {
  const maxEdge = 320
  const scale = Math.min(1, maxEdge / Math.max(source.width, source.height, 1))
  const thumbnail = document.createElement('canvas')
  thumbnail.width = Math.max(1, Math.round(source.width * scale))
  thumbnail.height = Math.max(1, Math.round(source.height * scale))
  thumbnail.getContext('2d')!.drawImage(source, 0, 0, thumbnail.width, thumbnail.height)
  const next = new Map(previews.value)
  next.set(String(assetId), thumbnail.toDataURL('image/webp', 0.86))
  previews.value = next
}

export function clearEditorLivePreview(assetId: string | number): void {
  const key = String(assetId)
  if (!previews.value.has(key)) return
  const next = new Map(previews.value)
  next.delete(key)
  previews.value = next
}
