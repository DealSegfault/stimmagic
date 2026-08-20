import axios from 'axios'
import { getApiBase } from '../apiConfig'

export type ProjectElementType = 'location' | 'character' | 'prop'

export interface ProjectElement {
  id: number
  project_id: number
  asset_id: number | null
  revision_id: number | null
  media_id: number | null
  file_hash: string | null
  file_format: string | null
  element_type: ProjectElementType
  name: string
  reference_id: string
  description: string | null
  created_at: string | null
  updated_at: string | null
  created?: boolean
}

export interface CreateProjectElementInput {
  name?: string
  element_type?: ProjectElementType
  asset_id?: number
  media_id?: number
  description?: string
}

const api = () => getApiBase()

export function useProjectElementsApi() {
  async function listElements(
    projectId: number,
    params: { element_type?: ProjectElementType; query?: string } = {},
  ): Promise<ProjectElement[]> {
    return (await axios.get(`${api()}/projects/${projectId}/elements`, { params })).data
  }

  async function createElement(
    projectId: number,
    input: CreateProjectElementInput,
  ): Promise<ProjectElement> {
    return (await axios.post(`${api()}/projects/${projectId}/elements`, input)).data
  }

  async function deleteElement(projectId: number, elementId: number): Promise<void> {
    await axios.delete(`${api()}/projects/${projectId}/elements/${elementId}`)
  }

  async function updateElement(
    projectId: number,
    elementId: number,
    input: { name?: string; description?: string },
  ): Promise<ProjectElement> {
    return (await axios.patch(`${api()}/projects/${projectId}/elements/${elementId}`, input)).data
  }

  return { listElements, createElement, updateElement, deleteElement }
}
