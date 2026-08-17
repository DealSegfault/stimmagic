import axios from 'axios'
import { getApiBase } from '../apiConfig'

export function useProjectDirectionApi() {
  const base = (projectId) => `${getApiBase()}/projects/${projectId}/direction`
  async function getDirection(projectId) { return (await axios.get(base(projectId))).data }
  async function importScript(projectId, payload) { return (await axios.post(`${base(projectId)}/import`, payload)).data }
  async function updateScript(projectId, payload) { return (await axios.put(`${base(projectId)}/script`, payload)).data }
  async function updateScene(projectId, sceneId, payload) { return (await axios.patch(`${base(projectId)}/scenes/${sceneId}`, payload)).data }
  async function getSceneGenerations(projectId, sceneId) { return (await axios.get(`${base(projectId)}/scenes/${sceneId}/generations`)).data }
  async function getSceneContinuity(projectId, sceneId) { return (await axios.get(`${base(projectId)}/scenes/${sceneId}/continuity`)).data }
  async function createSceneChat(projectId, sceneId) { return (await axios.post(`${base(projectId)}/scenes/${sceneId}/chat`)).data }
  return { getDirection, importScript, updateScript, updateScene, getSceneGenerations, getSceneContinuity, createSceneChat }
}
