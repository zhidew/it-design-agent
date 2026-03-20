import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Save, Settings2 } from 'lucide-react';
import { api } from '../api';
import { LanguageSwitcher } from './LanguageSwitcher';

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

const EMPTY_CONFIG: LlmConfigState = {
  llm_provider: 'openai',
  openai_api_key: '',
  openai_base_url: '',
  openai_model_name: '',
  gemini_api_key: '',
  gemini_model_name: '',
};

export function LlmConfig() {
  const [config, setConfig] = useState<LlmConfigState>(EMPTY_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadConfig = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const data = await api.getLlmConfig();
      setConfig({
        llm_provider: data.llm_provider || 'openai',
        openai_api_key: '',
        openai_base_url: data.openai_base_url || '',
        openai_model_name: data.openai_model_name || '',
        gemini_api_key: '',
        gemini_model_name: data.gemini_model_name || '',
        has_openai_api_key: data.has_openai_api_key || false,
        has_gemini_api_key: data.has_gemini_api_key || false,
      });
    } catch {
      setMessage('Failed to load LLM config.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConfig();
  }, []);

  const saveConfig = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.saveLlmConfig({
        llm_provider: config.llm_provider,
        openai_api_key: config.openai_api_key || undefined,
        openai_base_url: config.openai_base_url,
        openai_model_name: config.openai_model_name,
        gemini_api_key: config.gemini_api_key || undefined,
        gemini_model_name: config.gemini_model_name,
      });
      setMessage('LLM config saved.');
      await loadConfig();
    } catch {
      setMessage('Failed to save LLM config.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <div className="max-w-[1100px] mx-auto p-6">
        <div className="flex flex-col gap-5 mb-8 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <Link to="/" className="p-2 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-400 hover:text-indigo-600 transition-all">
              <ArrowLeft size={20} />
            </Link>
            <div>
              <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest mb-0.5">System Config</div>
              <h1 className="text-2xl font-black text-gray-900 uppercase flex items-center gap-3">
                <Settings2 size={24} className="text-indigo-600" />
                LLM Model Config
              </h1>
              <p className="text-sm text-gray-500 mt-1">Manage provider, base URL, model names, and API keys used by the orchestrator.</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void loadConfig()}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase text-gray-600 hover:text-indigo-600 hover:border-indigo-200 transition-all shadow-sm"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <LanguageSwitcher />
          </div>
        </div>

        {message && (
          <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700 shadow-sm">
            {message}
          </div>
        )}

        <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Provider</div>
              <select
                value={config.llm_provider}
                onChange={(e) => setConfig((prev) => ({ ...prev, llm_provider: e.target.value }))}
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              >
                <option value="openai">OpenAI Compatible</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">OpenAI Base URL</div>
              <input
                value={config.openai_base_url}
                onChange={(e) => setConfig((prev) => ({ ...prev, openai_base_url: e.target.value }))}
                placeholder="https://api.openai.com/v1"
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              />
            </div>
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">OpenAI Model</div>
              <input
                value={config.openai_model_name}
                onChange={(e) => setConfig((prev) => ({ ...prev, openai_model_name: e.target.value }))}
                placeholder="gpt-4o"
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              />
            </div>
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Gemini Model</div>
              <input
                value={config.gemini_model_name}
                onChange={(e) => setConfig((prev) => ({ ...prev, gemini_model_name: e.target.value }))}
                placeholder="gemini-2.5-flash"
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              />
            </div>
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">
                OpenAI API Key {config.has_openai_api_key ? '(saved)' : ''}
              </div>
              <input
                type="password"
                value={config.openai_api_key}
                onChange={(e) => setConfig((prev) => ({ ...prev, openai_api_key: e.target.value }))}
                placeholder={config.has_openai_api_key ? 'Leave blank to keep current key' : 'Enter API key'}
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              />
            </div>
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">
                Gemini API Key {config.has_gemini_api_key ? '(saved)' : ''}
              </div>
              <input
                type="password"
                value={config.gemini_api_key}
                onChange={(e) => setConfig((prev) => ({ ...prev, gemini_api_key: e.target.value }))}
                placeholder={config.has_gemini_api_key ? 'Leave blank to keep current key' : 'Enter Gemini key'}
                className="w-full p-3 bg-white border border-gray-200 rounded-xl"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void saveConfig()}
              disabled={saving}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase hover:bg-indigo-700 transition-all disabled:opacity-50"
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save Config'}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
