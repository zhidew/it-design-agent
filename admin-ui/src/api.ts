import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  api_key?: string;
  base_url?: string;
  is_default: boolean;
  has_api_key?: boolean;
  description?: string;
}

export interface LlmConfig {
  llm_provider: string;
  openai_api_key?: string;
  openai_base_url?: string;
  openai_model_name?: string;
  gemini_api_key?: string;
  gemini_model_name?: string;
  has_openai_api_key?: boolean;
  has_gemini_api_key?: boolean;
}

export const api = {
  getProjects: () => apiClient.get('/projects').then(res => res.data),
  createProject: (name: string, description?: string) => 
    apiClient.post('/projects', { name, description }).then(res => res.data),
  getProjectVersions: (projectId: string, page: number = 1, pageSize: number = 10) => 
    apiClient.get(`/projects/${projectId}/versions`, { params: { page, page_size: pageSize } }).then(res => res.data),
  deleteProjectVersion: (projectId: string, version: string) =>
    apiClient.delete(`/projects/${projectId}/versions/${version}`).then(res => res.data),
  runOrchestrator: (projectId: string, version: string, requirementText: string, model?: string) =>
   apiClient.post(`/projects/${projectId}/versions/${version}/run`, { requirement_text: requirementText, model }).then(res => res.data),

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
  getRepositoryConfigs: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/repositories`).then(res => res.data),
  saveRepositoryConfig: (projectId: string, payload: {
    id: string;
    name: string;
    url: string;
    branch?: string;
    username?: string;
    token?: string;
    local_path?: string;
    description?: string;
    type?: string;
  }) => apiClient.post(`/projects/${projectId}/config/repositories`, payload).then(res => res.data),
  deleteRepositoryConfig: (projectId: string, repoId: string) =>
    apiClient.delete(`/projects/${projectId}/config/repositories/${repoId}`).then(res => res.data),
  getDatabaseConfigs: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/databases`).then(res => res.data),
  saveDatabaseConfig: (projectId: string, payload: {
    id: string;
    name: string;
    type: string;
    host: string;
    port: number;
    database: string;
    username?: string;
    password?: string;
    schema_filter?: string[];
    description?: string;
  }) => apiClient.post(`/projects/${projectId}/config/databases`, payload).then(res => res.data),
  deleteDatabaseConfig: (projectId: string, dbId: string) =>
    apiClient.delete(`/projects/${projectId}/config/databases/${dbId}`).then(res => res.data),
  getKnowledgeBaseConfigs: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/knowledge-bases`).then(res => res.data),
  saveKnowledgeBaseConfig: (projectId: string, payload: {
    id: string;
    name: string;
    type: string;
    path?: string;
    index_url?: string;
    includes?: string[];
    description?: string;
  }) => apiClient.post(`/projects/${projectId}/config/knowledge-bases`, payload).then(res => res.data),
  deleteKnowledgeBaseConfig: (projectId: string, kbId: string) =>
    apiClient.delete(`/projects/${projectId}/config/knowledge-bases/${kbId}`).then(res => res.data),
  getExpertConfigs: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/experts`).then(res => res.data),
  saveExpertConfig: (projectId: string, payload: {
    id: string;
    name: string;
    enabled: boolean;
    description?: string;
  }) => apiClient.post(`/projects/${projectId}/config/experts`, payload).then(res => res.data),
  getProjectLlmConfig: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/llm`).then(res => res.data),
  saveProjectLlmConfig: (projectId: string, payload: {
    llm_provider: string;
    openai_api_key?: string;
    openai_base_url?: string;
    openai_model_name?: string;
    gemini_api_key?: string;
    gemini_model_name?: string;
  }) => apiClient.post(`/projects/${projectId}/config/llm`, payload).then(res => res.data),
  getProjectModels: (projectId: string) =>
    apiClient.get(`/projects/${projectId}/config/models`).then(res => res.data),
  saveProjectModel: (projectId: string, payload: {
    id: string;
    name: string;
    provider: string;
    model_name: string;
    api_key?: string;
    base_url?: string;
    is_default: boolean;
    description?: string;
  }) => apiClient.post(`/projects/${projectId}/config/models`, payload).then(res => res.data),
  deleteProjectModel: (projectId: string, modelId: string) =>
    apiClient.delete(`/projects/${projectId}/config/models/${modelId}`).then(res => res.data),
  testProjectModel: (projectId: string, payload: {
    id: string;
    name: string;
    provider: string;
    model_name: string;
    api_key?: string;
    base_url?: string;
    is_default: boolean;
    description?: string;
  }) => apiClient.post(`/projects/${projectId}/config/llm/test`, payload).then(res => res.data),
  getSystemLlmDefaults: () =>
    apiClient.get('/system/llm-config').then(res => res.data),
};
