/**
 * The one place an "Edit" verb turns into a route.
 *
 * Two editors ship side by side during the op-stack rollout, and which one
 * opens is decided by release channel, not by the caller. Every entry point
 * (slideshow, context menu, versions list) goes through here so the switch
 * lives in exactly one place and the eventual cutover is a one-line change.
 *
 * They are keyed differently on purpose: the snapshot editor opens an editor
 * INSTANCE (a counter) that a media id is loaded into, while the op-stack
 * editor opens an ASSET, because a stack belongs to the asset and reopening it
 * must resume the same document rather than start a second one.
 */

import type { Router } from 'vue-router'
import axios from 'axios'
import { isImageEditorV2Enabled } from '../../appConfig'
import { useWorkspaceTabs } from '../../composables/useWorkspaceTabs'

/**
 * Resolve the Asset a media id belongs to. Entry points hand us a media id
 * because that is what a tile or a slideshow frame knows about.
 */
async function assetIdForMedia(mediaId: number | string): Promise<number | null> {
  try {
    const { data } = await axios.get(`/api/media/${mediaId}`)
    return data?.asset_id ?? null
  } catch {
    return null
  }
}

export async function openImageEditor(router: Router, mediaId: number | string) {
  if (isImageEditorV2Enabled()) {
    const assetId = await assetIdForMedia(mediaId)
    if (assetId) {
      router.push({ name: 'edit-image-v2', params: { assetId: String(assetId) } })
      return
    }
    // Bare Media with no Asset has no stack to own; fall through to the
    // snapshot editor rather than failing the gesture.
  }
  const { nextEditorId } = useWorkspaceTabs()
  router.push({
    name: 'edit-image',
    params: { editorId: nextEditorId(), mediaId: String(mediaId) },
  })
}
