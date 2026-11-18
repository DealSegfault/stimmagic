import { computed, isRef, ref, type Ref } from 'vue'
import axios from 'axios'
import { getApiBase } from '../apiConfig'
import { getCurrentProfileId } from './useProfile'
import type { H3Example, H3ExampleReference } from '../utils/h3Examples'

const examples = new Map<string, Promise<H3Example>>()

export function getH3ThumbnailUrl(id: string) {
  return `${getApiBase()}/prompt/h3/examples/${id}/thumbnail?profile=${encodeURIComponent(getCurrentProfileId() || '')}`
}

export function getH3Example(id: string): Promise<H3Example> {
  if (!examples.has(id)) {
    const request = axios.get(`${getApiBase()}/prompt/h3/examples/${id}`).then(({ data }) => ({
      ...data, label: data.style_label,
    })).catch((error) => {
      examples.delete(id)
      throw error
    })
    examples.set(id, request)
  }
  return examples.get(id)!.then((example) => ({ ...example, thumbnail_url: getH3ThumbnailUrl(example.id) }))
}

export async function searchH3Examples(params: Record<string, string | number>) {
  const { data } = await axios.get(`${getApiBase()}/prompt/h3/examples`, { params })
  return {
    ...data,
    items: data.items.map((item: H3Example) => ({ ...item, label: item.style_label, thumbnail_url: getH3ThumbnailUrl(item.id) })),
  } as { items: H3Example[]; total: number; styles: Record<string, string>; topics: Record<string, string> }
}

const selections = new Map<string, Ref<H3ExampleReference[]>>()

export function useH3StyleReferences(chatId: Ref<string | number | null>) {
  function bucket() {
    const key = String(isRef(chatId) ? chatId.value ?? '' : chatId)
    if (!selections.has(key)) selections.set(key, ref([]))
    return selections.get(key)!
  }
  const items = computed(() => bucket().value)
  function add(reference: H3ExampleReference) {
    if (!/^\d{6}$/.test(reference.id)) return
    const current = bucket()
    current.value = [...current.value.filter((item) => item.id !== reference.id), reference]
  }
  function remove(id: string) { bucket().value = bucket().value.filter((item) => item.id !== id) }
  function clear() { bucket().value = [] }
  return { items, add, remove, clear }
}
