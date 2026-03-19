import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const api = {
  getProjects: () => apiClient.get('/projects').then(res => res.data),
  createProject: (name: string, description?: string) => 
    apiClient.post('/projects', { name, description }).then(res => res.data),
  getProjectVersions: (projectId: string, page: number = 1, pageSize: number = 10) => 
    apiClient.get(`/projects/${projectId}/versions`, { params: { page, page_size: pageSize } }).then(res => res.data),
  deleteProjectVersion: (projectId: string, version: string) =>
    apiClient.delete(`/projects/${projectId}/versions/${version}`).then(res => res.data),
  runOrchestrator: (projectId: string, version: string, requirementText: string) => 
    apiClient.post(`/projects/${projectId}/versions/${version}/run`, { requirement_text: requirementText }).then(res => res.data),
  uploadBaselineFiles: (projectId: string, version: string, files: File[]) => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    return apiClient.post(`/projects/${projectId}/versions/${version}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    }).then(res => res.data);
  },
  getProjectArtifacts: (projectId: string, version: string) => 
    apiClient.get(`/projects/${projectId}/versions/${version}/artifacts`).then(res => res.data),
  getProjectState: (projectId: string, version: string) => 
    apiClient.get(`/projects/${projectId}/versions/${version}/state`).then(res => res.data),
  resumeWorkflow: (
    projectId: string,
    version: string,
    humanInput: {
      action: 'approve' | 'revise' | 'answer';
      node_id?: string;
      interrupt_id?: string;
      selected_option?: string;
      answer?: string;
      feedback?: string;
    },
  ) => 
    apiClient.post(`/projects/${projectId}/versions/${version}/resume`, humanInput).then(res => res.data),
  retryWorkflowNode: (projectId: string, version: string, nodeType: string) =>
    apiClient.post(`/projects/${projectId}/versions/${version}/retry-node`, { node_type: nodeType }).then(res => res.data),
  continueWorkflow: (projectId: string, version: string) =>
    apiClient.post(`/projects/${projectId}/versions/${version}/continue`).then(res => res.data),
  getVersionLogs: (projectId: string, version: string) => 
    apiClient.get(`/projects/${projectId}/versions/${version}/logs`).then(res => res.data),
  getJobStatusSseUrl: (jobId: string) => `${API_BASE_URL}/jobs/${jobId}/status`,
};
