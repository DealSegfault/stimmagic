import { computed, isRef, ref, type ComputedRef, type Ref } from 'vue'
import type { ProjectElement } from './useProjectElementsApi'

interface ChatBucket {
  items: Ref<ProjectElement[]>
}

const buckets = new Map<string, ChatBucket>()

function bucketFor(chatId: string | number | null): ChatBucket {
  const key = chatId == null ? '' : String(chatId)
  let bucket = buckets.get(key)
  if (!bucket) {
    bucket = { items: ref<ProjectElement[]>([]) }
    buckets.set(key, bucket)
  }
  return bucket
}

type ChatIdArg = string | number | null | undefined | Ref<string | number | null>

export function useElementReferences(chatIdArg: ChatIdArg): {
  items: ComputedRef<ProjectElement[]>
  count: ComputedRef<number>
  has: (referenceId: string) => boolean
  add: (element: ProjectElement) => void
  remove: (referenceId: string) => void
  clear: () => void
} {
  const getId = (): string | number | null => {
    if (chatIdArg == null) return null
    return isRef(chatIdArg) ? chatIdArg.value : chatIdArg
  }
  const getBucket = () => bucketFor(getId())
  const items = computed(() => getBucket().items.value)
  const count = computed(() => items.value.length)

  function has(referenceId: string) {
    return getBucket().items.value.some((item) => item.reference_id === referenceId)
  }
  function add(element: ProjectElement) {
    const bucket = getBucket()
    if (has(element.reference_id)) return
    bucket.items.value = [...bucket.items.value, element]
  }
  function remove(referenceId: string) {
    const bucket = getBucket()
    bucket.items.value = bucket.items.value.filter(
      (item) => item.reference_id !== referenceId,
    )
  }
  function clear() {
    getBucket().items.value = []
  }

  return { items, count, has, add, remove, clear }
}

function cleanInline(value: string | null | undefined): string {
  return (value || '').replace(/[\r\n]+/g, ' ').replace(/\*\*/g, '').trim()
}

export function formatElementReferencesForMessage(elements: ProjectElement[]): string {
  if (elements.length === 0) return ''
  const lines = ['> **Project elements:**']
  for (const element of elements) {
    const meta = [
      `element_id: ${element.id}`,
      `asset_id: ${element.asset_id ?? ''}`,
      `media_id: ${element.media_id ?? ''}`,
      `file_hash: ${element.file_hash ?? ''}`,
      `file_format: ${element.file_format ?? ''}`,
    ].join(', ')
    lines.push(
      `> - ${element.element_type} · **${cleanInline(element.name)}** · `
      + `\`@${element.reference_id}\` (${meta})`,
    )
  }
  return lines.join('\n')
}

export interface ParsedElementReferences {
  refs: ProjectElement[]
  text: string
}

const HEADER_LINE = /^> \*\*Project elements:\*\*\s*$/
const ITEM_LINE = /^> - (location|character|prop) · \*\*(.+?)\*\* · `@([^`]+)` \(element_id: (\d+), asset_id: (\d*), media_id: (\d*), file_hash: ([^,]*), file_format: ([^)]*)\)\s*$/

export function parseElementReferences(
  message: string | null | undefined,
): ParsedElementReferences {
  const source = message ?? ''
  if (!source) return { refs: [], text: '' }
  const lines = source.split('\n')
  if (!HEADER_LINE.test(lines[0] || '')) return { refs: [], text: source }

  const refs: ProjectElement[] = []
  let index = 1
  while (index < lines.length) {
    const match = ITEM_LINE.exec(lines[index])
    if (!match) break
    const [, elementType, name, referenceId, elementId, assetId, mediaId, fileHash, fileFormat] = match
    refs.push({
      id: Number(elementId),
      project_id: 0,
      asset_id: assetId ? Number(assetId) : null,
      revision_id: null,
      media_id: mediaId ? Number(mediaId) : null,
      file_hash: fileHash || null,
      file_format: fileFormat || null,
      element_type: elementType as ProjectElement['element_type'],
      name,
      reference_id: referenceId,
      description: null,
      created_at: null,
      updated_at: null,
    })
    index++
  }
  if (lines[index] === '') index++
  return { refs, text: lines.slice(index).join('\n') }
}
