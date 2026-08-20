import axios from 'axios'
import { getApiBase } from '../apiConfig'

export type ReferenceStatus =
  | 'missing' | 'draft' | 'generating' | 'review' | 'approved'
  | 'stale' | 'inconsistent' | 'rejected' | 'error'

export interface ReferenceView {
  id: number
  project_id: number
  pack_id: number
  view_key: string
  label: string
  view_type: 'identity' | 'location_camera' | 'detail' | 'scale'
  state_key: string
  view_spec: Record<string, any>
  asset_id: number | null
  approved_revision_id: number | null
  approved_media_id: number | null
  candidate_media_id: number | null
  status: ReferenceStatus
  source_signature: string | null
  sort_order: number
}

export interface ElementState {
  id: number
  project_id: number
  project_element_id: number
  state_key: string
  label: string
  prompt_delta: string
  constraints: Record<string, any>
  is_default: boolean
}

export interface CompositionItem {
  id: number
  project_element_id: number
  element_name: string
  reference_id: string
  reference_view_id: number
  view_label: string
  source_revision_id: number
  source_media_id: number
  state_id: number | null
  state_key: string
  state_label: string
  role: string
  placement: Record<string, any>
  item_order: number
}

export interface ProjectComposition {
  id: number
  project_id: number
  name: string
  location_view_id: number
  base_location_revision_id: number
  base_location_media_id: number
  result_asset_id: number | null
  approved_revision_id: number | null
  approved_media_id: number | null
  candidate_media_id: number | null
  placement_guide_media_id: number | null
  prompt_delta: string
  prompt_version: number
  source_signature: string
  status: ReferenceStatus
  validation: Record<string, any>
  items: CompositionItem[]
}

export interface ReferencePack {
  id: number
  project_id: number
  project_element_id: number
  element: {
    id: number
    name: string
    reference_id: string
    element_type: 'location' | 'character' | 'prop'
    description: string | null
    asset_id: number | null
  }
  pack_type: 'location' | 'character' | 'prop'
  identity_prompt: string
  negative_prompt: string
  prompt_version: number
  sheet_asset_id: number | null
  approved_sheet_revision_id: number | null
  sheet_media_id: number | null
  status: ReferenceStatus
  views: ReferenceView[]
  states: ElementState[]
  compositions: ProjectComposition[]
}

export interface ReferenceWorkspace {
  project_id: number
  packs: ReferencePack[]
  stats: Record<string, number>
}

const api = () => getApiBase()
const generationConfig = { timeout: 660_000 }

export function useProjectReferencesApi() {
  async function getWorkspace(projectId: number): Promise<ReferenceWorkspace> {
    return (await axios.get(`${api()}/projects/${projectId}/references`)).data
  }

  async function updatePack(
    projectId: number,
    packId: number,
    input: { identity_prompt?: string; negative_prompt?: string },
  ): Promise<ReferencePack> {
    return (await axios.patch(`${api()}/projects/${projectId}/references/packs/${packId}`, input)).data
  }

  async function syncBlocking(projectId: number) {
    return (await axios.post(`${api()}/projects/${projectId}/references/sync-blocking`)).data
  }

  async function createState(
    projectId: number,
    packId: number,
    input: { state_key?: string; label: string; prompt_delta?: string },
  ): Promise<ElementState> {
    return (await axios.post(`${api()}/projects/${projectId}/references/packs/${packId}/states`, input)).data
  }

  async function generateView(projectId: number, viewId: number): Promise<ReferenceView> {
    return (await axios.post(
      `${api()}/projects/${projectId}/references/views/${viewId}/generate`,
      {},
      generationConfig,
    )).data
  }

  async function generateMissing(projectId: number, packId: number) {
    return (await axios.post(
      `${api()}/projects/${projectId}/references/packs/${packId}/generate-missing`,
      {},
      generationConfig,
    )).data
  }

  async function approveView(projectId: number, viewId: number): Promise<ReferenceView> {
    return (await axios.post(`${api()}/projects/${projectId}/references/views/${viewId}/approve`)).data
  }

  async function rejectView(projectId: number, viewId: number): Promise<ReferenceView> {
    return (await axios.post(`${api()}/projects/${projectId}/references/views/${viewId}/reject`)).data
  }

  async function renderSheet(projectId: number, packId: number) {
    return (await axios.post(`${api()}/projects/${projectId}/references/packs/${packId}/render-sheet`)).data
  }

  async function createComposition(projectId: number, input: Record<string, any>): Promise<ProjectComposition> {
    return (await axios.post(`${api()}/projects/${projectId}/references/compositions`, input)).data
  }

  async function generateComposition(projectId: number, compositionId: number): Promise<ProjectComposition> {
    return (await axios.post(
      `${api()}/projects/${projectId}/references/compositions/${compositionId}/generate`,
      {},
      generationConfig,
    )).data
  }

  async function approveComposition(
    projectId: number,
    compositionId: number,
    force = false,
  ): Promise<ProjectComposition> {
    return (await axios.post(
      `${api()}/projects/${projectId}/references/compositions/${compositionId}/approve`,
      { force },
    )).data
  }

  async function rejectComposition(projectId: number, compositionId: number): Promise<ProjectComposition> {
    return (await axios.post(`${api()}/projects/${projectId}/references/compositions/${compositionId}/reject`)).data
  }

  async function deleteComposition(projectId: number, compositionId: number): Promise<void> {
    await axios.delete(`${api()}/projects/${projectId}/references/compositions/${compositionId}`)
  }

  return {
    getWorkspace,
    updatePack,
    syncBlocking,
    createState,
    generateView,
    generateMissing,
    approveView,
    rejectView,
    renderSheet,
    createComposition,
    generateComposition,
    approveComposition,
    rejectComposition,
    deleteComposition,
  }
}
