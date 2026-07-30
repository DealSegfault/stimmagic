/**
 * The one place an "Edit" verb turns into a route.
 *
 * Entry points know a Media id because that is what tiles and slideshow frames
 * display. The editor is Asset-keyed, so this helper resolves the owning Asset
 * before navigating. Reopening an Asset resumes its one stack document.
 */

import type { Router } from 'vue-router'
import axios from 'axios'
import { addToast } from '../../composables/useToasts'

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
  const assetId = await assetIdForMedia(mediaId)
  if (!assetId) {
    addToast('Could not open this image in the editor.', 'warning')
    return
  }
  await router.push({ name: 'edit-image', params: { assetId: String(assetId) } })
}
