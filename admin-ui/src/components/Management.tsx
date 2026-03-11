import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Cpu, Zap, FileCode, History, Save, ChevronRight, ShieldCheck, Box, Settings, Loader as LucideLoader } from 'lucide-react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1/management';

interface AgentVersion {
  version_id: string;
  timestamp: string;
  content: string;
}

interface Agent {
  id: string;
  name: string;
  description: string;
  config_path: string;
  current_config: string;
  versions: AgentVersion[];
  skills: string[];
}

interface Skill {
  id: string;
  name: string;
  description: string;
  path: string;
  templates: string[];
}

interface TemplateVersion {
  version_id: string;
  timestamp: string;
  content: string;
}

interface Template {
  id: string;
  name: string;
  skill_id: string;
  current_content: string;
  versions: TemplateVersion[];
}

export function Management() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'agents' | 'skills' | 'templates'>('agents');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  
  const [editingContent, setEditingContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [agentsRes, skillsRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/agents`),
        axios.get(`${API_BASE_URL}/skills`)
      ]);
      setAgents(agentsRes.data);
      setSkills(skillsRes.data);
    } catch (err) {
      setMessage({ type: 'error', text: t('management.loadError') });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAgent = async (agentId: string) => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/agents/${agentId}`);
      setSelectedAgent(res.data);
      setSelectedTemplate(null);
      setEditingContent(res.data.current_config);
      setActiveTab('agents');
    } catch (err) {
      setMessage({ type: 'error', text: t('common.loadError') });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTemplate = async (skillId: string, templateName: string) => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/skills/${skillId}/templates/${templateName}`);
      setSelectedTemplate(res.data);
      setSelectedAgent(null);
      setEditingContent(res.data.current_content);
      setActiveTab('templates');
    } catch (err) {
      setMessage({ type: 'error', text: t('common.loadError') });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      if (selectedAgent) {
        await axios.post(`${API_BASE_URL}/agents/${selectedAgent.id}`, {
          config_yaml: editingContent
        });
        setMessage({ type: 'success', text: t('management.templateUpdateSuccess') });
        handleSelectAgent(selectedAgent.id);
      } else if (selectedTemplate) {
        await axios.post(`${API_BASE_URL}/skills/${selectedTemplate.skill_id}/templates/${selectedTemplate.name}`, {
          content: editingContent
        });
        setMessage({ type: 'success', text: t('management.templateUpdateSuccess') });
        handleSelectTemplate(selectedTemplate.skill_id, selectedTemplate.name);
      }
    } catch (err) {
      setMessage({ type: 'error', text: t('common.error') });
    } finally {
      setLoading(false);
    }
  };

  const restoreVersion = (content: string) => {
    setEditingContent(content);
    setMessage({ type: 'success', text: t('management.versionRestored') });
  };

  return (
    <div className="max-w-[1400px] mx-auto p-6 bg-gray-50/30 min-h-screen">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link to="/" className="p-2 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-400 hover:text-indigo-600 transition-all">
            <ArrowLeft size={20} />
          </Link>
          <div>
            <div className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-0.5">{t('management.admin')}</div>
            <h1 className="text-xl font-black text-gray-900 uppercase">{t('management.title')}</h1>
          </div>
        </div>
        <LanguageSwitcher />
      </div>

      {message && (
        <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between animate-in slide-in-from-top-2 ${message.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
          <span className="font-medium text-sm">{message.text}</span>
          <button onClick={() => setMessage(null)} className="text-xs font-bold uppercase opacity-50 hover:opacity-100">{t('common.dismiss')}</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Navigation Sidebar */}
        <div className="lg:col-span-3 flex flex-col gap-4">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-2">
            <button 
              onClick={() => { setActiveTab('agents'); setSelectedAgent(null); setSelectedTemplate(null); }}
              className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider ${activeTab === 'agents' && !selectedAgent ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
            >
              <Cpu size={16} /> {t('management.subAgents')}
            </button>
            <button 
              onClick={() => { setActiveTab('skills'); setSelectedAgent(null); setSelectedTemplate(null); }}
              className={`w-full flex items-center gap-3 p-3 rounded-xl transition-all text-xs font-bold uppercase tracking-wider mt-1 ${activeTab === 'skills' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'text-gray-500 hover:bg-gray-50'}`}
            >
              <Zap size={16} /> {t('management.skills')}
            </button>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden p-4">
            <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4 px-1">{t('management.quickSelect')}</h2>
            
            {/* Sub-Agent Config List */}
            <div className="mb-6">
               <div className="flex items-center gap-2 px-1 mb-2 text-[11px] font-bold text-gray-400 uppercase tracking-tighter">
                  <Settings size={12} /> {t('common.configuration')}
               </div>
               <div className="space-y-1 ml-4">
                  {agents.map(agent => (
                    <button 
                      key={agent.id}
                      onClick={() => handleSelectAgent(agent.id)}
                      className={`w-full text-left p-2 rounded-lg text-[10px] font-medium transition-all ${selectedAgent?.id === agent.id ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-500 hover:bg-gray-50'}`}
                    >
                      {agent.id}.agent.yaml
                    </button>
                  ))}
               </div>
            </div>

            {/* Skills & Templates List */}
            <div className="space-y-4">
              {skills.map(skill => (
                <div key={skill.id}>
                  <div className="flex items-center gap-2 px-1 mb-2 text-[11px] font-bold text-gray-700">
                    <Box size={12} className="text-indigo-400" /> {skill.name}
                  </div>
                  <div className="space-y-1 ml-4">
                    {skill.templates.map(tpl => (
                      <button 
                        key={tpl}
                        onClick={() => handleSelectTemplate(skill.id, tpl)}
                        className={`w-full text-left p-2 rounded-lg text-[10px] font-medium transition-all ${selectedTemplate?.name === tpl ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-500 hover:bg-gray-50'}`}
                      >
                        {tpl}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="lg:col-span-9">
          {activeTab === 'agents' && !selectedAgent && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in slide-in-from-bottom-2">
              {agents.map(agent => (
                <div key={agent.id} className="bg-white p-6 rounded-2xl border border-gray-200 shadow-sm hover:shadow-md transition-all group cursor-pointer" onClick={() => handleSelectAgent(agent.id)}>
                  <div className="flex items-center justify-between mb-4">
                    <div className="p-3 bg-indigo-50 rounded-xl text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-all">
                      <Cpu size={20} />
                    </div>
                    <span className="text-[10px] font-mono text-gray-400 uppercase">{t('common.id')}: {agent.id}</span>
                  </div>
                  <h3 className="text-sm font-black text-gray-900 uppercase mb-2">{agent.name}</h3>
                  <p className="text-xs text-gray-500 leading-relaxed mb-4">{agent.description || t('common.noDescription')}</p>
                  <div className="pt-4 border-t border-gray-50 flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-gray-400 uppercase">{t('management.configurationPath')}</span>
                        <span className="text-[10px] font-mono text-indigo-500">{agent.config_path}</span>
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                        {agent.skills?.map(s => (
                            <span key={s} className="px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded text-[9px] font-bold uppercase">{s}</span>
                        ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'skills' && (
            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2">
              {skills.map(skill => (
                <div key={skill.id} className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden group">
                  <div className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-4">
                        <div className="p-3 bg-amber-50 rounded-xl text-amber-600">
                          <Zap size={20} />
                        </div>
                        <div>
                          <h3 className="text-sm font-black text-gray-900 uppercase">{skill.name}</h3>
                          <span className="text-[10px] font-mono text-gray-400">{skill.path}</span>
                        </div>
                      </div>
                      <ShieldCheck size={20} className="text-emerald-500" />
                    </div>
                    <p className="text-xs text-gray-500 leading-relaxed mb-6">{skill.description || t('projectDetail.readyIdle')}</p>
                    
                    <div className="flex flex-wrap gap-2">
                      {skill.templates.map(tpl => (
                        <button 
                          key={tpl}
                          onClick={() => handleSelectTemplate(skill.id, tpl)}
                          className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border border-gray-100 rounded-lg text-[10px] font-bold text-gray-600 hover:border-indigo-200 hover:text-indigo-600 transition-all"
                        >
                          <FileCode size={12} /> {tpl}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {(selectedAgent || selectedTemplate) && (
            <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-2">
              <div className="bg-white rounded-2xl border border-gray-200 shadow-xl overflow-hidden flex flex-col min-h-[600px]">
                <div className="bg-gray-50 px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {selectedAgent ? <Cpu size={18} className="text-indigo-600" /> : <FileCode size={18} className="text-indigo-600" />}
                    <div>
                      <h3 className="text-xs font-black text-gray-900 uppercase">
                        {selectedAgent ? `${selectedAgent.id}.agent.yaml` : selectedTemplate?.name}
                      </h3>
                      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                        {selectedAgent ? t('common.configuration') : `${t('management.skills')}: ${selectedTemplate?.skill_id}`}
                      </span>
                    </div>
                  </div>
                  <button 
                    onClick={handleSave}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-700 shadow-lg shadow-indigo-100 transition-all disabled:opacity-50"
                  >
                    <Save size={14} /> {t('management.saveChanges')}
                  </button>
                </div>
                <div className="flex-1 flex flex-col md:flex-row">
                  {/* Editor */}
                  <div className="flex-1 p-0 flex flex-col">
                    <textarea 
                      className="flex-1 w-full p-6 font-mono text-sm text-gray-800 focus:outline-none resize-none bg-white"
                      value={editingContent}
                      onChange={(e) => setEditingContent(e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                  {/* Version History Panel */}
                  <div className="md:w-72 bg-gray-50 border-l border-gray-100 flex flex-col">
                    <div className="p-4 border-b border-gray-100 bg-white/50">
                      <div className="flex items-center gap-2 text-[10px] font-black text-gray-400 uppercase tracking-widest">
                        <History size={14} /> {t('management.versionHistory')}
                      </div>
                    </div>
                    <div className="flex-1 overflow-y-auto p-3 space-y-2">
                      {((selectedAgent?.versions?.length || 0) + (selectedTemplate?.versions?.length || 0)) === 0 ? (
                        <div className="p-8 text-center opacity-30 flex flex-col items-center gap-2">
                          <History size={24} />
                          <span className="text-[10px] font-bold uppercase">{t('management.noHistory')}</span>
                        </div>
                      ) : (
                        (selectedAgent ? selectedAgent.versions : selectedTemplate?.versions || []).map(v => (
                          <div key={v.version_id} className="bg-white p-3 rounded-xl border border-gray-100 shadow-sm group">
                            <div className="flex items-center justify-between mb-2">
                              <span className="px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[9px] font-black uppercase">v{v.version_id}</span>
                              <span className="text-[9px] font-bold text-gray-400">{v.timestamp}</span>
                            </div>
                            <button 
                              onClick={() => restoreVersion(v.content)}
                              className="w-full text-center py-1.5 border border-gray-100 rounded-lg text-[9px] font-black uppercase text-gray-500 hover:bg-indigo-600 hover:text-white hover:border-indigo-600 transition-all"
                            >
                              {t('management.inspectRestoreBtn')}
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
