import { shallowRef } from 'vue'

/**
 * Client-side live pixels for Assets with an open image editor.
 *
 * Persisted thumbnails deliberately lag behind the editor's mutable stack.
 * This small bridge gives grids a compact thumbnail and the slideshow a
 * full-resolution handoff frame while leave-autosave commits. Normal media
 * URLs and cache behavior stay untouched for Assets that are not being edited.
 */
const previews = shallowRef(new Map<string, string>())
const frames = shallowRef(new Map<string, { canvas: HTMLCanvasElement; revision: number }>())
let frameRevision = 0

export function editorLivePreview(assetId: string | number | null | undefined): string | undefined {
  if (assetId == null) return undefined
  return previews.value.get(String(assetId))
}

/**
 * Full-resolution live pixels for a slideshow shown while leave-autosave is
 * still materializing the new Asset Revision. The canvas belongs to the
 * KeepAlive'd editor; consumers copy it into their own canvas synchronously.
 */
export function editorLiveFrame(
  assetId: string | number | null | undefined,
): { canvas: HTMLCanvasElement; revision: number } | undefined {
  if (assetId == null) return undefined
  return frames.value.get(String(assetId))
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

  const nextFrames = new Map(frames.value)
  nextFrames.set(String(assetId), { canvas: source, revision: ++frameRevision })
  frames.value = nextFrames
}

export function clearEditorLivePreview(assetId: string | number): void {
  const key = String(assetId)
  if (previews.value.has(key)) {
    const next = new Map(previews.value)
    next.delete(key)
    previews.value = next
  }
  if (frames.value.has(key)) {
    const nextFrames = new Map(frames.value)
    nextFrames.delete(key)
    frames.value = nextFrames
  }
}
