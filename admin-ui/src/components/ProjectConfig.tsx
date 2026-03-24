import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { useNavigate, Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, Bot, Cpu, Database, FolderGit2, Plus, RefreshCw, Save, Settings2, Trash2, Activity, CheckCircle, XCircle, AlertTriangle, FileText, HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, type DebugConfig } from '../api';
import { LanguageSwitcher } from './LanguageSwitcher';

type TabKey = 'repositories' | 'databases' | 'knowledge' | 'experts' | 'llm' | 'danger';

interface AssetsSummary {
  exists: boolean;
  project_id: string;
  versions: {
    version: string;
    file_count: number;
    size_mb: number;
    has_baseline: boolean;
    has_artifacts: boolean;
    has_logs: boolean;
  }[];
  total_versions: number;
  total_files: number;
  total_size_mb: number;
  configs: {
    repositories_count: number;
    databases_count: number;
    knowledge_bases_count: number;
    models_count: number;
  };
}

interface RepositoryConfig {
  id: string;
  name: string;
  type?: string;
  url: string;
  branch?: string;
  username?: string;
  token?: string;
  local_path?: string;
  description?: string;
  has_token?: boolean;
}

interface DatabaseConfig {
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
  has_password?: boolean;
}

interface KnowledgeBaseConfig {
  id: string;
  name: string;
  type: string;
  path?: string;
  index_url?: string;
  includes?: string[];
  description?: string;
}

interface ExpertConfig {
  id: string;
  name: string;
  enabled: boolean;
  description?: string;
}

interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  api_key?: string;
  base_url?: string;
  headers?: string;
  is_default: boolean;
  has_api_key?: boolean;
  has_headers?: boolean;
  description?: string;
}

const createModel = (): ModelConfig => ({
  id: Math.random().toString(36).substring(2, 9),
  name: '',
  provider: 'openai',
  model_name: '',
  api_key: '',
  base_url: '',
  headers: '',
  is_default: false,
  description: '',
});

const createRepository = (): RepositoryConfig => ({
  id: '',
  name: '',
  type: 'git',
  url: '',
  branch: 'main',
  username: '',
  token: '',
  local_path: '',
  description: '',
});

const createDatabase = (): DatabaseConfig => ({
  id: '',
  name: '',
  type: 'postgresql',
  host: '',
  port: 5432,
  database: '',
  username: '',
  password: '',
  schema_filter: [],
  description: '',
});

const createKnowledgeBase = (): KnowledgeBaseConfig => ({
  id: '',
  name: '',
  type: 'local',
  path: '',
  index_url: '',
  includes: [],
  description: '',
});

function splitMultiline(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseHeadersJson(value?: string): Record<string, string> | undefined {
  if (!value?.trim()) {
    return undefined;
  }

  const candidate = JSON.parse(value);
  if (!candidate || Array.isArray(candidate) || typeof candidate !== 'object') {
    throw new Error('Headers must be a JSON object.');
  }

  return Object.fromEntries(
    Object.entries(candidate).map(([key, item]) => [String(key), String(item)]),
  );
}

interface ConfigEditorModalProps {
  title: string;
  icon: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}

function ConfigEditorModal({ title, icon, onClose, children, footer }: ConfigEditorModalProps) {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4 sm:p-6">
      <div className="absolute inset-0 bg-slate-950/35 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex w-full max-w-5xl max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-3xl border border-indigo-100 bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3 sm:px-5">
          <h3 className="flex items-center gap-2 text-base font-black uppercase tracking-tight text-gray-900">
            {icon}
            {title}
          </h3>
          <button onClick={onClose} className="rounded-lg p-2 text-gray-400 transition-all hover:bg-gray-100 hover:text-gray-600">
            <Trash2 size={16} />
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-4 sm:px-5">
          {children}
        </div>
        <div className="border-t border-gray-100 bg-white/95 px-4 py-3 sm:px-5">
          {footer}
        </div>
      </div>
    </div>
  );
}

