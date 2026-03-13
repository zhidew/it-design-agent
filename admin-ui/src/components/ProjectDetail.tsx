import React, { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import { ArrowLeft, Play, RefreshCw, Activity, Check, X, AlertCircle, Upload, FileText, Database, Layers, Book, List } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';
import { TaskKanban } from './TaskKanban';
import type { NodeStatus } from './TaskKanban';
import { ArtifactViewer } from './ArtifactViewer';

const AGENT_MAPPING: Record<string, string[]> = {
  planner: ['requirements.json', 'input-requirements.md', 'planner-reasoning.md', 'original-requirements.md'],
  'architecture-mapping': ['architecture.md', 'module-map.json', 'architecture-mapping-reasoning.md'],
  'integration-design': ['integration-', 'asyncapi.yaml', 'integration-design-reasoning.md'],
  'config-design': ['config-catalog.yaml', 'config-matrix.md', 'config-design-reasoning.md'],
  'data-design': ['schema.sql', 'er.md', 'migration-plan.md', 'data-design-reasoning.md'],
  'flow-design': ['sequence-', 'state-', 'flow-design-reasoning.md'],
  'ddd-structure': ['ddd-structure.md', 'class-', 'ddd-structure-reasoning.md'],
  'test-design': ['test-inputs.md', 'coverage-map.json', 'test-design-reasoning.md'],
  'ops-readiness': ['slo.yaml', 'observability-spec.yaml', 'deployment-runbook.md', 'ops-readiness-reasoning.md'],
  'design-assembler': ['detailed-design.md', 'traceability.json', 'review-checklist.md', 'design-assembler-reasoning.md'],
  validator: [],
};

type StreamStatus = 'idle' | 'connecting' | 'connected' | 'error';

interface InputFile {
  type: 'ir' | 'physical' | 'logical' | 'dict' | 'lookup';
  file: File;
}

export function ProjectDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [versions, setVersions] = useState<string[]>([]);
  const [requirement, setRequirement] = useState('');
  
  const [inputFiles, setInputFiles] = useState<InputFile[]>([]);

  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');

  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const [selectedNode, setSelectedNode] = useState<string | null>('planner');

  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<any>(null);

  const [isVersionsLoading, setIsVersionsLoading] = useState(false);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [uiError, setUiError] = useState<string | null>(null);

  const [isLogsOpen, setIsLogsOpen] = useState(true);

  const pollInterval = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (id) void loadVersions();
  }, [id]);

  useEffect(() => {
    if (id && selectedVersion) {
      void fetchState();
      pollInterval.current = setInterval(() => {
        void fetchState();
      }, 3000);
    }
    return () => {
      if (pollInterval.current) clearInterval(pollInterval.current);
    };
  }, [id, selectedVersion]);

  const fetchState = async () => {
    if (!id || !selectedVersion) return;
    try {
      const state = await api.getProjectState(id, selectedVersion);
      setWorkflowState(state);
      
      const newStatuses: Record<string, NodeStatus> = {};
      let hasRunning = false;
      if (state.task_queue) {
        state.task_queue.forEach((t: any) => {
          newStatuses[t.agent_type] = t.status;
          if (t.status === 'running') hasRunning = true;
        });
      }
      setNodeStatuses(prev => ({...prev, ...newStatuses}));

      if (hasRunning || state.workflow_phase !== 'DONE') {
        void loadArtifacts(selectedVersion);
      }
      
    } catch (err: any) {
      if (err.response?.status === 404) {
        setWorkflowState(null);
      }
    }
  };

  const loadVersions = async () => {
    if (!id) return;
    setIsVersionsLoading(true);
    try {
      const res = await api.getProjectVersions(id);
      setVersions(res);
      if (res.length > 0 && !selectedVersion) {
        handleSelectVersion(res[0]);
      }
    } catch {
      setUiError(t('common.loadError'));
    } finally {
      setIsVersionsLoading(false);
    }
  };

  const generateVersionId = () => {
    const d = new Date();
    const pad = (n: number, len: number) => String(n).padStart(len, '0');
    return `v${d.getFullYear()}${pad(d.getMonth()+1, 2)}${pad(d.getDate(), 2)}${pad(d.getHours(), 2)}${pad(d.getMinutes(), 2)}${pad(d.getSeconds(), 2)}`;
  };

  const handleFileChange = (type: InputFile['type'], e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setInputFiles(prev => [...prev.filter(f => f.type !== type), { type, file }]);
    }
  };

  const handleRun = async () => {
    const hasIRFile = inputFiles.some(f => f.type === 'ir');
    if (!id || (!requirement.trim() && !hasIRFile)) return;

    setLoading(true);
    setUiError(null);
    try {
      const timestampVersion = generateVersionId();
      setSelectedVersion(timestampVersion);
      setNodeStatuses({});
      setArtifacts({});
      setSelectedFile(null);
      setWorkflowState(null);
      setSelectedNode('planner');

      if (inputFiles.length > 0) {
        await api.uploadBaselineFiles(id, timestampVersion, inputFiles.map(f => f.file));
      }

      await api.runOrchestrator(id, timestampVersion, requirement);
      
      setRequirement('');
      setInputFiles([]);
      void loadArtifacts(timestampVersion);
      void loadVersions();
    } catch {
      setUiError(t('common.error'));
      setLoading(false);
    } finally {
      setLoading(false);
    }
  };

  const handleResumeExecution = async () => {
    if (!id || !selectedVersion) return;
    setLoading(true);
    try {
      await api.runOrchestrator(id, selectedVersion, "");
      void fetchState();
    } catch {
      setUiError("Failed to resume execution");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectVersion = (version: string) => {
    setSelectedVersion(version);
    setSelectedFile(null);
    setSelectedNode('planner');
    void loadArtifacts(version);
  };

  const loadArtifacts = async (version: string) => {
    if (!id) return;
    setIsArtifactsLoading(true);
    try {
      const data = await api.getProjectArtifacts(id, version);
      setArtifacts(data);
    } catch {
      setArtifacts({});
    } finally {
      setIsArtifactsLoading(false);
    }
  };

  const filteredArtifacts = useMemo(() => {
    if (!selectedNode || !AGENT_MAPPING[selectedNode]) {
      return [];
    }
    const patterns = AGENT_MAPPING[selectedNode];
    return Object.keys(artifacts).filter((filename) =>
      !filename.endsWith('-reasoning.md') && patterns.some(
        (pattern) => filename.startsWith(pattern) || filename === pattern || 
        (pattern === 'requirements.json' && filename.includes('requirements')) ||
        (selectedNode === 'planner' && (filename.includes('model') || filename.includes('lookup') || filename === 'original-requirements.md'))
      ),
    );
  }, [selectedNode, artifacts]);

  const filteredLogs = useMemo(() => {
    if (!workflowState?.history) return [];
    const history = workflowState.history;

    if (selectedNode && selectedNode !== 'planner' && selectedNode !== 'validator') {
      const reasoningFile = `${selectedNode}-reasoning.md`;
      if (artifacts[reasoningFile]) {
        return [artifacts[reasoningFile]];
      }
    }

    if (selectedNode === 'planner') {
      if (artifacts['planner-reasoning.md']) {
        return [artifacts['planner-reasoning.md']];
      }
    }

    if (selectedNode === 'validator') {
      if (artifacts['validator.log']) {
        return [artifacts['validator.log']];
      }
      return history.filter((log: string) => 
        log.toLowerCase().includes('validator') || log.toLowerCase().includes('validate') || log.includes('[SYSTEM]') || log.includes('[ERROR]')
      );
    }

    return history.filter((log: string) => log.includes('[SYSTEM]') || log.includes('[HUMAN]') || log.includes('[ERROR]'));
  }, [workflowState?.history, selectedNode, artifacts]);

  const renderUploadBtn = (type: InputFile['type'], label: string, icon: React.ReactNode, required: boolean = false) => {
    const hasFile = inputFiles.some(f => f.type === type);
    return (
      <div className="flex flex-col gap-1.5">
        <label className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border cursor-pointer transition-all ${hasFile ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-gray-100 text-gray-500 hover:border-indigo-200 hover:bg-indigo-50/30'}`}>
          {icon}
          <div className="flex-1 flex items-center gap-1">
            <span className="text-[10px] font-black uppercase tracking-wider">{label}</span>
            {required && <span className="text-rose-500 font-bold">*</span>}
          </div>
          {hasFile ? <Check size={12} strokeWidth={3} /> : <Upload size={12} />}
          <input type="file" className="hidden" onChange={(e) => handleFileChange(type, e)} />
        </label>
        {hasFile && <span className="text-[9px] font-bold text-emerald-600 truncate px-1">{inputFiles.find(f => f.type === type)?.file.name}</span>}
      </div>
    );
  };

  const isIRProvided = requirement.trim().length > 0 || inputFiles.some(f => f.type === 'ir');

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col font-sans text-gray-900 antialiased selection:bg-indigo-100 selection:text-indigo-900">
      <header className="sticky top-0 z-40 bg-white/80 backdrop-blur-md border-b border-gray-100 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-400 hover:text-gray-600">
              <ArrowLeft size={20} />
            </Link>
            <div className="flex flex-col">
              <h1 className="text-lg font-black tracking-tight text-gray-800 uppercase">{id}</h1>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{t('projectDetail.activeProject')}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <LanguageSwitcher />
            <div className="h-8 w-px bg-gray-100 mx-2" />
            <div className="flex -space-x-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-8 w-8 rounded-full border-2 border-white bg-gray-200 flex items-center justify-center text-[10px] font-bold text-gray-500">
                  {String.fromCharCode(64 + i)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full p-6 grid grid-cols-12 gap-8">
        <aside className="col-span-12 lg:col-span-3 space-y-8">
          <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-6 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('projectDetail.newDesignRun')}</h2>
              {inputFiles.length > 0 && <button onClick={() => setInputFiles([])} className="text-[9px] font-black text-rose-500 uppercase tracking-widest hover:underline">{t('projectDetail.clearFiles')}</button>}
            </div>
            
            <div className="grid grid-cols-1 gap-2">
              {renderUploadBtn('ir', 'IR(IT Requirement)', <FileText size={14} />, true)}
              {renderUploadBtn('physical', 'Physical Model', <Database size={14} />)}
              {renderUploadBtn('logical', 'Logical Model', <Layers size={14} />)}
              {renderUploadBtn('dict', 'Data Dictionary', <Book size={14} />)}
              {renderUploadBtn('lookup', 'Lookup List', <List size={14} />)}
            </div>

            <div className="h-px bg-gray-50" />

            <div className="space-y-2">
              <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest px-1">{t('projectDetail.orInputText')} <span className="text-rose-500">*</span></label>
              <textarea
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                placeholder={t('projectDetail.requirementPlaceholder')}
                className="w-full h-32 p-4 bg-gray-50 border-none rounded-2xl text-sm focus:ring-2 focus:ring-indigo-500 transition-all resize-none placeholder:text-gray-400 font-medium"
              />
            </div>

            <button
              onClick={handleRun}
              disabled={loading || !isIRProvided}
              className={`w-full py-4 rounded-2xl font-black text-xs uppercase tracking-widest flex items-center justify-center gap-3 transition-all ${
                loading || !isIRProvided ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-200'
              }`}
            >
              {loading ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
              {loading ? t('projectDetail.running') : t('projectDetail.startDesign')}
            </button>
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between px-2">
              <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('projectDetail.versionHistory')}</h2>
              <button onClick={loadVersions} className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors">
                <RefreshCw size={14} className={isVersionsLoading ? 'animate-spin' : ''} />
              </button>
            </div>
            <div className="space-y-2">
              {versions.map((v) => (
                <button
                  key={v}
                  onClick={() => handleSelectVersion(v)}
                  className={`w-full flex items-center justify-between p-4 rounded-2xl transition-all text-xs text-left ${
                    selectedVersion === v 
                      ? 'bg-white border-2 border-indigo-500 shadow-md text-gray-900 font-bold' 
                      : 'bg-transparent border border-transparent text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  <span className="font-mono">{v}</span>
                  {selectedVersion === v && <div className="h-2 w-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]" />}
                </button>
              ))}
            </div>
          </section>
        </aside>

        <div className="col-span-12 lg:col-span-9 space-y-8">
          <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-8">
            <div className="flex items-center justify-between">
               <div className="flex items-center gap-4">
                 <div className="p-3 bg-indigo-50 rounded-2xl text-indigo-600">
                   <Activity size={24} />
                 </div>
                 <div>
                   <h2 className="text-xl font-black tracking-tight text-gray-800">{t('projectDetail.executionPipeline')}</h2>
                   <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mt-0.5">{t('projectDetail.realTimeOrchestration')}</p>
                 </div>
               </div>
               
               <div className="flex items-center gap-3">
                 {workflowState?.task_queue?.some((t: any) => t.status === 'todo' || t.status === 'failed') && !loading && (
                   <button 
                     onClick={handleResumeExecution}
                     className="px-4 py-2 bg-indigo-100 text-indigo-600 rounded-xl text-xs font-black uppercase tracking-wider hover:bg-indigo-200 transition-all flex items-center gap-2"
                   >
                     <Play size={14} fill="currentColor" />
                     {t('projectDetail.resumeExecution')}
                   </button>
                 )}
               </div>
            </div>

            <TaskKanban 
              tasks={workflowState?.task_queue || []}
              nodeStatuses={nodeStatuses}
              selectedNode={selectedNode}
              onSelectNode={setSelectedNode}
              t={t}
              currentPhase={workflowState?.workflow_phase}
            />

            <div className="mt-8 border-t border-gray-50 pt-6">
              <button 
                onClick={() => setIsLogsOpen(!isLogsOpen)}
                className="flex items-center justify-between w-full group"
              >
                <div className="flex items-center gap-3">
                  <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-widest group-hover:text-indigo-500 transition-colors">
                    {selectedNode && selectedNode !== 'planner' && selectedNode !== 'validator' ? t('projectDetail.subagentReasoning') : t('projectDetail.orchestrationLogs')}
                  </h3>
                  {loading && <RefreshCw size={10} className="animate-spin text-indigo-500" />}
                </div>
                <div className={`text-gray-300 transition-transform duration-300 ${isLogsOpen ? 'rotate-180' : ''}`}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                </div>
              </button>
              
              {isLogsOpen && (
                <div className="mt-4 bg-gray-900 rounded-2xl p-4 font-mono text-[11px] leading-relaxed text-gray-300 overflow-y-auto max-h-60 space-y-1 animate-in slide-in-from-top-2 duration-300">
                  {filteredLogs && filteredLogs.length > 0 ? (
                    filteredLogs.map((log: string, idx: number) => (
                      <div key={idx} className="flex gap-3 whitespace-pre-wrap">
                        <span className="text-gray-600 flex-shrink-0">[{idx+1}]</span>
                        <span className={log.includes('[ERROR]') ? 'text-rose-400' : 'text-emerald-400/80'}>
                          {log}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="text-gray-600 italic text-[10px]">{t('projectDetail.noRelevantContext')}</div>
                  )}
                </div>
              )}
            </div>
          </section>

          <section className="space-y-6">
            <div className="flex items-center gap-3 px-2">
              <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
                {selectedNode === 'planner' ? t('projectDetail.inputMaterials') : t('projectDetail.designArtifacts')}
              </h2>
              <div className="h-px flex-1 bg-gray-100" />
            </div>
            
            <ArtifactViewer 
              artifacts={artifacts}
              selectedFile={selectedFile}
              onSelectFile={setSelectedFile}
              filteredArtifacts={filteredArtifacts}
              t={t}
            />
          </section>
        </div>
      </main>

      {uiError && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom duration-300">
          <div className="bg-gray-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-4 border border-white/10 backdrop-blur-xl">
            <div className="p-2 bg-rose-500/20 rounded-full text-rose-400">
              <X size={20} />
            </div>
            <span className="text-sm font-bold tracking-tight">{uiError}</span>
            <button onClick={() => setUiError(null)} className="ml-4 text-gray-400 hover:text-white transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
