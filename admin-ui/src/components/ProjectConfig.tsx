import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, BookOpen, Bot, Cpu, Database, FolderGit2, Plus, RefreshCw, Save, Settings2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { LanguageSwitcher } from './LanguageSwitcher';

type TabKey = 'repositories' | 'databases' | 'knowledge' | 'experts' | 'llm';

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

interface LlmConfigState {
  llm_provider: string;
  openai_api_key: string;
  openai_base_url: string;
  openai_model_name: string;
  gemini_api_key: string;
  gemini_model_name: string;
  has_openai_api_key?: boolean;
  has_gemini_api_key?: boolean;
}

const EMPTY_LLM_CONFIG: LlmConfigState = {
  llm_provider: 'openai',
  openai_api_key: '',
  openai_base_url: '',
  openai_model_name: '',
  gemini_api_key: '',
  gemini_model_name: '',
};

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

export function ProjectConfig() {
  const { t, i18n } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const projectId = id || '';
  const backTo = (location.state as { from?: string } | null)?.from || '/';
  const [activeTab, setActiveTab] = useState<TabKey>('repositories');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [repositories, setRepositories] = useState<RepositoryConfig[]>([]);
  const [databases, setDatabases] = useState<DatabaseConfig[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseConfig[]>([]);
  const [experts, setExperts] = useState<ExpertConfig[]>([]);
  const [llmConfig, setLlmConfig] = useState<LlmConfigState>(EMPTY_LLM_CONFIG);

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
        ? '配置当前项目使用的模型提供商、网关地址、模型名称与密钥；未覆盖时回退系统默认。'
        : 'Configure project-level provider, gateway URL, model names, and API keys. Unset fields fall back to system defaults.',
      refresh: isZh ? '刷新配置' : 'Refresh Config',
      provider: isZh ? '模型提供商' : 'Provider',
      openaiBaseUrl: isZh ? 'OpenAI 网关地址' : 'OpenAI Base URL',
      openaiModel: isZh ? 'OpenAI 模型名' : 'OpenAI Model',
      geminiModel: isZh ? 'Gemini 模型名' : 'Gemini Model',
      openaiKey: isZh ? 'OpenAI API Key' : 'OpenAI API Key',
      geminiKey: isZh ? 'Gemini API Key' : 'Gemini API Key',
      saved: isZh ? '已保存' : 'saved',
      keepCurrent: isZh ? '留空则保持当前密钥' : 'Leave blank to keep current key',
      enterKey: isZh ? '请输入 API Key' : 'Enter API key',
      saveSuccess: isZh ? '大模型配置已保存。' : 'LLM config saved.',
      saveError: isZh ? '保存大模型配置失败。' : 'Failed to save LLM config.',
      loadError: isZh ? '加载大模型配置失败。' : 'Failed to load LLM config.',
    };
  }, [i18n.language]);

  const loadAll = async () => {
    if (!projectId) return;
    setLoading(true);
    setMessage(null);
    try {
      const [repoRes, dbRes, kbRes, expertRes, llmRes] = await Promise.all([
        api.getRepositoryConfigs(projectId),
        api.getDatabaseConfigs(projectId),
        api.getKnowledgeBaseConfigs(projectId),
        api.getExpertConfigs(projectId),
        api.getProjectLlmConfig(projectId),
      ]);
      setRepositories(repoRes.repositories || []);
      setDatabases(dbRes.databases || []);
      setKnowledgeBases(kbRes.knowledge_bases || []);
      setExperts(expertRes.experts || []);
      setLlmConfig({
        llm_provider: llmRes.llm_provider || 'openai',
        openai_api_key: '',
        openai_base_url: llmRes.openai_base_url || '',
        openai_model_name: llmRes.openai_model_name || '',
        gemini_api_key: '',
        gemini_model_name: llmRes.gemini_model_name || '',
        has_openai_api_key: llmRes.has_openai_api_key || false,
        has_gemini_api_key: llmRes.has_gemini_api_key || false,
      });
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.loadError') });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, [projectId]);

  const saveRepositories = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      await Promise.all(
        repositories
          .filter((item) => item.id && item.name && item.url)
          .map((item) =>
            api.saveRepositoryConfig(projectId, {
              ...item,
              branch: item.branch || 'main',
              type: item.type || 'git',
              token: item.token?.trim() ? item.token.trim() : undefined,
            }),
          ),
      );
      setMessage({ type: 'success', text: t('projectConfig.messages.saveRepositoriesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.saveRepositoriesError') });
    } finally {
      setSaving(false);
    }
  };

  const saveDatabases = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      await Promise.all(
        databases
          .filter((item) => item.id && item.name && item.host && item.database)
          .map((item) =>
            api.saveDatabaseConfig(projectId, {
              ...item,
              port: Number(item.port),
              schema_filter: item.schema_filter || [],
              password: item.password?.trim() ? item.password.trim() : undefined,
            }),
          ),
      );
      setMessage({ type: 'success', text: t('projectConfig.messages.saveDatabasesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.saveDatabasesError') });
    } finally {
      setSaving(false);
    }
  };

  const saveKnowledgeBases = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      await Promise.all(
        knowledgeBases
          .filter((item) => item.id && item.name)
          .map((item) =>
            api.saveKnowledgeBaseConfig(projectId, {
              ...item,
              includes: item.includes || [],
            }),
          ),
      );
      setMessage({ type: 'success', text: t('projectConfig.messages.saveKnowledgeBasesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.saveKnowledgeBasesError') });
    } finally {
      setSaving(false);
    }
  };

  const saveExperts = async () => {
    if (!projectId) return;
    setSaving(true);
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
      setMessage({ type: 'success', text: t('projectConfig.messages.saveExpertsSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.saveExpertsError') });
    } finally {
      setSaving(false);
    }
  };

  const saveLlmConfig = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      await api.saveProjectLlmConfig(projectId, {
        llm_provider: llmConfig.llm_provider,
        openai_api_key: llmConfig.openai_api_key || undefined,
        openai_base_url: llmConfig.openai_base_url,
        openai_model_name: llmConfig.openai_model_name,
        gemini_api_key: llmConfig.gemini_api_key || undefined,
        gemini_model_name: llmConfig.gemini_model_name,
      });
      setMessage({ type: 'success', text: llmCopy.saveSuccess });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: llmCopy.saveError });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRepository = async (repoId: string) => {
    if (!projectId || !repoId) return;
    try {
      await api.deleteRepositoryConfig(projectId, repoId);
      setMessage({ type: 'success', text: t('projectConfig.messages.deleteRepositoriesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.deleteRepositoriesError') });
    }
  };

  const handleDeleteDatabase = async (dbId: string) => {
    if (!projectId || !dbId) return;
    try {
      await api.deleteDatabaseConfig(projectId, dbId);
      setMessage({ type: 'success', text: t('projectConfig.messages.deleteDatabasesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.deleteDatabasesError') });
    }
  };

  const handleDeleteKnowledgeBase = async (kbId: string) => {
    if (!projectId || !kbId) return;
    try {
      await api.deleteKnowledgeBaseConfig(projectId, kbId);
      setMessage({ type: 'success', text: t('projectConfig.messages.deleteKnowledgeBasesSuccess') });
      await loadAll();
    } catch {
      setMessage({ type: 'error', text: t('projectConfig.messages.deleteKnowledgeBasesError') });
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <div className="max-w-[1400px] mx-auto p-6">
        <div className="flex flex-col gap-5 mb-8 lg:flex-row lg:items-center lg:justify-between">
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

        {message && (
          <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between ${message.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
            <span className="font-medium text-sm">{message.text}</span>
            <button onClick={() => setMessage(null)} className="text-xs font-bold uppercase opacity-50 hover:opacity-100">
              {t('common.dismiss')}
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-3">
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-2">
              <button
                onClick={() => setActiveTab('repositories')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider ${activeTab === 'repositories' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <FolderGit2 size={16} />
                {t('projectConfig.tabs.repositories')}
              </button>
              <button
                onClick={() => setActiveTab('databases')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider mt-1 ${activeTab === 'databases' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Database size={16} />
                {t('projectConfig.tabs.databases')}
              </button>
              <button
                onClick={() => setActiveTab('knowledge')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider mt-1 ${activeTab === 'knowledge' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <BookOpen size={16} />
                {t('projectConfig.tabs.knowledge')}
              </button>
              <button
                onClick={() => setActiveTab('experts')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider mt-1 ${activeTab === 'experts' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Bot size={16} />
                {expertCopy.tab}
              </button>
              <button
                onClick={() => setActiveTab('llm')}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider mt-1 ${activeTab === 'llm' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
              >
                <Cpu size={16} />
                {llmCopy.tab}
              </button>
            </div>
          </div>

          <div className="lg:col-span-9">
            {activeTab === 'repositories' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{t('projectConfig.repositories.eyebrow')}</div>
                    <h2 className="text-xl font-black text-gray-900">{t('projectConfig.repositories.title')}</h2>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => setRepositories((prev) => [...prev, createRepository()])} className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all">
                      <Plus size={14} />
                      {t('projectConfig.actions.addRepo')}
                    </button>
                    <button onClick={() => void saveRepositories()} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50">
                      <Save size={14} />
                      {t('common.save')}
                    </button>
                  </div>
                </div>

                <div className="space-y-5">
                  {repositories.map((repo, index) => (
                    <div key={`${repo.id || 'new'}-${index}`} className="rounded-2xl border border-gray-200 p-5 bg-gray-50/50 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-black uppercase tracking-widest text-gray-500">
                          {t('projectConfig.repositories.itemLabel', { index: index + 1 })}
                        </div>
                        <button onClick={() => repo.id ? void handleDeleteRepository(repo.id) : setRepositories((prev) => prev.filter((_, i) => i !== index))} className="inline-flex items-center gap-2 text-rose-600 text-xs font-black uppercase">
                          <Trash2 size={14} />
                          {t('projectConfig.actions.delete')}
                        </button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input value={repo.id} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, id: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.id')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={repo.name} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, name: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.name')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={repo.url} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, url: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.url')} className="w-full p-3 bg-white border border-gray-200 rounded-xl md:col-span-2" />
                        <input value={repo.branch || ''} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, branch: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.branch')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={repo.username || ''} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, username: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.username')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={repo.token || ''} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, token: e.target.value } : item))} placeholder={repo.has_token ? t('projectConfig.repositories.placeholders.tokenExisting') : t('projectConfig.repositories.placeholders.token')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={repo.local_path || ''} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, local_path: e.target.value } : item))} placeholder={t('projectConfig.repositories.placeholders.localPath')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <textarea value={repo.description || ''} onChange={(e) => setRepositories((prev) => prev.map((item, i) => i === index ? { ...item, description: e.target.value } : item))} placeholder={t('projectConfig.placeholders.description')} className="w-full p-3 bg-white border border-gray-200 rounded-xl md:col-span-2 min-h-24 resize-none" />
                      </div>
                    </div>
                  ))}
                  {repositories.length === 0 && <div className="rounded-2xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-400">{t('projectConfig.repositories.empty')}</div>}
                </div>
              </section>
            )}

            {activeTab === 'databases' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{t('projectConfig.databases.eyebrow')}</div>
                    <h2 className="text-xl font-black text-gray-900">{t('projectConfig.databases.title')}</h2>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => setDatabases((prev) => [...prev, createDatabase()])} className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all">
                      <Plus size={14} />
                      {t('projectConfig.actions.addDatabase')}
                    </button>
                    <button onClick={() => void saveDatabases()} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50">
                      <Save size={14} />
                      {t('common.save')}
                    </button>
                  </div>
                </div>

                <div className="space-y-5">
                  {databases.map((db, index) => (
                    <div key={`${db.id || 'new'}-${index}`} className="rounded-2xl border border-gray-200 p-5 bg-gray-50/50 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-black uppercase tracking-widest text-gray-500">
                          {t('projectConfig.databases.itemLabel', { index: index + 1 })}
                        </div>
                        <button onClick={() => db.id ? void handleDeleteDatabase(db.id) : setDatabases((prev) => prev.filter((_, i) => i !== index))} className="inline-flex items-center gap-2 text-rose-600 text-xs font-black uppercase">
                          <Trash2 size={14} />
                          {t('projectConfig.actions.delete')}
                        </button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input value={db.id} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, id: e.target.value } : item))} placeholder={t('projectConfig.databases.placeholders.id')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={db.name} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, name: e.target.value } : item))} placeholder={t('projectConfig.databases.placeholders.name')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <select value={db.type} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, type: e.target.value } : item))} className="w-full p-3 bg-white border border-gray-200 rounded-xl">
                          <option value="postgresql">PostgreSQL</option>
                          <option value="opengauss">openGauss</option>
                          <option value="dws">DWS</option>
                          <option value="mysql">MySQL</option>
                          <option value="oracle">Oracle</option>
                          <option value="sqlite">SQLite</option>
                        </select>
                        <input value={db.port} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, port: Number(e.target.value || 0) } : item))} placeholder={t('projectConfig.databases.placeholders.port')} type="number" className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={db.host} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, host: e.target.value } : item))} placeholder={t('projectConfig.databases.placeholders.host')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={db.database} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, database: e.target.value } : item))} placeholder={t('projectConfig.databases.placeholders.database')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={db.username || ''} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, username: e.target.value } : item))} placeholder={t('projectConfig.databases.placeholders.username')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={db.password || ''} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, password: e.target.value } : item))} placeholder={db.has_password ? t('projectConfig.databases.placeholders.passwordExisting') : t('projectConfig.databases.placeholders.password')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <textarea value={(db.schema_filter || []).join('\n')} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, schema_filter: splitMultiline(e.target.value) } : item))} placeholder={t('projectConfig.databases.placeholders.schemaFilter')} className="w-full p-3 bg-white border border-gray-200 rounded-xl min-h-24 resize-none" />
                        <textarea value={db.description || ''} onChange={(e) => setDatabases((prev) => prev.map((item, i) => i === index ? { ...item, description: e.target.value } : item))} placeholder={t('projectConfig.placeholders.description')} className="w-full p-3 bg-white border border-gray-200 rounded-xl min-h-24 resize-none" />
                      </div>
                    </div>
                  ))}
                  {databases.length === 0 && <div className="rounded-2xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-400">{t('projectConfig.databases.empty')}</div>}
                </div>
              </section>
            )}

            {activeTab === 'knowledge' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{t('projectConfig.knowledge.eyebrow')}</div>
                    <h2 className="text-xl font-black text-gray-900">{t('projectConfig.knowledge.title')}</h2>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => setKnowledgeBases((prev) => [...prev, createKnowledgeBase()])} className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all">
                      <Plus size={14} />
                      {t('projectConfig.actions.addKnowledgeBase')}
                    </button>
                    <button onClick={() => void saveKnowledgeBases()} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50">
                      <Save size={14} />
                      {t('common.save')}
                    </button>
                  </div>
                </div>

                <div className="space-y-5">
                  {knowledgeBases.map((kb, index) => (
                    <div key={`${kb.id || 'new'}-${index}`} className="rounded-2xl border border-gray-200 p-5 bg-gray-50/50 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-black uppercase tracking-widest text-gray-500">
                          {t('projectConfig.knowledge.itemLabel', { index: index + 1 })}
                        </div>
                        <button onClick={() => kb.id ? void handleDeleteKnowledgeBase(kb.id) : setKnowledgeBases((prev) => prev.filter((_, i) => i !== index))} className="inline-flex items-center gap-2 text-rose-600 text-xs font-black uppercase">
                          <Trash2 size={14} />
                          {t('projectConfig.actions.delete')}
                        </button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input value={kb.id} onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? { ...item, id: e.target.value } : item))} placeholder={t('projectConfig.knowledge.placeholders.id')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <input value={kb.name} onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? { ...item, name: e.target.value } : item))} placeholder={t('projectConfig.knowledge.placeholders.name')} className="w-full p-3 bg-white border border-gray-200 rounded-xl" />
                        <select value={kb.type} onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? { ...item, type: e.target.value } : item))} className="w-full p-3 bg-white border border-gray-200 rounded-xl">
                          <option value="local">{t('projectConfig.knowledge.types.local')}</option>
                          <option value="remote">{t('projectConfig.knowledge.types.remote')}</option>
                        </select>
                        <input
                          value={kb.type === 'local' ? (kb.path || '') : (kb.index_url || '')}
                          onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? (item.type === 'local' ? { ...item, path: e.target.value } : { ...item, index_url: e.target.value }) : item))}
                          placeholder={kb.type === 'local' ? t('projectConfig.knowledge.placeholders.path') : t('projectConfig.knowledge.placeholders.indexUrl')}
                          className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                        />
                        <textarea value={(kb.includes || []).join('\n')} onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? { ...item, includes: splitMultiline(e.target.value) } : item))} placeholder={t('projectConfig.knowledge.placeholders.includes')} className="w-full p-3 bg-white border border-gray-200 rounded-xl min-h-24 resize-none" />
                        <textarea value={kb.description || ''} onChange={(e) => setKnowledgeBases((prev) => prev.map((item, i) => i === index ? { ...item, description: e.target.value } : item))} placeholder={t('projectConfig.placeholders.description')} className="w-full p-3 bg-white border border-gray-200 rounded-xl min-h-24 resize-none" />
                      </div>
                    </div>
                  ))}
                  {knowledgeBases.length === 0 && <div className="rounded-2xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-400">{t('projectConfig.knowledge.empty')}</div>}
                </div>
              </section>
            )}

            {activeTab === 'experts' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{expertCopy.eyebrow}</div>
                    <h2 className="text-xl font-black text-gray-900">{expertCopy.title}</h2>
                  </div>
                  <button onClick={() => void saveExperts()} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50">
                    <Save size={14} />
                    {t('common.save')}
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {experts.map((expert, index) => (
                    <div key={expert.id} className="rounded-xl border border-gray-200 bg-white hover:border-indigo-200 hover:shadow-sm transition-all p-3">
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
                  {experts.length === 0 && <div className="col-span-full rounded-2xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-400">{expertCopy.empty}</div>}
                </div>
              </section>
            )}

            {activeTab === 'llm' && (
              <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{llmCopy.eyebrow}</div>
                    <h2 className="text-xl font-black text-gray-900">{llmCopy.title}</h2>
                    <p className="text-sm text-gray-500 mt-2">{llmCopy.description}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => void loadAll()}
                      disabled={loading}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-xl text-xs font-black uppercase text-gray-700 hover:bg-gray-200 transition-all"
                    >
                      <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                      {llmCopy.refresh}
                    </button>
                    <button onClick={() => void saveLlmConfig()} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50">
                      <Save size={14} />
                      {t('common.save')}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{llmCopy.provider}</div>
                    <select
                      value={llmConfig.llm_provider}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, llm_provider: e.target.value }))}
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    >
                      <option value="openai">OpenAI Compatible</option>
                      <option value="gemini">Gemini</option>
                    </select>
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{llmCopy.openaiBaseUrl}</div>
                    <input
                      value={llmConfig.openai_base_url}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, openai_base_url: e.target.value }))}
                      placeholder="https://api.openai.com/v1"
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{llmCopy.openaiModel}</div>
                    <input
                      value={llmConfig.openai_model_name}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, openai_model_name: e.target.value }))}
                      placeholder="gpt-4o"
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">{llmCopy.geminiModel}</div>
                    <input
                      value={llmConfig.gemini_model_name}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, gemini_model_name: e.target.value }))}
                      placeholder="gemini-2.5-flash"
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">
                      {llmCopy.openaiKey} {llmConfig.has_openai_api_key ? `(${llmCopy.saved})` : ''}
                    </div>
                    <input
                      type="password"
                      value={llmConfig.openai_api_key}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, openai_api_key: e.target.value }))}
                      placeholder={llmConfig.has_openai_api_key ? llmCopy.keepCurrent : llmCopy.enterKey}
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    />
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">
                      {llmCopy.geminiKey} {llmConfig.has_gemini_api_key ? `(${llmCopy.saved})` : ''}
                    </div>
                    <input
                      type="password"
                      value={llmConfig.gemini_api_key}
                      onChange={(e) => setLlmConfig((prev) => ({ ...prev, gemini_api_key: e.target.value }))}
                      placeholder={llmConfig.has_gemini_api_key ? llmCopy.keepCurrent : llmCopy.enterKey}
                      className="w-full p-3 bg-white border border-gray-200 rounded-xl"
                    />
                  </div>
                </div>
              </section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
