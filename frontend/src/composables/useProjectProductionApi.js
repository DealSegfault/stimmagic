import axios from 'axios'
import { getApiBase } from '../apiConfig'

export function useProjectProductionApi() {
  const base = (projectId) => `${getApiBase()}/projects/${projectId}/production`

  async function getProduction(projectId) {
    return (await axios.get(base(projectId))).data
  }

  async function findCandidateShot(projectId, mediaId) {
    return (await axios.get(`${base(projectId)}/candidates/by-media/${mediaId}`)).data
  }

  async function getCandidates(projectId, shotId) {
    return (await axios.get(`${base(projectId)}/shots/${shotId}/candidates`)).data
  }

  async function updateShot(projectId, shotId, payload) {
    return (await axios.patch(`${base(projectId)}/shots/${shotId}`, payload)).data
  }

  async function approveShot(projectId, shotId, payload) {
    return (await axios.post(`${base(projectId)}/shots/${shotId}/approve`, payload)).data
  }

  async function rejectShot(projectId, shotId, payload) {
    return (await axios.post(`${base(projectId)}/shots/${shotId}/reject`, payload)).data
  }

  return { getProduction, findCandidateShot, getCandidates, updateShot, approveShot, rejectShot }
}
