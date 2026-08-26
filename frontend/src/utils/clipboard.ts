import { writeImage, writeText } from '@tauri-apps/plugin-clipboard-manager'
import { isTauri } from '../apiConfig'

/**
 * Copy text to clipboard using Tauri's clipboard plugin
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await writeText(text)
    return true
  } catch (e) {
    console.error('[clipboard] Failed to copy:', e)
    return false
  }
}

/**
 * Copy actual image pixels to the system clipboard.
 * Tauri needs encoded image bytes (PNG is the most portable format); browsers
 * use the async Clipboard API with a ClipboardItem.
 */
export async function copyImageToClipboard(blob: Blob): Promise<boolean> {
  try {
    const png = await toPngBlob(blob)

    if (isTauri()) {
      await writeImage(await png.arrayBuffer())
      return true
    }

    if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
      return false
    }

    await navigator.clipboard.write([
      new ClipboardItem({ 'image/png': png })
    ])
    return true
  } catch (e) {
    console.error('[clipboard] Failed to copy image:', e)
    return false
  }
}

async function toPngBlob(blob: Blob): Promise<Blob> {
  if (blob.type === 'image/png') return blob

  const bitmap = await createImageBitmap(blob)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Could not create image canvas')
    context.drawImage(bitmap, 0, 0)

    const png = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/png')
    })
    if (!png) throw new Error('Could not encode image as PNG')
    return png
  } finally {
    bitmap.close()
  }
}
