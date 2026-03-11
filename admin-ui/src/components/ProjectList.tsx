import React, { useEffect, useState } from 'react';
import { api } from '../api';
import { Link } from 'react-router-dom';
import { Folder, Plus, RefreshCw, Settings, LayoutDashboard, Loader as LucideLoader } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';

interface Project {
  id: string;
  name: string;
}

export function ProjectList() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [newProjectName, setNewProjectName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getProjects();
      setProjects(data);
    } catch {
      setError(t('common.loadError') || 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    setIsCreating(true);
    setError(null);
    try {
      await api.createProject(newProjectName.trim());
      setNewProjectName('');
      await loadProjects();
    } catch {
      setError(t('common.error') || 'Failed to create project');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="max-w-[1400px] mx-auto p-6 bg-gray-50/30 min-h-screen">
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-200 text-white">
            <LayoutDashboard size={24} />
          </div>
          <div>
            <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest mb-0.5">{t('projectList.subtitle')}</div>
            <h1 className="text-2xl font-black text-gray-900 uppercase">{t('projectList.title')}</h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/management"
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase text-gray-600 hover:text-indigo-600 hover:border-indigo-200 transition-all shadow-sm"
          >
            <Settings size={16} />
            {t('common.systemRegistry')}
          </Link>
          <button
            type="button"
            onClick={loadProjects}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl font-bold text-xs uppercase text-gray-600 hover:text-indigo-600 hover:border-indigo-200 transition-all shadow-sm"
          >
            <RefreshCw size={16} className={isLoading ? 'animate-spin' : ''} />
            {t('common.refresh')}
          </button>
          <div className="h-8 w-px bg-gray-200 mx-2" />
          <LanguageSwitcher />
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 flex items-center justify-between shadow-sm">
          <span>{error}</span>
          <button onClick={loadProjects} className="text-xs font-bold uppercase">{t('common.retry')}</button>
        </div>
      )}

      <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-200 mb-8 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-5">
          <Plus size={64} className="text-indigo-600" />
        </div>
        <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">{t('projectList.createTitle')}</h2>
        <form onSubmit={handleCreate} className="flex flex-col sm:flex-row gap-4 relative z-10">
          <div className="flex-1">
            <input
              id="project-name"
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder={t('projectList.projectNamePlaceholder')}
              className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={isCreating || !newProjectName.trim()}
            className="bg-indigo-600 text-white px-6 py-3 rounded-xl font-bold text-xs uppercase hover:bg-indigo-700 disabled:opacity-50 shadow-lg shadow-indigo-100 transition-all flex items-center justify-center gap-2"
          >
            {isCreating ? <RefreshCw size={18} className="animate-spin" /> : <Plus size={18} />}
            {isCreating ? t('projectList.creating') : t('projectList.createBtn')}
          </button>
        </form>
      </div>

      {isLoading ? (
        <div className="rounded-2xl border border-gray-200 bg-white p-20 text-center flex flex-col items-center gap-4">
           <RefreshCw size={32} className="text-indigo-500 animate-spin" />
           <span className="text-sm font-bold text-gray-400 uppercase tracking-widest">{t('common.loadingProjects')}</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((proj) => (
            <Link
              key={proj.id}
              to={`/projects/${proj.id}`}
              className="group bg-white p-6 rounded-2xl shadow-sm border border-gray-200 hover:border-indigo-500 hover:shadow-xl hover:shadow-indigo-50 transition-all relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-10 transition-opacity">
                <Folder size={48} className="text-indigo-600" />
              </div>
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 bg-gray-50 rounded-xl text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-all">
                  <Folder size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-black text-gray-900 uppercase truncate max-w-[200px]">{proj.name}</h3>
                  <span className="text-[10px] font-mono text-gray-400 uppercase">{t('common.id')}: {proj.id}</span>
                </div>
              </div>
              <div className="pt-4 border-t border-gray-50 flex items-center justify-between">
                 <span className="text-[10px] font-bold text-gray-400 uppercase">{t('projectList.workspaceActive')}</span>
                 <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-500 uppercase">
                    <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> {t('projectList.ready')}
                 </div>
              </div>
            </Link>
          ))}
          {projects.length === 0 && (
            <div className="col-span-full text-center py-20 bg-white rounded-2xl border border-gray-200 border-dashed">
              <div className="max-w-xs mx-auto flex flex-col items-center gap-4">
                <Folder size={48} className="text-gray-200" />
                <p className="text-sm font-bold text-gray-400 uppercase tracking-widest leading-relaxed">{t('projectList.noProjects')}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