export function ProjectConfig() {
  const { t, i18n } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const projectId = id || '';
  const backTo = (location.state as { from?: string } | null)?.from || '/';
  const [activeTab, setActiveTab] = useState<TabKey>('repositories');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [repositories, setRepositories] = useState<RepositoryConfig[]>([]);
  const [databases, setDatabases] = useState<DatabaseConfig[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseConfig[]>([]);
  const [experts, setExperts] = useState<ExpertConfig[]>([]);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [debugConfig, setDebugConfig] = useState<DebugConfig>({
    llm_interaction_logging_enabled: false,
    llm_full_payload_logging_enabled: false,
  });
  const [isModelModalOpen, setIsModelModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
  const [testingModel, setTestingModel] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Repository modal & test states
  const [isRepoModalOpen, setIsRepoModalOpen] = useState(false);
  const [editingRepo, setEditingRepo] = useState<RepositoryConfig | null>(null);
  const [isNewRepo, setIsNewRepo] = useState(false);
  const [testingRepo, setTestingRepo] = useState(false);

  // Database modal & test states
  const [isDbModalOpen, setIsDbModalOpen] = useState(false);
  const [editingDb, setEditingDb] = useState<DatabaseConfig | null>(null);
  const [isNewDb, setIsNewDb] = useState(false);
  const [testingDb, setTestingDb] = useState(false);

  // Knowledge base modal & test states
  const [isKbModalOpen, setIsKbModalOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBaseConfig | null>(null);
  const [isNewKb, setIsNewKb] = useState(false);
  const [testingKb, setTestingKb] = useState(false);

  // Project Deletion states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [assetsSummary, setAssetsSummary] = useState<AssetsSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const testModelConfig = async () => {
    if (!projectId || !editingModel) return;
    setTestingModel(true);
    setTestResult(null);
    try {
      const res = await api.testProjectModel(projectId, {
        ...editingModel,
        api_key: editingModel.api_key?.trim() || undefined,
        headers: parseHeadersJson(editingModel.headers),
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, message: err.response?.data?.detail || err.message });
    } finally {
      setTestingModel(false);
    }
  };

  const testRepoConfig = async () => {
    if (!projectId || !editingRepo) return;
    setTestingRepo(true);
    setTestResult(null);
    try {
      const res = await api.testProjectRepository(projectId, {
        ...editingRepo,
        token: editingRepo.token?.trim() || undefined,
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, message: err.response?.data?.detail || err.message });
    } finally {
      setTestingRepo(false);
    }
  };

  const testDbConfig = async () => {
    if (!projectId || !editingDb) return;
    setTestingDb(true);
    setTestResult(null);
    try {
      const res = await api.testProjectDatabase(projectId, {
        ...editingDb,
        password: editingDb.password?.trim() || undefined,
      });
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, message: err.response?.data?.detail || err.message });
    } finally {
      setTestingDb(false);
    }
  };

  const testKbConfig = async () => {
    if (!projectId || !editingKb) return;
    setTestingKb(true);
    setTestResult(null);
    try {
      const res = await api.testProjectKnowledgeBase(projectId, editingKb);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, message: err.response?.data?.detail || err.message });
    } finally {
      setTestingKb(false);
    }
  };

  const expertCopy = useMemo(() => {
    const isZh = i18n.language.toLowerCase().startsWith('zh');
    const fallback = {
      tab: isZh ? '专家启用配置' : 'Expert Config',
      eyebrow: isZh ? '专家可用性' : 'Expert Availability',
      title: isZh ? '专家启用配置' : 'Expert Enablement',
      empty: isZh ? '暂无可配置专家。' : 'No experts available yet.',
      enabled: isZh ? '已启用' : 'Enabled',
      disabled: isZh ? '未启用' : 'Disabled',
    };
    const pick = (key: string, fallbackValue: string) => {
      const value = t(key);
      return /\?{2,}/.test(value) ? fallbackValue : value;
    };
    return {
      tab: pick('projectConfig.tabs.experts', fallback.tab),
      eyebrow: pick('projectConfig.experts.eyebrow', fallback.eyebrow),
      title: pick('projectConfig.experts.title', fallback.title),
      empty: pick('projectConfig.experts.empty', fallback.empty),
      enabled: pick('projectConfig.experts.enabled', fallback.enabled),
      disabled: pick('projectConfig.experts.disabled', fallback.disabled),
    };
  }, [i18n.language, t]);

  const llmCopy = useMemo(() => {
    const isZh = i18n.language.toLowerCase().startsWith('zh');
    return {
      tab: isZh ? '大模型配置' : 'LLM CONFIG',
      eyebrow: isZh ? '系统模型配置' : 'System Model Setup',
      title: isZh ? '大模型配置' : 'LLM CONFIG',
      description: isZh
        ? '配置当前项目使用的模型提供商、网关地址、模型名称与密钥。可以配置多个模型供执行时选择。'
        : 'Configure project-level models. You can add multiple configurations to choose from during execution.',
      refresh: isZh ? '刷新配置' : 'Refresh Config',
      provider: isZh ? '模型提供商' : 'Provider',
      openaiBaseUrl: isZh ? 'OpenAI 网关地址' : 'OpenAI Base URL',
      openaiModel: isZh ? 'OpenAI 模型名' : 'OpenAI Model',
      geminiModel: isZh ? 'Gemini 模型名' : 'Gemini Model',
      openaiKey: isZh ? 'OpenAI API Key (选填)' : 'OpenAI API Key (Optional)',
      geminiKey: isZh ? 'Gemini API Key (选填)' : 'Gemini API Key (Optional)',
      saved: isZh ? '保存' : 'Save',
      keepCurrent: isZh ? '留空则保持当前密钥' : 'Leave blank to keep current key',
      enterKey: isZh ? 'API Key (选填)' : 'API Key (Optional)',
      saveSuccess: isZh ? '大模型配置已保存。' : 'LLM config saved.',
      saveError: isZh ? '保存大模型配置失败。' : 'Failed to save LLM config.',
      loadError: isZh ? '加载大模型配置失败。' : 'Failed to load LLM config.',
      addModel: isZh ? '添加模型配置' : 'Add Model',
      editModel: isZh ? '编辑模型' : 'Edit Model',
      deleteModel: isZh ? '删除模型' : 'Delete Model',
      modelName: isZh ? '显示名称' : 'Display Name',
      modelId: isZh ? '模型 ID' : 'Model ID',
      isDefault: isZh ? '设为默认' : 'Set as Default',
      defaultLabel: isZh ? '默认' : 'Default',
      testModel: isZh ? '测试连接' : 'Test Connection',
      testing: isZh ? '正在测试...' : 'Testing...',
      testSuccess: isZh ? '连接成功！' : 'Connection successful!',
      testFailed: isZh ? '连接失败：' : 'Connection failed: ',
      debugEyebrow: isZh ? '调试日志' : 'Debug Logging',
      debugTitle: isZh ? 'LLM 调试日志开关' : 'LLM Debug Logging',
      debugDescription: isZh
        ? '默认关闭。排查问题时再开启，避免产生额外磁盘占用和敏感上下文落盘。'
        : 'Disabled by default. Turn it on only when you need deeper troubleshooting logs.',
      debugIndexTitle: isZh ? '记录交互索引' : 'Record Interaction Index',
      debugIndexDesc: isZh
        ? '写入 llm_interactions.jsonl，保留每次调用的摘要、状态与文件引用。'
        : 'Write llm_interactions.jsonl with per-call summaries, statuses, and file references.',
      debugPayloadTitle: isZh ? '记录完整 Prompts / Responses' : 'Record Full Prompts / Responses',
      debugPayloadDesc: isZh
        ? '额外写入 logs/prompts 与 logs/responses 下的完整文件。仅在开启交互索引后生效。'
        : 'Also persist full prompt/response files under logs/prompts and logs/responses. Only works when interaction index logging is enabled.',
      debugSave: isZh ? '保存调试设置' : 'Save Debug Settings',
      debugWarning: isZh
        ? '注意：完整日志会增加磁盘占用，并可能记录敏感业务上下文。'
        : 'Warning: full payload logging increases disk usage and may capture sensitive business context.',
    };
  }, [i18n.language]);

  const dangerCopy = useMemo(() => {
    const isZh = i18n.language.toLowerCase().startsWith('zh');
    return {
      tab: isZh ? '危险区域' : 'DANGER ZONE',
      title: isZh ? '删除项目' : 'Delete Project',
      description: isZh 
        ? '永久删除此项目及其所有关联资产（版本、产出物、配置等）。此操作无法撤销。' 
        : 'Permanently delete this project and all its associated assets (versions, artifacts, configs, etc.). This action cannot be undone.',
      button: isZh ? '删除项目' : 'Delete Project',
      confirmTitle: isZh ? '确认删除项目？' : 'Confirm Delete Project?',
      confirmDescription: isZh 
        ? '在确认删除之前，请查看以下将要被清理的资产清单：' 
        : 'Before confirming deletion, please review the following list of assets that will be cleared:',
      assetsVersions: isZh ? '个版本' : ' versions',
      assetsFiles: isZh ? '个文件' : ' files',
      assetsSize: isZh ? '总计大小' : 'Total size',
      assetsConfigs: isZh ? '项配置 (仓库/数据库/模型等)' : ' configs (repos/dbs/models etc.)',
      deleteSuccess: isZh ? '项目已成功删除。' : 'Project deleted successfully.',
      deleteError: isZh ? '无法删除项目。请确保没有正在运行的版本。' : 'Cannot delete project. Make sure no versions are running.',
      finalConfirm: isZh ? '我确定要删除此项目' : 'I am sure I want to delete this project',
    };
  }, [i18n.language]);

  const loadAll = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [repoRes, dbRes, kbRes, expertRes, _llmRes, modelRes, debugRes] = await Promise.all([
        api.getRepositoryConfigs(projectId),
        api.getDatabaseConfigs(projectId),
        api.getKnowledgeBaseConfigs(projectId),
        api.getExpertConfigs(projectId),
        api.getProjectLlmConfig(projectId),
        api.getProjectModels(projectId),
        api.getProjectDebugConfig(projectId),
      ]);
      setRepositories(repoRes.repositories || []);
      setDatabases(dbRes.databases || []);
      setKnowledgeBases(kbRes.knowledge_bases || []);
      setExperts(expertRes.experts || []);
      setModels(modelRes.models || []);
      setDebugConfig({
        llm_interaction_logging_enabled: Boolean(debugRes.llm_interaction_logging_enabled),
        llm_full_payload_logging_enabled: Boolean(debugRes.llm_full_payload_logging_enabled),
      });
    } catch (error) {
      console.error('Failed to load project configurations:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, [projectId]);

  const loadAssetsSummary = async () => {
    if (!projectId) return;
    setLoadingSummary(true);
    setDeleteError(null);
    try {
      const summary = await api.getProjectAssetsSummary(projectId);
      setAssetsSummary(summary);
    } catch (err: any) {
      console.error('Failed to load assets summary:', err);
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!projectId) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteProject(projectId);
      setIsDeleteModalOpen(false);
      navigate('/');
    } catch (err: any) {
      setDeleteError(err.response?.data?.detail || dangerCopy.deleteError);
    } finally {
      setDeleting(false);
    }
  };

  const saveRepositoryModal = async (repo: RepositoryConfig) => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await api.saveRepositoryConfig(projectId, {
        ...repo,
        branch: repo.branch || 'main',
        type: repo.type || 'git',
        token: repo.token?.trim() ? repo.token.trim() : undefined,
      });
      setSaving(false);
      setIsSaved(true);
      await loadAll();
      setEditingRepo(prev => prev ? { ...prev, token: '', has_token: true } : null);
      setTimeout(() => setIsSaved(false), 3000);
    } catch (error: any) {
      setSaving(false);
      setIsSaved(false);
      setTestResult({ success: false, message: error?.message || 'Failed to save repository.' });
    }
  };

  const saveDatabaseModal = async (db: DatabaseConfig) => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await api.saveDatabaseConfig(projectId, {
        ...db,
        port: Number(db.port),
        schema_filter: db.schema_filter || [],
        password: db.password?.trim() ? db.password.trim() : undefined,
      });
      setSaving(false);
      setIsSaved(true);
      await loadAll();
      setEditingDb(prev => prev ? { ...prev, password: '', has_password: true } : null);
      setTimeout(() => setIsSaved(false), 3000);
    } catch (error: any) {
      setSaving(false);
      setIsSaved(false);
      setTestResult({ success: false, message: error?.message || 'Failed to save database.' });
    }
  };

  const saveKnowledgeBaseModal = async (kb: KnowledgeBaseConfig) => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await api.saveKnowledgeBaseConfig(projectId, {
        ...kb,
        includes: kb.includes || [],
      });
      setSaving(false);
      setIsSaved(true);
      await loadAll();
      setTimeout(() => setIsSaved(false), 3000);
    } catch (error: any) {
      setSaving(false);
      setIsSaved(false);
      setTestResult({ success: false, message: error?.message || 'Failed to save knowledge base.' });
    }
  };

  const saveExperts = async () => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await Promise.all(
        experts.map((item) =>
          api.saveExpertConfig(projectId, {
            id: item.id,
            name: item.name,
            enabled: item.enabled,
            description: item.description,
          }),
        ),
      );
      setIsSaved(true);
      await loadAll();
      setTimeout(() => setIsSaved(false), 2000);
    } catch {
    } finally {
      setSaving(false);
    }
  };

  const saveModel = async (model: ModelConfig) => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await api.saveProjectModel(projectId, {
        ...model,
        api_key: model.api_key?.trim() ? model.api_key.trim() : undefined,
        headers: parseHeadersJson(model.headers),
      });
      setSaving(false);
      setIsSaved(true);
      
      // Refresh the list to get updated metadata (has_api_key etc.)
      await loadAll();
      
      // Keep modal open but clear the temporary API key so it shows the "configured" placeholder
      setEditingModel(prev => prev ? { ...prev, api_key: '', has_api_key: true } : null);
      
      // Clear success state after 3 seconds but keep modal open
      setTimeout(() => {
        setIsSaved(false);
      }, 3000);
    } catch (error: any) {
      setSaving(false);
      setIsSaved(false);
      setTestResult({ success: false, message: error?.message || 'Failed to save model.' });
    }
  };

  const saveDebugSettings = async () => {
    if (!projectId) return;
    setSaving(true);
    setIsSaved(false);
    try {
      await api.saveProjectDebugConfig(projectId, {
        llm_interaction_logging_enabled: Boolean(debugConfig.llm_interaction_logging_enabled),
        llm_full_payload_logging_enabled: Boolean(
          debugConfig.llm_interaction_logging_enabled && debugConfig.llm_full_payload_logging_enabled,
        ),
      });
      setIsSaved(true);
      await loadAll();
      setTimeout(() => setIsSaved(false), 2000);
    } catch {
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    if (!projectId || !modelId) return;
    if (!window.confirm(t('common.confirmDelete'))) return;
    try {
      await api.deleteProjectModel(projectId, modelId);
      await loadAll();
    } catch {
    }
  };

  const handleDeleteRepository = async (repoId: string) => {
    if (!projectId || !repoId) return;
    try {
      await api.deleteRepositoryConfig(projectId, repoId);
      await loadAll();
    } catch {
    }
  };

  const handleDeleteDatabase = async (dbId: string) => {
    if (!projectId || !dbId) return;
    try {
      await api.deleteDatabaseConfig(projectId, dbId);
      await loadAll();
    } catch {
    }
  };

  const handleDeleteKnowledgeBase = async (kbId: string) => {
    if (!projectId || !kbId) return;
    try {
      await api.deleteKnowledgeBaseConfig(projectId, kbId);
      await loadAll();
    } catch {
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <div className="mx-auto max-w-[1480px] p-4 sm:p-5 lg:p-6">
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <Link to={backTo} className="p-2 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-400 hover:text-indigo-600 transition-all">
              <ArrowLeft size={20} />
            </Link>
            <div>
              <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest mb-0.5">{t('projectConfig.eyebrow')}</div>
              <h1 className="text-2xl font-black text-gray-900 uppercase flex items-center gap-3">
                <Settings2 size={24} className="text-indigo-600" />
                {t('projectConfig.title')}
              </h1>
              <p className="text-sm text-gray-500 mt-1">{t('projectConfig.description')}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void loadAll()}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase text-gray-600 hover:text-indigo-600 hover:border-indigo-200 transition-all shadow-sm"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              {t('common.refresh')}
            </button>
            <LanguageSwitcher />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-3">
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-1.5">
              <button
                onClick={() => setActiveTab('repositories')}
                className={`w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'repositories' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <FolderGit2 size={16} />
                {t('projectConfig.tabs.repositories')}
              </button>
              <button
                onClick={() => setActiveTab('databases')}
                className={`mt-1 w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'databases' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Database size={16} />
                {t('projectConfig.tabs.databases')}
              </button>
              <button
                onClick={() => setActiveTab('knowledge')}
                className={`mt-1 w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'knowledge' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <BookOpen size={16} />
                {t('projectConfig.tabs.knowledge')}
              </button>
              <button
                onClick={() => setActiveTab('experts')}
                className={`mt-1 w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'experts' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Bot size={16} />
                {expertCopy.tab}
              </button>
              <button
                onClick={() => setActiveTab('llm')}
                className={`mt-1 w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'llm' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Cpu size={16} />
                {llmCopy.tab}
              </button>
              <button
                onClick={() => {
                  setActiveTab('danger');
                  void loadAssetsSummary();
                }}
                className={`mt-1 w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-bold uppercase tracking-wider transition-all ${activeTab === 'danger' ? 'bg-rose-600 text-white shadow-lg shadow-rose-100' : 'text-rose-500 hover:bg-rose-50'}`}
              >
                <AlertTriangle size={16} />
                {dangerCopy.tab}
              </button>
            </div>
          </div>

          <div className="lg:col-span-9">
            {activeTab === 'repositories' && (
              <section className="space-y-4">
                <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{t('projectConfig.repositories.eyebrow')}</div>
                      <h2 className="text-xl font-black text-gray-900">{t('projectConfig.repositories.title')}</h2>
                    </div>
                    <button
                      onClick={() => {
                        setEditingRepo(createRepository());
                        setIsNewRepo(true);
                        setTestResult(null);
                        setIsRepoModalOpen(true);
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all"
                    >
                      <Plus size={14} />
                      {t('projectConfig.actions.addRepo')}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {repositories.map((repo) => (
                      <div
                        key={repo.id}
                        onClick={() => {
                          setEditingRepo({ ...repo, token: '' });
                          setIsNewRepo(false);
                          setTestResult(null);
                          setIsRepoModalOpen(true);
                        }}
                        className="group relative flex cursor-pointer flex-col justify-between gap-2.5 rounded-2xl border border-gray-200 bg-white p-3.5 transition-all hover:border-indigo-200 hover:shadow-md"
                      >
                        <div className="flex items-start justify-between">
                          <div className="min-w-0">
                            <span className="text-sm font-black text-gray-900 truncate group-hover:text-indigo-600 transition-colors">{repo.name}</span>
                            <div className="text-[10px] font-mono text-gray-400 mt-1 flex items-center gap-2">
                              <span className="uppercase">{repo.type || 'git'}</span>
                              <span className="w-1 h-1 rounded-full bg-gray-300" />
                              <span className="truncate">{repo.url}</span>
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleDeleteRepository(repo.id);
                            }}
                            className="rounded-lg p-1.5 text-gray-400 transition-all hover:bg-rose-50 hover:text-rose-600"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="flex items-center gap-2">
                          {repo.branch && (
                            <span className="px-1.5 py-0.5 rounded-md bg-gray-100 text-gray-500 text-[8px] font-bold uppercase">{repo.branch}</span>
                          )}
                          {repo.has_token && (
                            <span className="px-1.5 py-0.5 rounded-md bg-emerald-50 text-emerald-600 text-[8px] font-bold uppercase">Token Configured</span>
                          )}
                        </div>
                        {repo.description && <p className="text-[10px] text-gray-500 line-clamp-2">{repo.description}</p>}
                      </div>
                    ))}
                    {repositories.length === 0 && (
                      <div className="xl:col-span-2 rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">{t('projectConfig.repositories.empty')}</div>
                    )}
                  </div>
                </div>

                {isRepoModalOpen && editingRepo && (
                  <ConfigEditorModal
                    title={isNewRepo ? (t('projectConfig.actions.addRepo') || 'Add Repository') : (t('projectConfig.repositories.editRepo') || 'Edit Repository')}
                    icon={<FolderGit2 size={18} className="text-indigo-600" />}
                    onClose={() => {
                      setIsRepoModalOpen(false);
                      setTestResult(null);
                    }}
                    footer={
                      <div className="space-y-3">
                        {testResult && (
                          <div className={`flex items-start gap-3 rounded-xl border p-3 ${testResult.success ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-rose-100 bg-rose-50 text-rose-800'} animate-in fade-in slide-in-from-top-2 duration-300`}>
                            <div className="mt-0.5">{testResult.success ? <CheckCircle size={16} className="text-emerald-500" /> : <XCircle size={16} className="text-rose-500" />}</div>
                            <div className="min-w-0 flex-1">
                              <p className="mb-1 text-xs font-black uppercase leading-none tracking-tight">{testResult.success ? 'Success' : 'Error'}</p>
                              <p className="text-[11px] font-medium leading-normal break-words opacity-90">{testResult.message}</p>
                            </div>
                          </div>
                        )}
                        <div className="flex flex-col gap-3 sm:flex-row">
                          <button onClick={() => void testRepoConfig()} disabled={testingRepo || !editingRepo.url} className="flex-1 flex items-center justify-center gap-2 py-3 bg-white border-2 border-gray-100 text-gray-700 rounded-2xl font-black text-xs uppercase tracking-widest hover:border-indigo-100 hover:text-indigo-600 transition-all disabled:opacity-50">
                            {testingRepo ? <RefreshCw size={16} className="animate-spin" /> : <Activity size={16} />}
                            {testingRepo ? llmCopy.testing : llmCopy.testModel}
                          </button>
                          <button onClick={() => void saveRepositoryModal(editingRepo)} disabled={saving || isSaved || !editingRepo.id || !editingRepo.name || !editingRepo.url} className={`flex-[1.5] flex items-center justify-center gap-2 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-lg disabled:opacity-50 ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}>
                            {saving ? <RefreshCw size={16} className="animate-spin" /> : (isSaved ? <CheckCircle size={16} /> : null)}
                            {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : t('common.save'))}
                          </button>
                          <button onClick={() => { setIsRepoModalOpen(false); setTestResult(null); }} className="py-3 px-4 text-gray-400 font-bold text-[10px] uppercase tracking-widest hover:text-gray-600 transition-all">
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    }
                  >
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.id')}</label>
                        <input value={editingRepo.id} onChange={(e) => setEditingRepo({ ...editingRepo, id: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.name')}</label>
                        <input value={editingRepo.name} onChange={(e) => setEditingRepo({ ...editingRepo, name: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.url')}</label>
                        <input value={editingRepo.url} onChange={(e) => setEditingRepo({ ...editingRepo, url: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.branch')}</label>
                        <input value={editingRepo.branch || ''} onChange={(e) => setEditingRepo({ ...editingRepo, branch: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.username')}</label>
                        <input value={editingRepo.username || ''} onChange={(e) => setEditingRepo({ ...editingRepo, username: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.repositories.placeholders.localPath')}</label>
                        <input value={editingRepo.local_path || ''} onChange={(e) => setEditingRepo({ ...editingRepo, local_path: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">
                          {editingRepo.has_token ? t('projectConfig.repositories.placeholders.tokenExisting') : t('projectConfig.repositories.placeholders.token')}
                        </label>
                        <input type="password" value={editingRepo.token || ''} onChange={(e) => setEditingRepo({ ...editingRepo, token: e.target.value })} placeholder={editingRepo.has_token ? (t('common.keepCurrent') || 'Leave blank to keep current') : t('projectConfig.repositories.placeholders.token')} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.placeholders.description')}</label>
                        <textarea value={editingRepo.description || ''} onChange={(e) => setEditingRepo({ ...editingRepo, description: e.target.value })} className="min-h-14 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                    </div>
                  </ConfigEditorModal>
                )}
              </section>
            )}

            {activeTab === 'databases' && (
              <section className="space-y-4">
                <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{t('projectConfig.databases.eyebrow')}</div>
                      <h2 className="text-xl font-black text-gray-900">{t('projectConfig.databases.title')}</h2>
                    </div>
                    <button
                      onClick={() => {
                        setEditingDb(createDatabase());
                        setIsNewDb(true);
                        setTestResult(null);
                        setIsDbModalOpen(true);
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all"
                    >
                      <Plus size={14} />
                      {t('projectConfig.actions.addDatabase')}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {databases.map((db) => (
                      <div
                        key={db.id}
                        onClick={() => {
                          setEditingDb({ ...db, password: '' });
                          setIsNewDb(false);
                          setTestResult(null);
                          setIsDbModalOpen(true);
                        }}
                        className="group relative flex cursor-pointer flex-col justify-between gap-2.5 rounded-2xl border border-gray-200 bg-white p-3.5 transition-all hover:border-indigo-200 hover:shadow-md"
                      >
                        <div className="flex items-start justify-between">
                          <div className="min-w-0">
                            <span className="text-sm font-black text-gray-900 truncate group-hover:text-indigo-600 transition-colors">{db.name}</span>
                            <div className="text-[10px] font-mono text-gray-400 mt-1 flex items-center gap-2">
                              <span className="uppercase">{db.type}</span>
                              <span className="w-1 h-1 rounded-full bg-gray-300" />
                              <span>{db.host}:{db.port}</span>
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleDeleteDatabase(db.id);
                            }}
                            className="rounded-lg p-1.5 text-gray-400 transition-all hover:bg-rose-50 hover:text-rose-600"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded-md bg-gray-100 text-gray-500 text-[8px] font-bold uppercase">{db.database}</span>
                          {db.has_password && (
                            <span className="px-1.5 py-0.5 rounded-md bg-emerald-50 text-emerald-600 text-[8px] font-bold uppercase">Password Configured</span>
                          )}
                        </div>
                        {db.description && <p className="text-[10px] text-gray-500 line-clamp-2">{db.description}</p>}
                      </div>
                    ))}
                    {databases.length === 0 && (
                      <div className="xl:col-span-2 rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">{t('projectConfig.databases.empty')}</div>
                    )}
                  </div>
                </div>

                {isDbModalOpen && editingDb && (
                  <ConfigEditorModal
                    title={isNewDb ? (t('projectConfig.actions.addDatabase') || 'Add Database') : (t('projectConfig.databases.editDatabase') || 'Edit Database')}
                    icon={<Database size={18} className="text-indigo-600" />}
                    onClose={() => {
                      setIsDbModalOpen(false);
                      setTestResult(null);
                    }}
                    footer={
                      <div className="space-y-3">
                        {testResult && (
                          <div className={`flex items-start gap-3 rounded-xl border p-3 ${testResult.success ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-rose-100 bg-rose-50 text-rose-800'} animate-in fade-in slide-in-from-top-2 duration-300`}>
                            <div className="mt-0.5">{testResult.success ? <CheckCircle size={16} className="text-emerald-500" /> : <XCircle size={16} className="text-rose-500" />}</div>
                            <div className="min-w-0 flex-1">
                              <p className="mb-1 text-xs font-black uppercase leading-none tracking-tight">{testResult.success ? 'Success' : 'Error'}</p>
                              <p className="text-[11px] font-medium leading-normal break-words opacity-90">{testResult.message}</p>
                            </div>
                          </div>
                        )}
                        <div className="flex flex-col gap-3 sm:flex-row">
                          <button onClick={() => void testDbConfig()} disabled={testingDb || !editingDb.host} className="flex-1 flex items-center justify-center gap-2 py-3 bg-white border-2 border-gray-100 text-gray-700 rounded-2xl font-black text-xs uppercase tracking-widest hover:border-indigo-100 hover:text-indigo-600 transition-all disabled:opacity-50">
                            {testingDb ? <RefreshCw size={16} className="animate-spin" /> : <Activity size={16} />}
                            {testingDb ? llmCopy.testing : llmCopy.testModel}
                          </button>
                          <button onClick={() => void saveDatabaseModal(editingDb)} disabled={saving || isSaved || !editingDb.id || !editingDb.name || !editingDb.host || !editingDb.database} className={`flex-[1.5] flex items-center justify-center gap-2 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-lg disabled:opacity-50 ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}>
                            {saving ? <RefreshCw size={16} className="animate-spin" /> : (isSaved ? <CheckCircle size={16} /> : null)}
                            {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : t('common.save'))}
                          </button>
                          <button onClick={() => { setIsDbModalOpen(false); setTestResult(null); }} className="py-3 px-4 text-gray-400 font-bold text-[10px] uppercase tracking-widest hover:text-gray-600 transition-all">
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    }
                  >
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.id')}</label>
                        <input value={editingDb.id} onChange={(e) => setEditingDb({ ...editingDb, id: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.name')}</label>
                        <input value={editingDb.name} onChange={(e) => setEditingDb({ ...editingDb, name: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">Type</label>
                        <select value={editingDb.type} onChange={(e) => setEditingDb({ ...editingDb, type: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500">
                          <option value="postgresql">PostgreSQL</option>
                          <option value="opengauss">openGauss</option>
                          <option value="dws">DWS</option>
                          <option value="mysql">MySQL</option>
                          <option value="oracle">Oracle</option>
                          <option value="sqlite">SQLite</option>
                        </select>
                      </div>
                      <div className="xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.host')}</label>
                        <input value={editingDb.host} onChange={(e) => setEditingDb({ ...editingDb, host: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.port')}</label>
                        <input value={editingDb.port} onChange={(e) => setEditingDb({ ...editingDb, port: Number(e.target.value || 0) })} type="number" className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.database')}</label>
                        <input value={editingDb.database} onChange={(e) => setEditingDb({ ...editingDb, database: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.username')}</label>
                        <input value={editingDb.username || ''} onChange={(e) => setEditingDb({ ...editingDb, username: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">
                          {editingDb.has_password ? t('projectConfig.databases.placeholders.passwordExisting') : t('projectConfig.databases.placeholders.password')}
                        </label>
                        <input type="password" value={editingDb.password || ''} onChange={(e) => setEditingDb({ ...editingDb, password: e.target.value })} placeholder={editingDb.has_password ? (t('common.keepCurrent') || 'Leave blank to keep current') : t('projectConfig.databases.placeholders.password')} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.databases.placeholders.schemaFilter')}</label>
                        <textarea value={(editingDb.schema_filter || []).join('\n')} onChange={(e) => setEditingDb({ ...editingDb, schema_filter: splitMultiline(e.target.value) })} className="min-h-14 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 font-mono text-xs outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.placeholders.description')}</label>
                        <textarea value={editingDb.description || ''} onChange={(e) => setEditingDb({ ...editingDb, description: e.target.value })} className="min-h-14 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                    </div>
                  </ConfigEditorModal>
                )}
              </section>
            )}

            {activeTab === 'knowledge' && (
              <section className="space-y-4">
                <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{t('projectConfig.knowledge.eyebrow')}</div>
                      <h2 className="text-xl font-black text-gray-900">{t('projectConfig.knowledge.title')}</h2>
                    </div>
                    <button
                      onClick={() => {
                        setEditingKb(createKnowledgeBase());
                        setIsNewKb(true);
                        setTestResult(null);
                        setIsKbModalOpen(true);
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all"
                    >
                      <Plus size={14} />
                      {t('projectConfig.actions.addKnowledgeBase')}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {knowledgeBases.map((kb) => (
                      <div
                        key={kb.id}
                        onClick={() => {
                          setEditingKb({ ...kb });
                          setIsNewKb(false);
                          setTestResult(null);
                          setIsKbModalOpen(true);
                        }}
                        className="group relative flex cursor-pointer flex-col justify-between gap-2.5 rounded-2xl border border-gray-200 bg-white p-3.5 transition-all hover:border-indigo-200 hover:shadow-md"
                      >
                        <div className="flex items-start justify-between">
                          <div className="min-w-0">
                            <span className="text-sm font-black text-gray-900 truncate group-hover:text-indigo-600 transition-colors">{kb.name}</span>
                            <div className="text-[10px] font-mono text-gray-400 mt-1 flex items-center gap-2">
                              <span className="uppercase">{kb.type}</span>
                              <span className="w-1 h-1 rounded-full bg-gray-300" />
                              <span className="truncate">{kb.type === 'local' ? (kb.path || '') : (kb.index_url || '')}</span>
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleDeleteKnowledgeBase(kb.id);
                            }}
                            className="rounded-lg p-1.5 text-gray-400 transition-all hover:bg-rose-50 hover:text-rose-600"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                        {kb.description && <p className="text-[10px] text-gray-500 line-clamp-2">{kb.description}</p>}
                      </div>
                    ))}
                    {knowledgeBases.length === 0 && (
                      <div className="xl:col-span-2 rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">{t('projectConfig.knowledge.empty')}</div>
                    )}
                  </div>
                </div>

                {isKbModalOpen && editingKb && (
                  <ConfigEditorModal
                    title={isNewKb ? (t('projectConfig.actions.addKnowledgeBase') || 'Add Knowledge Base') : (t('projectConfig.knowledge.editKnowledgeBase') || 'Edit Knowledge Base')}
                    icon={<BookOpen size={18} className="text-indigo-600" />}
                    onClose={() => {
                      setIsKbModalOpen(false);
                      setTestResult(null);
                    }}
                    footer={
                      <div className="space-y-3">
                        {testResult && (
                          <div className={`flex items-start gap-3 rounded-xl border p-3 ${testResult.success ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-rose-100 bg-rose-50 text-rose-800'} animate-in fade-in slide-in-from-top-2 duration-300`}>
                            <div className="mt-0.5">{testResult.success ? <CheckCircle size={16} className="text-emerald-500" /> : <XCircle size={16} className="text-rose-500" />}</div>
                            <div className="min-w-0 flex-1">
                              <p className="mb-1 text-xs font-black uppercase leading-none tracking-tight">{testResult.success ? 'Success' : 'Error'}</p>
                              <p className="text-[11px] font-medium leading-normal break-words opacity-90">{testResult.message}</p>
                            </div>
                          </div>
                        )}
                        <div className="flex flex-col gap-3 sm:flex-row">
                          <button onClick={() => void testKbConfig()} disabled={testingKb || (editingKb.type === 'local' ? !editingKb.path : !editingKb.index_url)} className="flex-1 flex items-center justify-center gap-2 py-3 bg-white border-2 border-gray-100 text-gray-700 rounded-2xl font-black text-xs uppercase tracking-widest hover:border-indigo-100 hover:text-indigo-600 transition-all disabled:opacity-50">
                            {testingKb ? <RefreshCw size={16} className="animate-spin" /> : <Activity size={16} />}
                            {testingKb ? llmCopy.testing : llmCopy.testModel}
                          </button>
                          <button onClick={() => void saveKnowledgeBaseModal(editingKb)} disabled={saving || isSaved || !editingKb.id || !editingKb.name} className={`flex-[1.5] flex items-center justify-center gap-2 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-lg disabled:opacity-50 ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}>
                            {saving ? <RefreshCw size={16} className="animate-spin" /> : (isSaved ? <CheckCircle size={16} /> : null)}
                            {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : t('common.save'))}
                          </button>
                          <button onClick={() => { setIsKbModalOpen(false); setTestResult(null); }} className="py-3 px-4 text-gray-400 font-bold text-[10px] uppercase tracking-widest hover:text-gray-600 transition-all">
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    }
                  >
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.knowledge.placeholders.id')}</label>
                        <input value={editingKb.id} onChange={(e) => setEditingKb({ ...editingKb, id: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.knowledge.placeholders.name')}</label>
                        <input value={editingKb.name} onChange={(e) => setEditingKb({ ...editingKb, name: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">Type</label>
                        <select value={editingKb.type} onChange={(e) => setEditingKb({ ...editingKb, type: e.target.value })} className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500">
                          <option value="local">{t('projectConfig.knowledge.types.local')}</option>
                          <option value="remote">{t('projectConfig.knowledge.types.remote')}</option>
                        </select>
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">
                          {editingKb.type === 'local' ? t('projectConfig.knowledge.placeholders.path') : t('projectConfig.knowledge.placeholders.indexUrl')}
                        </label>
                        <input
                          value={editingKb.type === 'local' ? (editingKb.path || '') : (editingKb.index_url || '')}
                          onChange={(e) => setEditingKb(editingKb.type === 'local' ? { ...editingKb, path: e.target.value } : { ...editingKb, index_url: e.target.value })}
                          placeholder={editingKb.type === 'local' ? t('projectConfig.knowledge.placeholders.path') : t('projectConfig.knowledge.placeholders.indexUrl')}
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.knowledge.placeholders.includes')}</label>
                        <textarea value={(editingKb.includes || []).join('\n')} onChange={(e) => setEditingKb({ ...editingKb, includes: splitMultiline(e.target.value) })} className="min-h-14 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{t('projectConfig.placeholders.description')}</label>
                        <textarea value={editingKb.description || ''} onChange={(e) => setEditingKb({ ...editingKb, description: e.target.value })} className="min-h-14 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500" />
                      </div>
                    </div>
                  </ConfigEditorModal>
                )}
              </section>
            )}

            {activeTab === 'experts' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 sm:p-6 space-y-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{expertCopy.eyebrow}</div>
                    <h2 className="text-xl font-black text-gray-900">{expertCopy.title}</h2>
                  </div>
                  <button
                    onClick={() => void saveExperts()}
                    disabled={saving || isSaved}
                    className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase transition-all shadow-lg disabled:opacity-50 min-w-[100px] justify-center ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}
                  >
                    {saving ? <RefreshCw size={14} className="animate-spin" /> : (isSaved ? <CheckCircle size={14} /> : <Save size={14} />)}
                    {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : t('common.save'))}
                  </button>

                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {experts.map((expert, index) => (
                    <div key={expert.id} className="rounded-xl border border-gray-200 bg-white p-3 transition-all hover:border-indigo-200 hover:shadow-sm">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-bold text-gray-900 truncate">{expert.name}</div>
                          <div className={`mt-1.5 text-[10px] font-black uppercase tracking-wider ${expert.enabled ? 'text-emerald-600' : 'text-gray-400'}`}>
                            {expert.enabled ? expertCopy.enabled : expertCopy.disabled}
                          </div>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={expert.enabled}
                          aria-label={`${expert.name} ${expert.enabled ? expertCopy.enabled : expertCopy.disabled}`}
                          onClick={() => setExperts((prev) => prev.map((item, i) => i === index ? { ...item, enabled: !item.enabled } : item))}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 ${expert.enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${expert.enabled ? 'translate-x-6' : 'translate-x-1'}`}
                          />
                        </button>
                      </div>
                    </div>
                  ))}
                  {experts.length === 0 && <div className="col-span-full rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">{expertCopy.empty}</div>}
                </div>
              </section>
            )}

            {activeTab === 'llm' && (
              <section className="space-y-4">
                <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{llmCopy.eyebrow}</div>
                      <h2 className="text-xl font-black text-gray-900">{llmCopy.title}</h2>
                      <p className="text-sm text-gray-500 mt-1">{llmCopy.description}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => {
                          setEditingModel(createModel());
                          setTestResult(null);
                          setIsModelModalOpen(true);
                        }}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all"
                      >
                        <Plus size={14} />
                        {llmCopy.addModel}
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {models.map((model) => (
                      <div
                        key={model.id}
                        onClick={() => {
                          setEditingModel({ ...model, api_key: '' });
                          setTestResult(null);
                          setIsModelModalOpen(true);
                        }}
                        className={`group relative flex cursor-pointer flex-col justify-between gap-2.5 rounded-2xl border p-3.5 transition-all ${model.is_default
                          ? 'border-indigo-200 bg-indigo-50/30 hover:shadow-md hover:border-indigo-300'
                          : 'border-gray-200 bg-white hover:border-indigo-200 hover:shadow-md'
                          }`}
                      >
                        <div className="flex items-start justify-between">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-black text-gray-900 truncate group-hover:text-indigo-600 transition-colors">{model.name}</span>
                              {model.is_default && (
                                <span className="px-1.5 py-0.5 rounded-md bg-indigo-600 text-white text-[8px] font-black uppercase tracking-wider">
                                  {llmCopy.defaultLabel}
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] font-mono text-gray-400 mt-1 flex items-center gap-2">
                              <span className="uppercase">{model.provider}</span>
                              <span className="w-1 h-1 rounded-full bg-gray-300" />
                              <span>{model.model_name}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                void handleDeleteModel(model.id);
                              }}
                              className="rounded-lg p-1.5 text-gray-400 transition-all hover:bg-rose-50 hover:text-rose-600"
                              title={llmCopy.deleteModel}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                        {model.description && <p className="text-[10px] text-gray-500 line-clamp-2">{model.description}</p>}
                      </div>
                    ))}
                    {models.length === 0 && (
                      <div className="xl:col-span-2 rounded-2xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-400">
                        {t('projectConfig.llm.empty') || 'No models configured yet.'}
                      </div>
                    )}
                  </div>
                </div>

                {isModelModalOpen && editingModel && (
                  <ConfigEditorModal
                    title={editingModel.id ? llmCopy.editModel : llmCopy.addModel}
                    icon={<Cpu size={18} className="text-indigo-600" />}
                    onClose={() => {
                      setIsModelModalOpen(false);
                      setTestResult(null);
                    }}
                    footer={
                      <div className="space-y-3">
                        {testResult && (
                          <div className={`flex items-start gap-3 rounded-xl border p-3 ${testResult.success ? 'border-emerald-100 bg-emerald-50 text-emerald-800' : 'border-rose-100 bg-rose-50 text-rose-800'} animate-in fade-in slide-in-from-top-2 duration-300`}>
                            <div className="mt-0.5">
                              {testResult.success ? <CheckCircle size={16} className="text-emerald-500" /> : <XCircle size={16} className="text-rose-500" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="mb-1 text-xs font-black uppercase leading-none tracking-tight">
                                {testResult.success ? 'Success' : 'Error'}
                              </p>
                              <p className="text-[11px] font-medium leading-normal break-words opacity-90">
                                {testResult.success ? llmCopy.testSuccess : `${llmCopy.testFailed} ${testResult.message}`}
                              </p>
                            </div>
                          </div>
                        )}

                        <div className="flex flex-col gap-3 sm:flex-row">
                          <button
                            onClick={() => void testModelConfig()}
                            disabled={testingModel || !editingModel.model_name}
                            className="flex-1 flex items-center justify-center gap-2 py-3 bg-white border-2 border-gray-100 text-gray-700 rounded-2xl font-black text-xs uppercase tracking-widest hover:border-indigo-100 hover:text-indigo-600 transition-all disabled:opacity-50"
                          >
                            {testingModel ? <RefreshCw size={16} className="animate-spin" /> : <Activity size={16} />}
                            {testingModel ? llmCopy.testing : llmCopy.testModel}
                          </button>
                          <button
                            onClick={() => void saveModel(editingModel)}
                            disabled={saving || isSaved || !editingModel.name || !editingModel.model_name}
                            className={`flex-[1.5] flex items-center justify-center gap-2 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-lg disabled:opacity-50 ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}
                          >
                            {saving ? <RefreshCw size={16} className="animate-spin" /> : (isSaved ? <CheckCircle size={16} /> : null)}
                            {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : llmCopy.saved)}
                          </button>
                          <button
                            onClick={() => {
                              setIsModelModalOpen(false);
                              setTestResult(null);
                            }}
                            className="py-3 px-4 text-gray-400 font-bold text-[10px] uppercase tracking-widest hover:text-gray-600 transition-all"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    }
                  >
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div className="md:col-span-2 xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{llmCopy.modelName}</label>
                        <input
                          value={editingModel.name}
                          onChange={(e) => setEditingModel({ ...editingModel, name: e.target.value })}
                          placeholder="e.g. My Custom GPT-4"
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>

                      <div>
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{llmCopy.provider}</label>
                        <select
                          value={editingModel.provider}
                          onChange={(e) => setEditingModel({ ...editingModel, provider: e.target.value })}
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        >
                          <option value="openai">OpenAI Compatible</option>
                          <option value="gemini">Gemini</option>
                        </select>
                      </div>

                      <div className="md:col-span-2 xl:col-span-1">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{llmCopy.modelId}</label>
                        <input
                          value={editingModel.model_name}
                          onChange={(e) => setEditingModel({ ...editingModel, model_name: e.target.value })}
                          placeholder="gpt-4o"
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>

                      <div className="md:col-span-2 xl:col-span-2">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">{llmCopy.openaiBaseUrl}</label>
                        <input
                          value={editingModel.base_url || ''}
                          onChange={(e) => setEditingModel({ ...editingModel, base_url: e.target.value })}
                          placeholder="https://api.openai.com/v1"
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>

                      <div className="flex items-center gap-3 rounded-2xl border border-gray-100 bg-gray-50 px-3 py-2.5">
                        <button
                          type="button"
                          onClick={() => setEditingModel({ ...editingModel, is_default: !editingModel.is_default })}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${editingModel.is_default ? 'bg-indigo-600' : 'bg-gray-200'}`}
                        >
                          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${editingModel.is_default ? 'translate-x-6' : 'translate-x-1'}`} />
                        </button>
                        <span className="text-xs font-bold text-gray-600">{llmCopy.isDefault}</span>
                      </div>

                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">
                          {llmCopy.enterKey} {editingModel.has_api_key ? `(${llmCopy.saved})` : ''}
                        </label>
                        <input
                          type="password"
                          value={editingModel.api_key || ''}
                          onChange={(e) => setEditingModel({ ...editingModel, api_key: e.target.value })}
                          placeholder={editingModel.has_api_key ? llmCopy.keepCurrent : llmCopy.enterKey}
                          className="w-full rounded-xl border border-gray-100 bg-gray-50 p-2.5 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>

                      <div className="md:col-span-2 xl:col-span-3">
                        <label className="mb-1 block text-[10px] font-black uppercase tracking-widest text-gray-400">
                          Request Headers JSON {editingModel.has_headers ? `(${llmCopy.saved})` : ''}
                        </label>
                        <textarea
                          value={editingModel.headers || ''}
                          onChange={(e) => setEditingModel({ ...editingModel, headers: e.target.value })}
                          placeholder={editingModel.has_headers ? 'Leave blank to keep current headers' : '{"Authorization":"Bearer custom-token"}'}
                          className="min-h-16 w-full resize-none rounded-xl border border-gray-100 bg-gray-50 p-2.5 font-mono text-xs outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                        />
                      </div>
                    </div>
                  </ConfigEditorModal>
                )}

                <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">{llmCopy.debugEyebrow}</div>
                      <h3 className="text-lg font-black text-gray-900">{llmCopy.debugTitle}</h3>
                      <p className="text-sm text-gray-500 mt-1">{llmCopy.debugDescription}</p>
                    </div>
                    <button
                      onClick={() => void saveDebugSettings()}
                      disabled={saving || isSaved}
                      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase transition-all shadow-lg disabled:opacity-50 min-w-[132px] justify-center ${isSaved ? 'bg-emerald-500 text-white shadow-emerald-100' : 'bg-indigo-600 text-white shadow-indigo-100 hover:bg-indigo-700'}`}
                    >
                      {saving ? <RefreshCw size={14} className="animate-spin" /> : (isSaved ? <CheckCircle size={14} /> : <Save size={14} />)}
                      {saving ? t('common.saving') : (isSaved ? t('common.saveSuccess') : llmCopy.debugSave)}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    <div className="rounded-2xl border border-gray-200 bg-gray-50/60 p-3.5 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-black text-gray-900">{llmCopy.debugIndexTitle}</div>
                        <p className="text-xs text-gray-500 mt-1">{llmCopy.debugIndexDesc}</p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={debugConfig.llm_interaction_logging_enabled}
                        onClick={() => setDebugConfig((prev) => ({
                          llm_interaction_logging_enabled: !prev.llm_interaction_logging_enabled,
                          llm_full_payload_logging_enabled: prev.llm_interaction_logging_enabled ? false : prev.llm_full_payload_logging_enabled,
                        }))}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 ${debugConfig.llm_interaction_logging_enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${debugConfig.llm_interaction_logging_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                      </button>
                    </div>

                    <div className={`rounded-2xl border p-3.5 flex items-start justify-between gap-3 ${debugConfig.llm_interaction_logging_enabled ? 'border-gray-200 bg-gray-50/60' : 'border-gray-100 bg-gray-50/30 opacity-60'}`}>
                      <div className="min-w-0">
                        <div className="text-sm font-black text-gray-900">{llmCopy.debugPayloadTitle}</div>
                        <p className="text-xs text-gray-500 mt-1">{llmCopy.debugPayloadDesc}</p>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={debugConfig.llm_full_payload_logging_enabled}
                        disabled={!debugConfig.llm_interaction_logging_enabled}
                        onClick={() => setDebugConfig((prev) => ({
                          ...prev,
                          llm_full_payload_logging_enabled: !prev.llm_full_payload_logging_enabled,
                        }))}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 disabled:cursor-not-allowed ${debugConfig.llm_interaction_logging_enabled && debugConfig.llm_full_payload_logging_enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${debugConfig.llm_interaction_logging_enabled && debugConfig.llm_full_payload_logging_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                      </button>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                    {llmCopy.debugWarning}
                  </div>
                </div>
              </section>
            )}

            {activeTab === 'danger' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-5 sm:p-6 space-y-5">
                <div>
                  <div className="text-[10px] font-black text-rose-500 uppercase tracking-widest mb-2">{dangerCopy.tab}</div>
                  <h2 className="text-xl font-black text-gray-900">{dangerCopy.title}</h2>
                  <p className="text-sm text-gray-500 mt-2">{dangerCopy.description}</p>
                </div>

                <div className="rounded-2xl border border-rose-100 bg-rose-50/50 p-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-rose-100 rounded-xl text-rose-600">
                      <AlertTriangle size={24} />
                    </div>
                    <div>
                      <h3 className="text-sm font-black text-gray-900 uppercase tracking-tight">{dangerCopy.title}</h3>
                      <p className="text-xs text-gray-500 mt-1 max-w-md">{dangerCopy.description}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setIsDeleteModalOpen(true);
                      void loadAssetsSummary();
                    }}
                    className="px-6 py-3 bg-rose-600 text-white rounded-xl font-black text-xs uppercase tracking-widest hover:bg-rose-700 transition-all shadow-lg shadow-rose-100"
                  >
                    {dangerCopy.button}
                  </button>
                </div>

                {/* Deletion Confirmation Modal */}
                {isDeleteModalOpen && (
                  <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
                    <div className="absolute inset-0 bg-gray-900/60 backdrop-blur-sm" onClick={() => !deleting && setIsDeleteModalOpen(false)} />
                    <div className="relative w-full max-w-2xl bg-white rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
                      <div className="p-8 space-y-6">
                        <div className="flex items-center gap-4 text-rose-600">
                          <div className="p-3 bg-rose-50 rounded-2xl">
                            <AlertTriangle size={32} />
                          </div>
                          <div>
                            <h3 className="text-2xl font-black uppercase tracking-tight">{dangerCopy.confirmTitle}</h3>
                            <p className="text-sm font-medium text-gray-500">{dangerCopy.confirmDescription}</p>
                          </div>
                        </div>

                        {loadingSummary ? (
                          <div className="py-12 flex flex-col items-center justify-center gap-4">
                            <RefreshCw size={32} className="text-indigo-600 animate-spin" />
                            <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">{t('common.loading')}</p>
                          </div>
                        ) : assetsSummary ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="rounded-2xl bg-gray-50 p-5 flex items-center gap-4 border border-gray-100">
                              <div className="p-3 bg-white rounded-xl text-indigo-600 shadow-sm">
                                <Settings2 size={20} />
                              </div>
                              <div>
                                <div className="text-lg font-black text-gray-900">{assetsSummary.total_versions}</div>
                                <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{dangerCopy.assetsVersions}</div>
                              </div>
                            </div>
                            <div className="rounded-2xl bg-gray-50 p-5 flex items-center gap-4 border border-gray-100">
                              <div className="p-3 bg-white rounded-xl text-indigo-600 shadow-sm">
                                <FileText size={20} />
                              </div>
                              <div>
                                <div className="text-lg font-black text-gray-900">{assetsSummary.total_files}</div>
                                <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{dangerCopy.assetsFiles}</div>
                              </div>
                            </div>
                            <div className="rounded-2xl bg-gray-50 p-5 flex items-center gap-4 border border-gray-100">
                              <div className="p-3 bg-white rounded-xl text-indigo-600 shadow-sm">
                                <HardDrive size={20} />
                              </div>
                              <div>
                                <div className="text-lg font-black text-gray-900">{assetsSummary.total_size_mb} MB</div>
                                <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{dangerCopy.assetsSize}</div>
                              </div>
                            </div>
                            <div className="rounded-2xl bg-gray-50 p-5 flex items-center gap-4 border border-gray-100">
                              <div className="p-3 bg-white rounded-xl text-indigo-600 shadow-sm">
                                <Cpu size={18} />
                              </div>
                              <div>
                                <div className="text-lg font-black text-gray-900">
                                  {Object.values(assetsSummary.configs).reduce((a, b) => a + b, 0)}
                                </div>
                                <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{dangerCopy.assetsConfigs}</div>
                              </div>
                            </div>
                          </div>
                        ) : null}

                        {deleteError && (
                          <div className="p-4 bg-rose-50 border border-rose-100 rounded-2xl flex items-center gap-3 text-rose-800 text-sm font-medium">
                            <XCircle size={18} className="text-rose-500 shrink-0" />
                            {deleteError}
                          </div>
                        ) }

                        <div className="flex flex-col gap-3 pt-4 border-t border-gray-50">
                          <button
                            onClick={() => void handleDeleteProject()}
                            disabled={deleting}
                            className="w-full py-4 bg-rose-600 text-white rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-rose-700 transition-all shadow-xl shadow-rose-100 disabled:opacity-50"
                          >
                            {deleting ? <RefreshCw size={20} className="animate-spin mx-auto" /> : dangerCopy.finalConfirm}
                          </button>
                          <button
                            onClick={() => setIsDeleteModalOpen(false)}
                            disabled={deleting}
                            className="w-full py-3 text-gray-400 font-bold text-[11px] uppercase tracking-widest hover:text-gray-600 transition-all"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
