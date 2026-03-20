import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Bot,
  Braces,
  Code2,
  FileCode,
  Loader as LucideLoader,
  Plus,
  Save,
  ScrollText,
  Trash2,
  Search,
  X,
} from 'lucide-react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1') + '/expert-center';

type WorkbenchTab = 'profile' | 'skill' | 'templates' | 'references' | 'scripts' | 'tools';

interface Expert {
  id: string;
  name: string;
  description: string;
  expertise: string[];
  profile_path: string;
  skill_path?: string | null;
}

interface FileVersion {
  version_id: string;
  timestamp: string;
  content: string;
}

interface FileNode {
  id: string;
  name: string;
  path: string;
  node_type: 'expert' | 'folder' | 'file';
  expert_id?: string | null;
  children?: FileNode[];
}

interface FileContent {
  path: string;
  name: string;
  content: string;
  versions: FileVersion[];
}

interface ToolInfo {
  name: string;
  category: string;
  description_zh: string;
  description_en: string;
  input_schema: Record<string, any>;
  output_schema: Record<string, any>;
  use_cases: string[];
  recommended_for: string[];
  script_path?: string;
}

interface WorkbenchSection {
  tab: WorkbenchTab;
  title: string;
  description: string;
  paths: string[];
}

const TAB_ORDER: WorkbenchTab[] = ['profile', 'skill', 'templates', 'references', 'scripts', 'tools'];

