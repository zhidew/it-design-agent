import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const api = {
  getProjects: () => apiClient.get('/projects').then(res => res.data),
  createProject: (name: string, description?: string) => 
    apiClient.post('/projects', { name, description }).then(res => res.data),
  getProjectVersions: (projectId: string) => 
    apiClient.get(`/projects/${projectId}/versions`).then(res => res.data),
  runOrchestrator: (projectId: string, version: string, requirementText: string) => 
    apiClient.post(`/projects/${projectId}/versions/${version}/run`, { requirement_text: requirementText }).then(res => res.data),
  getProjectArtifacts: (projectId: string, version: string) => 
    apiClient.get(`/projects/${projectId}/versions/${version}/artifacts`).then(res => res.data),
  getVersionLogs: (projectId: string, version: string) => 
    apiClient.get(`/projects/${projectId}/versions/${version}/logs`).then(res => res.data),
  getJobStatusSseUrl: (jobId: string) => `${API_BASE_URL}/jobs/${jobId}/status`,
};