export function ExpertCenter() {
  const { t, i18n } = useTranslation();
  const [experts, setExperts] = useState<Expert[]>([]);
  const [tree, setTree] = useState<FileNode[]>([]);
  const [selectedExpertId, setSelectedExpertId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('profile');
  const [selectedPath, setSelectedPath] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<FileContent | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  
  // Search and Modal states
  const [searchTerm, setSearchTerm] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newExpertName, setNewExpertName] = useState('');
  const [newExpertDescription, setNewExpertDescription] = useState('');
  const [generationStep, setGenerationStep] = useState(0);
  
  // File management states
  const [showNewFileModal, setShowNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState('');
  const [creatingFile, setCreatingFile] = useState(false);
  const [deletingFile, setDeletingFile] = useState(false);
  
  // Tools management states
  const [toolsList, setToolsList] = useState<ToolInfo[]>([]);
  const [selectedTool, setSelectedTool] = useState<ToolInfo | null>(null);
  const [toolCode, setToolCode] = useState<string>('');
  const [loadingTools, setLoadingTools] = useState(false);

  const GENERATION_STEPS = [
    t('management.generationSteps.0'),
    t('management.generationSteps.1'),
    t('management.generationSteps.2'),
    t('management.generationSteps.3'),
    t('management.generationSteps.4'),
  ];

  useEffect(() => {
    let interval: any;
    if (creating) {
      setGenerationStep(0);
      interval = setInterval(() => {
        setGenerationStep((prev) => (prev < GENERATION_STEPS.length - 1 ? prev + 1 : prev));
      }, 3500); 
    } else {
      setGenerationStep(0);
      if (interval) clearInterval(interval);
    }
    return () => { if (interval) clearInterval(interval); };
  }, [creating, GENERATION_STEPS.length]);

  useEffect(() => {
    void loadExpertCenter();
  }, []);

  const loadExpertCenter = async () => {
    setLoading(true);
    try {
      const [expertsRes, treeRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/experts`),
        axios.get(`${API_BASE_URL}/file-tree`),
      ]);

      const nextExperts = expertsRes.data as Expert[];
      setExperts(nextExperts);
      setTree(treeRes.data as FileNode[]);

      if (!selectedExpertId && nextExperts.length > 0) {
        setSelectedExpertId(nextExperts[0].id);
        setActiveTab('profile');
      }
    } catch {
      setMessage({ type: 'error', text: t('management.loadError') });
    } finally {
      setLoading(false);
    }
  };
  
  const loadToolsList = async () => {
    setLoadingTools(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/tools`);
      setToolsList(response.data as ToolInfo[]);
    } catch {
      setMessage({ type: 'error', text: 'Failed to load tools list' });
    } finally {
      setLoadingTools(false);
    }
  };
  
  const loadToolCode = async (toolName: string) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/tools/${toolName}/code`);
      setToolCode(response.data.code || '');
    } catch {
      setMessage({ type: 'error', text: `Failed to load ${toolName} code` });
    }
  };

  const filteredExperts = useMemo(() => {
    if (!searchTerm.trim()) {
      return experts;
    }
    const term = searchTerm.toLowerCase();
    return experts.filter((expert) => {
      // Search in both i18n translations and raw data
      const expertI18n = t(`experts.${expert.id}`, { returnObjects: true }) as { name?: string; description?: string } | undefined;
      const searchable = [
        expert.id,
        expert.name,
        expert.description,
        expertI18n?.name || '',
        expertI18n?.description || '',
        ...(expert.expertise ?? []),
      ].join(' ').toLowerCase();
      return searchable.includes(term);
    });
  }, [experts, searchTerm, t]);

  const translateExpertName = (expert: Expert | null) => {
    if (!expert) {
      return t('management.selectExpert');
    }
    // Prefer i18n translation, fallback to API data
    return t(`experts.${expert.id}.name`, expert.name);
  };

  const translateExpertDescription = (expert: Expert | null) => {
    if (!expert) {
      return t('management.selectExpertHint');
    }
    // Prefer i18n translation, fallback to API data
    return t(`experts.${expert.id}.description`, expert.description);
  };

  const displayRelativePath = (path: string) => {
    if (path.startsWith('skills/')) {
      return path.slice('skills/'.length);
    }
    if (path.startsWith('experts/')) {
      return path.slice('experts/'.length);
    }
    return path;
  };

  const normalizeProfileContent = (path: string, content: string) => {
    // Return content as-is since expert.yaml already contains proper localized values
    return content;
  };

  const selectedExpert = useMemo(
    () => experts.find((expert) => expert.id === selectedExpertId) ?? null,
    [experts, selectedExpertId],
  );

  const fileNamesByPath = useMemo(() => {
    const entries: Record<string, string> = {};
    const visit = (node: FileNode) => {
      if (node.node_type === 'file') {
        entries[node.path] = node.name;
      }
      node.children?.forEach(visit);
    };
    tree.forEach(visit);
    return entries;
  }, [tree]);

  const workbenchSections = useMemo<Record<string, WorkbenchSection[]>>(() => {
    const sectionsByExpert: Record<string, WorkbenchSection[]> = {};

    const collectFilePaths = (node?: FileNode): string[] => {
      if (!node) {
        return [];
      }
      if (node.node_type === 'file') {
        return [node.path];
      }
      return (node.children ?? []).flatMap((child) => collectFilePaths(child));
    };

    const uniquePaths = (paths: string[]) => Array.from(new Set(paths));

    tree.forEach((expertNode) => {
      if (expertNode.node_type !== 'expert' || !expertNode.expert_id) {
        return;
      }

      const profileNode = (expertNode.children ?? []).find((child) => child.name === 'Expert Profile');
      const skillRoot = (expertNode.children ?? []).find((child) => child.name === 'Skill Files');
      const skillFiles = uniquePaths(collectFilePaths(skillRoot));

      const baseSections: WorkbenchSection[] = [
        {
          tab: 'profile',
          title: t('management.profileTab'),
          description: t('management.profileTabHint'),
          paths: profileNode ? [profileNode.path] : [],
        },
        {
          tab: 'skill',
          title: t('management.skillTab'),
          description: t('management.skillTabHint'),
          paths: uniquePaths(skillFiles.filter((path) => path.endsWith('/SKILL.md'))),
        },
        {
          tab: 'templates',
          title: t('management.templatesTab'),
          description: t('management.templatesTabHint'),
          paths: uniquePaths(skillFiles.filter((path) => path.includes('/assets/templates/'))),
        },
        {
          tab: 'references',
          title: t('management.referencesTab'),
          description: t('management.referencesTabHint'),
          paths: uniquePaths(skillFiles.filter((path) => path.includes('/references/'))),
        },
        {
          tab: 'scripts',
          title: t('management.scriptsTab'),
          description: t('management.scriptsTabHint'),
          paths: uniquePaths(skillFiles.filter((path) => path.includes('/scripts/'))),
        },
      ];
      
      // Add tools tab for expert-creator
      if (expertNode.expert_id === 'expert-creator') {
        baseSections.push({
          tab: 'tools',
          title: t('management.toolsTab') || 'Tools',
          description: t('management.toolsTabHint') || 'View system built-in tools and their implementations',
          paths: [],
        });
      }

      sectionsByExpert[expertNode.expert_id] = baseSections;
    });

    return sectionsByExpert;
  }, [tree, t]);

  const activeSections = selectedExpertId ? workbenchSections[selectedExpertId] ?? [] : [];
  const activeSection = activeSections.find((section) => section.tab === activeTab) ?? null;

  useEffect(() => {
    if (!selectedExpertId) {
      return;
    }
    setActiveTab('profile');
    setSelectedPath('');
    setSelectedFile(null);
    setEditingContent('');
  }, [selectedExpertId]);

  useEffect(() => {
    if (!selectedExpertId) {
      return;
    }
    if (!activeSection || activeSection.paths.length === 0) {
      setSelectedPath('');
      setSelectedFile(null);
      setEditingContent('');
      return;
    }
    if (activeSection.paths.includes(selectedPath)) {
      return;
    }
    void selectFile(activeSection.paths[0]);
  }, [selectedExpertId, activeTab, activeSection?.paths.join('|')]);

  const selectFile = async (path: string) => {
    setSelectedPath(path);
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/files/${path}/content`);
      setSelectedFile(response.data);
      setEditingContent(normalizeProfileContent(path, response.data.content));
    } catch {
      setMessage({ type: 'error', text: t('common.loadError') });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedFile) {
      return;
    }
    setSaving(true);
    try {
      await axios.put(`${API_BASE_URL}/files/${selectedFile.path}/content`, {
        content: editingContent,
      });
      setMessage({ type: 'success', text: t('management.saveSuccess') });
      await selectFile(selectedFile.path);
      await loadExpertCenter();
    } catch {
      setMessage({ type: 'error', text: t('common.error') });
    } finally {
      setSaving(false);
    }
  };

  const handleCreateExpert = async () => {
    if (!newExpertName.trim()) {
      return;
    }
    
    // Auto-generate expert_id from name (slugify) - FORCE ENGLISH ID
    const expert_id = newExpertName.trim()
      .toLowerCase()
      .replace(/[^\w\s-]/g, '') // Remove non-alphanumeric except whitespace and hyphens
      .trim()
      .replace(/\s+/g, '-') // Replace spaces with hyphens
      .replace(/-+/g, '-');
      
    setCreating(true);
    try {
      const response = await axios.post(`${API_BASE_URL}/experts`, {
        expert_id: expert_id || 'new-expert', // Fallback if name was all Chinese
        name: newExpertName.trim(),
        description: newExpertDescription.trim(),
      });
      setMessage({ type: 'success', text: t('management.createExpertSuccess') });
      setNewExpertName('');
      setNewExpertDescription('');
      setShowCreateModal(false);
      await loadExpertCenter();
      setSelectedExpertId(response.data.id);
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || t('management.createExpertError');
      setMessage({ type: 'error', text: errMsg });
      // Keep modal open so user can see what happened, but reset creating state
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteExpert = async () => {
    if (!selectedExpert) {
      return;
    }
    const confirmed = window.confirm(
      t('management.deleteExpertConfirm', { name: translateExpertName(selectedExpert) }),
    );
    if (!confirmed) {
      return;
    }
    setDeleting(true);
    try {
      await axios.delete(`${API_BASE_URL}/experts/${selectedExpert.id}`);
      setMessage({ type: 'success', text: t('management.deleteExpertSuccess') });
      setSelectedExpertId('');
      setSelectedPath('');
      setSelectedFile(null);
      setEditingContent('');
      await loadExpertCenter();
    } catch {
      setMessage({ type: 'error', text: t('management.deleteExpertError') });
    } finally {
      setDeleting(false);
    }
  };

  const handleCreateFile = async () => {
    if (!newFileName.trim() || !selectedExpertId || !activeTab) {
      return;
    }
    
    // Determine the base path for the current tab
    const section = activeSections.find((s) => s.tab === activeTab);
    if (!section || section.paths.length === 0) {
      setMessage({ type: 'error', text: 'No folder available for this section' });
      return;
    }
    
    // Get the directory path from the first file in the section
    const firstPath = section.paths[0];
    const dirPath = firstPath.substring(0, firstPath.lastIndexOf('/'));
    const newPath = `${dirPath}/${newFileName.trim()}`;
    
    setCreatingFile(true);
    try {
      // Create an empty file
      await axios.put(`${API_BASE_URL}/files/${newPath}/content`, {
        content: '',
      });
      setMessage({ type: 'success', text: 'File created successfully' });
      setNewFileName('');
      setShowNewFileModal(false);
      await loadExpertCenter();
      // Select the new file
      setTimeout(() => void selectFile(newPath), 100);
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || 'Failed to create file';
      setMessage({ type: 'error', text: errMsg });
    } finally {
      setCreatingFile(false);
    }
  };

  const handleDeleteFile = async (path: string) => {
    const fileName = path.split('/').pop() || path;
    const confirmed = window.confirm(`Delete file "${fileName}"?`);
    if (!confirmed) {
      return;
    }
    
    setDeletingFile(true);
    try {
      await axios.delete(`${API_BASE_URL}/files/${path}`);
      setMessage({ type: 'success', text: 'File deleted successfully' });
      if (selectedPath === path) {
        setSelectedPath('');
        setSelectedFile(null);
        setEditingContent('');
      }
      await loadExpertCenter();
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || 'Failed to delete file';
      setMessage({ type: 'error', text: errMsg });
    } finally {
      setDeletingFile(false);
    }
  };

  const canManageFiles = activeTab !== 'profile' && activeTab !== 'skill' && activeTab !== 'tools';
  
  // Load tools when expert-creator is selected
  useEffect(() => {
    if (selectedExpertId === 'expert-creator') {
      void loadToolsList();
    }
  }, [selectedExpertId]);
  
  // Load tool code when a tool is selected
  useEffect(() => {
    if (selectedTool && selectedExpertId === 'expert-creator' && activeTab === 'tools') {
      void loadToolCode(selectedTool.name);
    }
  }, [selectedTool, selectedExpertId, activeTab]);
  
  // System experts that cannot be deleted
  const SYSTEM_EXPERTS = ['expert-creator'];
  const isSystemExpert = selectedExpertId ? SYSTEM_EXPERTS.includes(selectedExpertId) : false;

  const restoreVersion = (content: string) => {
    setEditingContent(content);
    setMessage({ type: 'success', text: t('management.versionRestored') });
  };

  const tabMeta: Record<WorkbenchTab, { icon: React.ReactNode }> = {
    profile: { icon: <Bot size={14} /> },
    skill: { icon: <ScrollText size={14} /> },
    templates: { icon: <FileCode size={14} /> },
    references: { icon: <BookOpen size={14} /> },
    scripts: { icon: <Code2 size={14} /> },
    tools: { icon: <Braces size={14} /> },
  };

  const fileKind = useMemo(() => {
    if (!selectedFile) {
      return '';
    }
    if (selectedFile.path.endsWith('.yaml') || selectedFile.path.endsWith('.yml')) {
      return t('management.kindYaml');
    }
    if (selectedFile.path.endsWith('.json')) {
      return t('management.kindJson');
    }
    if (selectedFile.path.endsWith('.md')) {
      return t('management.kindMarkdown');
    }
    if (selectedFile.path.endsWith('.py')) {
      return t('management.kindScript');
    }
    return t('management.kindText');
  }, [selectedFile, t]);

  return (
    <div className="max-w-[1560px] mx-auto p-6 bg-gray-50/30 min-h-screen">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link to="/" className="p-2 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-400 hover:text-indigo-600 transition-all">
            <ArrowLeft size={20} />
          </Link>
          <div>
            <div className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-0.5">{t('management.admin')}</div>
            <h1 className="text-xl font-black text-gray-900 uppercase">
              {t('management.workbenchExperts')}
            </h1>
            <div className="text-xs text-gray-400 mt-1">{t('management.title')}</div>
          </div>
        </div>
        <LanguageSwitcher />
      </div>

      {message ? (
        <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between ${message.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700'}`}>
          <span className="font-medium text-sm">{message.text}</span>
          <button type="button" onClick={() => setMessage(null)} className="text-xs font-bold uppercase opacity-60 hover:opacity-100">
            {t('common.dismiss')}
          </button>
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8">
        <aside className="xl:col-span-3 space-y-6">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden flex flex-col h-[82vh]">
            <div className="px-5 py-4 border-b border-gray-100 bg-white sticky top-0 z-10">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-black text-gray-900 uppercase">{t('management.workbenchExperts')}</div>
                <button
                   onClick={() => setShowCreateModal(true)}
                   className="p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-all shadow-md shadow-indigo-100"
                   title={t('management.createExpert')}
                >
                  <Plus size={16} />
                </button>
              </div>
              <div className="mt-4 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                  <Search size={14} />
                </div>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder={t('management.searchExperts')}
                  className="w-full bg-gray-50 border border-gray-100 rounded-xl pl-9 pr-3 py-2 text-xs outline-none focus:border-indigo-400 focus:bg-white transition-all"
                />
              </div>
            </div>

            <div className="p-3 space-y-2 flex-1 overflow-y-auto">
              {/* Regular experts list */}
              {filteredExperts
                .filter((expert) => !SYSTEM_EXPERTS.includes(expert.id))
                .map((expert) => {
                  const active = selectedExpertId === expert.id;
                  return (
                    <button
                      key={expert.id}
                      type="button"
                      onClick={() => setSelectedExpertId(expert.id)}
                      className={`w-full rounded-2xl border p-4 text-left transition-all ${
                        active
                          ? 'border-indigo-500 bg-indigo-600 text-white shadow-lg shadow-indigo-100'
                          : 'border-gray-200 bg-white text-gray-700 hover:border-indigo-200 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-xs font-black uppercase truncate">{translateExpertName(expert)}</div>
                          <div className={`text-[11px] mt-1 truncate ${active ? 'text-indigo-100' : 'text-gray-400'}`}>{expert.id}</div>
                        </div>
                        <Bot size={16} />
                      </div>
                    </button>
                  );
                })}
              {filteredExperts.filter((e) => !SYSTEM_EXPERTS.includes(e.id)).length === 0 && (
                <div className="py-10 text-center text-xs text-gray-400 italic">
                  {t('management.noExpertSearchResults')}
                </div>
              )}
              
              {/* System Tools Section */}
              <div className="pt-4 mt-4 border-t border-gray-200">
                <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-3 px-1">
                  {t('management.systemTools') || 'System Tools'}
                </div>
                {filteredExperts
                  .filter((expert) => SYSTEM_EXPERTS.includes(expert.id))
                  .map((expert) => {
                    const active = selectedExpertId === expert.id;
                    return (
                      <button
                        key={expert.id}
                        type="button"
                        onClick={() => setSelectedExpertId(expert.id)}
                        className={`w-full rounded-2xl border p-4 text-left transition-all ${
                          active
                            ? 'border-purple-500 bg-purple-600 text-white shadow-lg shadow-purple-100'
                            : 'border-gray-200 bg-gradient-to-br from-purple-50 to-indigo-50 text-gray-700 hover:border-purple-200'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-xs font-black uppercase truncate">{translateExpertName(expert)}</div>
                            <div className={`text-[11px] mt-1 truncate ${active ? 'text-purple-100' : 'text-gray-400'}`}>{expert.id}</div>
                          </div>
                          <Code2 size={16} />
                        </div>
                      </button>
                    );
                  })}
              </div>
            </div>
          </div>
        </aside>

        <main className="xl:col-span-9 space-y-6">
          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
              <div className="space-y-3">
                <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">{t('management.workbenchTitle')}</div>
                <div className="text-2xl font-black text-gray-900">{translateExpertName(selectedExpert)}</div>
                <div className="max-w-3xl text-sm text-gray-500 leading-relaxed">
                  {translateExpertDescription(selectedExpert)}
                </div>
              </div>
              {selectedExpert && !isSystemExpert && (
                <button
                  type="button"
                  onClick={handleDeleteExpert}
                  disabled={deleting}
                  className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs font-black uppercase text-rose-600 hover:bg-rose-100 disabled:opacity-50 transition-all"
                >
                  {deleting ? <LucideLoader size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  {t('management.deleteExpert')}
                </button>
              )}
            </div>
          </section>

          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-3">{t('management.workbenchSections')}</div>
              <div className="flex flex-wrap gap-2">
                {TAB_ORDER.map((tab) => {
                  const section = activeSections.find((item) => item.tab === tab);
                  // For tools tab, use toolsList.length instead of paths.length
                  const count = tab === 'tools' 
                    ? toolsList.length 
                    : (section?.paths.length ?? 0);
                  const active = activeTab === tab;
                  // Only show tools tab for expert-creator
                  if (tab === 'tools' && selectedExpertId !== 'expert-creator') {
                    return null;
                  }
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setActiveTab(tab)}
                      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wide transition-all ${
                        active ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-100' : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      {tabMeta[tab].icon}
                      <span>{section?.title ?? tab}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] ${active ? 'bg-white/15 text-white' : 'bg-white text-gray-500'}`}>{count}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 2xl:grid-cols-12">
              <div className="2xl:col-span-4 border-r border-gray-100 bg-gray-50/70">
                <div className="p-5 border-b border-gray-100 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-black text-gray-900">{activeSection?.title ?? t('management.selectExpert')}</div>
                    <div className="text-xs text-gray-500 mt-1">{activeSection?.description ?? t('management.selectExpertHint')}</div>
                  </div>
                  {canManageFiles && activeSection && (
                    <button
                      type="button"
                      onClick={() => setShowNewFileModal(true)}
                      className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-all shadow-sm"
                      title={t('common.newFile') || 'New File'}
                    >
                      <Plus size={14} />
                    </button>
                  )}
                </div>
                <div className="p-4 max-h-[620px] overflow-y-auto">
                  {/* Tools List for expert-creator */}
                  {activeTab === 'tools' && selectedExpertId === 'expert-creator' ? (
                    loadingTools ? (
                      <div className="flex items-center justify-center py-12">
                        <LucideLoader size={24} className="animate-spin text-indigo-600" />
                      </div>
                    ) : toolsList.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-sm text-gray-400 min-h-[220px] flex items-center justify-center text-center">
                        No tools found
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-3">
                        {toolsList.map((tool) => {
                          const active = selectedTool?.name === tool.name;
                          return (
                            <div
                              key={tool.name}
                              className={`rounded-2xl border p-4 transition-all cursor-pointer ${
                                active ? 'border-indigo-500 bg-white shadow-sm' : 'border-gray-200 bg-white hover:border-indigo-200'
                              }`}
                              onClick={() => setSelectedTool(tool)}
                            >
                              <div className="flex items-start gap-3">
                                <div className={`p-2 rounded-xl ${active ? 'bg-indigo-600 text-white' : 'bg-gray-50 text-gray-500'}`}>
                                  <Braces size={14} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="text-xs font-black text-gray-900">{tool.name}</div>
                                  <div className="text-[11px] text-gray-400 mt-1">{tool.category}</div>
                                  <div className="text-xs text-gray-600 mt-2 line-clamp-2">{tool.description_zh}</div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )
                  ) : !activeSection || activeSection.paths.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-sm text-gray-400 min-h-[220px] flex items-center justify-center text-center">
                      {t('management.emptySection')}
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {activeSection.paths.map((path) => {
                        const active = path === selectedPath;
                        return (
                          <div
                            key={path}
                            className={`rounded-2xl border p-4 transition-all relative group ${
                              active ? 'border-indigo-500 bg-white shadow-sm' : 'border-gray-200 bg-white hover:border-indigo-200'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => void selectFile(path)}
                              className="w-full text-left"
                            >
                              <div className="flex items-start gap-3">
                                <div className={`p-2 rounded-xl ${active ? 'bg-indigo-600 text-white' : 'bg-gray-50 text-gray-500'}`}>
                                  <Braces size={14} />
                                </div>
                                <div className="min-w-0">
                                  <div className="text-xs font-black text-gray-900 truncate">{fileNamesByPath[path] ?? path.split('/').pop() ?? path}</div>
                                  <div className="text-[11px] text-gray-400 mt-1 break-all">{displayRelativePath(path)}</div>
                                </div>
                              </div>
                            </button>
                            {canManageFiles && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleDeleteFile(path);
                                }}
                                disabled={deletingFile}
                                className="absolute top-2 right-2 p-1.5 bg-rose-50 text-rose-500 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-rose-100 transition-all"
                                title={t('common.delete') || 'Delete'}
                              >
                                {deletingFile ? <LucideLoader size={12} className="animate-spin" /> : <Trash2 size={12} />}
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="2xl:col-span-8 grid grid-cols-1 xl:grid-cols-12 min-h-[620px]">
                <div className="xl:col-span-8 flex flex-col">
                  {/* Tool Details */}
                  {activeTab === 'tools' && selectedExpertId === 'expert-creator' ? (
                    <>
                      <div className="px-6 py-5 border-b border-gray-100 bg-white">
                        <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">Tool Details</div>
                        <h2 className="text-sm font-black text-gray-900 mt-1">{selectedTool?.name ?? 'Select a Tool'}</h2>
                        {selectedTool && (
                          <div className="text-xs text-gray-400 mt-1">{selectedTool.category}</div>
                        )}
                      </div>
                      {selectedTool ? (
                        <div className="flex-1 overflow-y-auto p-6 bg-white">
                          <div className="space-y-4">
                            <div>
                              <div className="text-xs font-black text-gray-400 uppercase mb-2">Description</div>
                              <div className="text-sm text-gray-700">{selectedTool.description_zh}</div>
                              <div className="text-sm text-gray-500 mt-1">{selectedTool.description_en}</div>
                            </div>
                            
                            <div>
                              <div className="text-xs font-black text-gray-400 uppercase mb-2">Use Cases</div>
                              <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                                {selectedTool.use_cases.map((uc, idx) => (
                                  <li key={idx}>{uc}</li>
                                ))}
                              </ul>
                            </div>
                            
                            <div>
                              <div className="text-xs font-black text-gray-400 uppercase mb-2">Input Schema</div>
                              <pre className="text-xs bg-gray-50 p-3 rounded-lg overflow-x-auto">
                                {JSON.stringify(selectedTool.input_schema, null, 2)}
                              </pre>
                            </div>
                            
                            <div>
                              <div className="text-xs font-black text-gray-400 uppercase mb-2">Output Schema</div>
                              <pre className="text-xs bg-gray-50 p-3 rounded-lg overflow-x-auto">
                                {JSON.stringify(selectedTool.output_schema, null, 2)}
                              </pre>
                            </div>
                            
                            {toolCode && (
                              <div>
                                <div className="text-xs font-black text-gray-400 uppercase mb-2">Implementation</div>
                                <pre className="text-xs bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto max-h-[300px]">
                                  {toolCode}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 flex items-center justify-center text-sm text-gray-400 bg-white">
                          Select a tool to view details
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="px-6 py-5 border-b border-gray-100 bg-white flex items-center justify-between gap-4">
                        <div>
                          <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">{fileKind}</div>
                          <h2 className="text-sm font-black text-gray-900 mt-1">{selectedFile?.name ?? t('management.fileEditor')}</h2>
                          <div className="text-[11px] text-gray-400 mt-1">{selectedFile ? displayRelativePath(selectedFile.path) : t('management.selectFileHint')}</div>
                        </div>
                        <button
                          type="button"
                          onClick={handleSave}
                          disabled={!selectedFile || saving}
                          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-50"
                        >
                          {saving ? <LucideLoader size={14} className="animate-spin" /> : <Save size={14} />}
                          {t('management.saveChanges')}
                        </button>
                      </div>
                      {selectedFile ? (
                        <textarea
                          className="flex-1 w-full p-6 font-mono text-sm text-gray-800 focus:outline-none resize-none bg-white"
                          value={editingContent}
                          onChange={(event) => setEditingContent(event.target.value)}
                          spellCheck={false}
                        />
                      ) : (
                        <div className="flex-1 bg-white flex items-center justify-center text-sm text-gray-400">
                          {t('management.emptySection')}
                        </div>
                      )}
                    </>
                  )}
                </div>

                <aside className="xl:col-span-4 border-l border-gray-100 bg-gray-50/70">
                  <div className="px-5 py-4 border-b border-gray-100">
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('management.versionHistory')}</div>
                  </div>
                  <div className="p-4 space-y-3 max-h-[620px] overflow-y-auto">
                    {!selectedFile?.versions?.length ? (
                      <div className="rounded-xl border border-dashed border-gray-200 bg-white p-5 text-xs text-gray-400">
                        {t('management.noHistory')}
                      </div>
                    ) : (
                      selectedFile.versions.map((version) => (
                        <div key={version.version_id} className="rounded-xl border border-gray-200 bg-white p-3">
                          <div className="flex items-center justify-between gap-2 mb-3">
                            <span className="text-[10px] font-black text-indigo-600 uppercase">v{version.version_id}</span>
                            <span className="text-[10px] text-gray-400">{version.timestamp}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => restoreVersion(version.content)}
                            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-[10px] font-black uppercase text-gray-600 hover:bg-indigo-600 hover:border-indigo-600 hover:text-white transition-all"
                          >
                            {t('management.inspectRestoreBtn')}
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </aside>
              </div>
            </div>
          </section>
        </main>
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-white rounded-[2.5rem] shadow-2xl border border-white/20 w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-300">
            {creating ? (
              <div className="p-12 text-center space-y-8">
                <div className="relative mx-auto w-32 h-32">
                  <div className="absolute inset-0 rounded-full border-4 border-indigo-50 animate-pulse"></div>
                  <div className="absolute inset-0 rounded-full border-t-4 border-indigo-600 animate-spin"></div>
                  <div className="absolute inset-0 flex items-center justify-center text-indigo-600">
                    <Bot size={48} className="animate-bounce" />
                  </div>
                </div>
                
                <div className="space-y-4">
                  <h3 className="text-2xl font-black text-gray-900">{t('management.aiBuilding')}</h3>
                  <div className="flex flex-col gap-3 max-w-xs mx-auto">
                    {GENERATION_STEPS.map((step, idx) => (
                      <div key={step} className={`flex items-center gap-3 text-sm transition-all duration-500 ${idx === generationStep ? 'text-indigo-600 font-bold scale-105' : idx < generationStep ? 'text-emerald-500 opacity-60' : 'text-gray-300 opacity-40'}`}>
                        {idx < generationStep ? <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> : <div className={`w-1.5 h-1.5 rounded-full ${idx === generationStep ? 'bg-indigo-600' : 'bg-gray-300'}`} />}
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-4">
                  <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                    <div 
                      className="bg-indigo-600 h-full transition-all duration-1000 ease-out" 
                      style={{ width: `${((generationStep + 1) / GENERATION_STEPS.length) * 100}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-gray-400 mt-4 uppercase tracking-[0.2em] font-black">{t('management.buildingHint')}</p>
                </div>
              </div>
            ) : (
              <>
                <div className="px-10 pt-12 pb-8 text-center">
                  <div className="mx-auto w-20 h-20 bg-indigo-50 rounded-3xl flex items-center justify-center text-indigo-600 mb-6 rotate-3">
                    <Plus size={40} />
                  </div>
                  <h3 className="text-2xl font-black text-gray-900 tracking-tight">{t('management.newExpertDomain')}</h3>
                  <p className="text-gray-500 mt-3 px-4">{t('management.newExpertDomainHint')}</p>
                </div>
                
                <div className="px-10 pb-12 space-y-6">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">{t('management.expertNameLabel')}</label>
                    <input
                      autoFocus
                      value={newExpertName}
                      onChange={(e) => setNewExpertName(e.target.value)}
                      placeholder={t('management.searchExperts')}
                      className="w-full rounded-2xl border-2 border-gray-100 bg-gray-50 px-5 py-4 text-sm font-medium outline-none focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-500/5 transition-all"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">{t('management.expertDescLabel')}</label>
                    <textarea
                      value={newExpertDescription}
                      onChange={(e) => setNewExpertDescription(e.target.value)}
                      placeholder={t('management.searchExperts')}
                      className="w-full rounded-2xl border-2 border-gray-100 bg-gray-50 px-5 py-4 text-sm font-medium outline-none focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-500/5 transition-all min-h-[140px] resize-none"
                    />
                  </div>

                  <div className="flex gap-4 pt-4">
                    <button
                      onClick={() => setShowCreateModal(false)}
                      className="flex-1 px-6 py-4 rounded-2xl border-2 border-gray-100 text-sm font-black uppercase text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-all"
                    >
                      {t('management.back')}
                    </button>
                    <button
                      disabled={!newExpertName.trim() || creating}
                      onClick={handleCreateExpert}
                      className="flex-[2] px-8 py-4 rounded-2xl bg-indigo-600 text-white text-sm font-black uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-50 shadow-xl shadow-indigo-200 transition-all flex items-center justify-center gap-3 group"
                    >
                      <span>{t('management.startGeneration')}</span>
                      <Bot size={18} className="group-hover:rotate-12 transition-transform" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* New File Modal */}
      {showNewFileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md overflow-hidden">
            <div className="px-8 pt-8 pb-6 border-b border-gray-100 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">{activeSection?.title}</div>
                <h3 className="text-lg font-black text-gray-900 mt-1">{t('common.newFile') || 'New File'}</h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowNewFileModal(false);
                  setNewFileName('');
                }}
                className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-all"
              >
                <X size={18} />
              </button>
            </div>
            
            <div className="px-8 py-6">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">{t('common.fileName') || 'File Name'}</label>
                <input
                  autoFocus
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  placeholder="example.yaml"
                  className="w-full rounded-xl border-2 border-gray-100 bg-gray-50 px-4 py-3 text-sm font-medium outline-none focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-500/5 transition-all"
                />
              </div>
            </div>
            
            <div className="px-8 pb-8 flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowNewFileModal(false);
                  setNewFileName('');
                }}
                className="flex-1 px-4 py-3 rounded-xl border-2 border-gray-100 text-sm font-black uppercase text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-all"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={!newFileName.trim() || creatingFile}
                onClick={handleCreateFile}
                className="flex-[2] px-4 py-3 rounded-xl bg-indigo-600 text-white text-sm font-black uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
              >
                {creatingFile ? <LucideLoader size={14} className="animate-spin" /> : <Plus size={14} />}
                {t('common.create') || 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="fixed bottom-6 right-6 bg-white border border-gray-200 shadow-lg rounded-full px-4 py-3 flex items-center gap-2 text-xs font-bold text-gray-600">
          <LucideLoader size={14} className="animate-spin" />
          {t('common.loading')}
        </div>
      ) : null}
    </div>
  );
}

export const Management = ExpertCenter;
