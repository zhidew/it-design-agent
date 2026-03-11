import React, { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import { ArrowLeft, Play, FileText, CheckCircle, XCircle, FileJson, Database, Circle, Activity, Loader as LucideLoader, RefreshCw, Code, Maximize2, Copy, Check, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mermaid from 'mermaid';
import { Highlight, themes } from 'prism-react-renderer';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';

mermaid.initialize({
  startOnLoad: true,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
});

const Mermaid = ({ chart }: { chart: string }) => {
  const { t } = useTranslation();
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let isMounted = true;
    
    const renderChart = async () => {
      if (!chart) return;
      
      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        
        if (isMounted) {
          setSvg(renderedSvg);
          setError(null);
        }
      } catch (err: any) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError(err?.message || t('projectDetail.renderingFailed'));
        }
      }
    };

    void renderChart();
    return () => { isMounted = false; };
  }, [chart, t]);

  const handleCopy = () => {
    void navigator.clipboard.writeText(chart);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (error) {
    return (
      <div className="my-4">
        <div className="p-2 bg-red-50 text-red-600 rounded-t border border-red-200 text-xs font-bold flex justify-between items-center">
          <span>{t('projectDetail.mermaidError')}: {error}</span>
          <button onClick={handleCopy} className="p-1 hover:bg-red-100 rounded transition-colors" title={t('projectDetail.copySource')}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>
        <pre className="bg-gray-100 p-4 rounded-b overflow-x-auto text-xs border-x border-b border-gray-200 text-gray-900 font-mono leading-relaxed">
          <code>{chart}</code>
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-gray-50 rounded-lg border border-gray-100 my-4 gap-3">
        <LucideLoader size={24} className="text-blue-500 animate-spin" />
        <span className="text-gray-400 text-xs font-medium">{t('projectDetail.renderingDiagram')}</span>
      </div>
    );
  }

  return (
    <>
      <div className="group relative my-6">
        {/* Toolbar */}
        <div className="absolute right-2 top-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity z-20">
          <button 
            onClick={handleCopy}
            className="p-1.5 bg-white shadow-sm border border-gray-200 rounded-md text-gray-500 hover:text-blue-600 hover:bg-gray-50 transition-all"
            title={t('projectDetail.copySource')}
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          <button 
            onClick={() => setIsMaximized(true)}
            className="p-1.5 bg-white shadow-sm border border-gray-200 rounded-md text-gray-500 hover:text-blue-600 hover:bg-gray-50 transition-all"
            title={t('projectDetail.fullscreen')}
          >
            <Maximize2 size={16} />
          </button>
        </div>

        {/* Chart Container */}
        <div 
          className="flex justify-center p-6 bg-white rounded-xl border border-gray-100 overflow-x-auto shadow-sm hover:shadow-md transition-all duration-300" 
          dangerouslySetInnerHTML={{ __html: svg }} 
        />
      </div>

      {/* Fullscreen Modal */}
      {isMaximized && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-10">
          <div className="relative w-full h-full bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wider flex items-center gap-2">
                <FileText size={16} className="text-blue-500" />
                {t('projectDetail.diagramPreview')}
              </h3>
              <div className="flex items-center gap-3">
                <button 
                  onClick={handleCopy}
                  className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                >
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? t('common.copied') : t('projectDetail.copyCode')}
                </button>
                <button 
                  onClick={() => setIsMaximized(false)}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
                >
                  <X size={20} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-8 flex items-start justify-center bg-gray-50/30">
              <div 
                className="min-w-full bg-white p-10 rounded-xl shadow-sm border border-gray-100"
                dangerouslySetInnerHTML={{ __html: svg }} 
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
};

const CodeBlock = (props: any) => {
  const { t } = useTranslation();
  const { children, className, node, ...rest } = props;
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const codeString = String(children).replace(/\n$/, '');
  
  // If it's a fenced code block with mermaid language
  if (language === 'mermaid') {
    return <Mermaid chart={codeString} />;
  }

  // If it's a fenced code block with any other language, use prism-react-renderer
  if (language) {
    return (
      <div className="my-6 rounded-xl overflow-hidden border border-gray-200 shadow-sm">
        <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex justify-between items-center">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{language}</span>
          <button 
            onClick={() => {
              void navigator.clipboard.writeText(codeString);
            }}
            className="text-gray-400 hover:text-blue-600 transition-colors"
            title={t('common.copy')}
          >
            <Copy size={14} />
          </button>
        </div>
        <Highlight theme={themes.vsLight} code={codeString} language={language}>
          {({ className, style, tokens, getLineProps, getTokenProps }) => (
            <pre className={`${className} p-4 overflow-x-auto text-sm leading-relaxed`} style={{ ...style, backgroundColor: '#fdfdfd' }}>
              {tokens.map((line, i) => {
                const { key: lineKey, ...lineProps } = getLineProps({ line, key: i });
                return (
                  <div key={lineKey} {...lineProps}>
                    {line.map((token, key) => {
                      const { key: tokenKey, ...tokenProps } = getTokenProps({ token, key });
                      return <span key={tokenKey} {...tokenProps} />;
                    })}
                  </div>
                );
              })}
            </pre>
          )}
        </Highlight>
      </div>
    );
  }

  // Inline code (no language class)
  return (
    <code className="px-1.5 py-0.5 bg-gray-100 text-indigo-700 border border-gray-200 rounded text-[0.85em] font-mono font-semibold mx-0.5" {...rest}>
      {children}
    </code>
  );
};

const AGENT_MAPPING: Record<string, string[]> = {
  planner: ['requirements.json', 'input-requirements.md', 'planner-reasoning.md'],
  'architecture-mapping': ['architecture.md', 'module-map.json', 'architecture-mapping-reasoning.md'],
  'api-design': ['api-internal.yaml', 'api-public.yaml', 'api-design.md', 'errors-rfc9457.json', 'api-design-reasoning.md'],
  'data-design': ['schema.sql', 'er.md', 'migration-plan.md', 'data-design-reasoning.md'],
  'flow-design': ['sequence-', 'state-', 'flow-design-reasoning.md'],
  'ddd-structure': ['ddd-structure.md', 'class-', 'ddd-structure-reasoning.md'],
  'integration-design': ['integration-', 'asyncapi.yaml', 'integration-design-reasoning.md'],
  'config-design': ['config-catalog.yaml', 'config-matrix.md', 'config-design-reasoning.md'],
  'test-design': ['test-inputs.md', 'coverage-map.json', 'test-design-reasoning.md'],
  'ops-readiness': ['slo.yaml', 'observability-spec.yaml', 'deployment-runbook.md', 'ops-readiness-reasoning.md'],
  'design-assembler': ['detailed-design.md', 'traceability.json', 'review-checklist.md', 'design-assembler-reasoning.md'],
  validator: [],
};

type NodeStatus = 'idle' | 'running' | 'success' | 'failed';
type StreamStatus = 'idle' | 'connecting' | 'connected' | 'error';

export function ProjectDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [versions, setVersions] = useState<string[]>([]);
  const [requirement, setRequirement] = useState('');

  const [loading, setLoading] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');

  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeStatus>>({});
  const [nodeLogs, setNodeLogs] = useState<Record<string, string[]>>({});
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  const [isVersionsLoading, setIsVersionsLoading] = useState(false);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [uiError, setUiError] = useState<string | null>(null);

  const terminalContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (id) void loadVersions();
  }, [id]);

  useEffect(() => {
    if (terminalContainerRef.current) {
      terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight;
    }
  }, [nodeLogs, selectedNode]);

  useEffect(() => {
    if (!currentJobId) return;

    const eventSource = new EventSource(api.getJobStatusSseUrl(currentJobId));
    setStreamStatus('connecting');

    setNodeStatuses({
      planner: 'running',
      'architecture-mapping': 'idle',
      'api-design': 'idle',
      'data-design': 'idle',
      'flow-design': 'idle',
      'ddd-structure': 'idle',
      'integration-design': 'idle',
      'config-design': 'idle',
      'test-design': 'idle',
      'ops-readiness': 'idle',
      'design-assembler': 'idle',
      validator: 'idle',
    });
    setSelectedNode('planner');
    setNodeLogs({});

    const updateLog = (node: string, msg: string) => {
      setNodeLogs((prev) => ({ ...prev, [node]: [...(prev[node] || []), msg] }));
    };

    const updateStatus = (node: string, status: NodeStatus) => {
      setNodeStatuses((prev) => ({ ...prev, [node]: status }));
    };

    eventSource.onopen = () => {
      setStreamStatus('connected');
      setUiError(null);
    };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'log') {
        const msg = data.message;
        let targetNode = 'system';

        if (msg.includes('阶段 1: LLM 意图识别')) {
          targetNode = 'planner';
          updateStatus('planner', 'running');
        } else if (msg.includes('意图识别与参数抽取') || msg.includes('正在连接大模型') || msg.includes('解析成功')) {
          targetNode = 'planner';
          if (msg.includes('解析成功')) updateStatus('planner', 'success');
        } else if (msg.includes('阶段 2: 根据 LLM 决策进行动态路由执行')) {
          updateStatus('planner', 'success');
        } else if (msg.includes('阶段 3: 调度 Design Assembler')) {
          updateStatus('design-assembler', 'running');
          targetNode = 'design-assembler';
        } else if (msg.includes('阶段 4: 触发 CI 质量门禁校验')) {
          updateStatus('design-assembler', 'success');
          updateStatus('validator', 'running');
          targetNode = 'validator';
        }

        const agentNameMatch = msg.match(/(?:\[SUCCESS\]|\[ERROR\]|\[WARNING\])?\s*\[([a-z-]+)\]/);

        if (agentNameMatch && agentNameMatch[1]) {
          const agentName = agentNameMatch[1];
          if (AGENT_MAPPING[agentName]) {
            targetNode = agentName;
            if (msg.includes('开始执行') || msg.includes('正在读取')) {
              updateStatus(agentName, 'running');
            } else if (msg.includes('[SUCCESS]')) {
              updateStatus(agentName, 'success');
            } else if (msg.includes('[ERROR]')) {
              updateStatus(agentName, 'failed');
            }
          }
        }

        if (targetNode === 'system' && selectedNode) targetNode = selectedNode;
        updateLog(targetNode, msg);
      } else if (data.type === 'status') {
        if (data.status === 'success' || data.status === 'failed') {
          setLoading(false);
          setStreamStatus('idle');
          updateStatus('validator', data.status === 'success' ? 'success' : 'failed');
          if (data.status === 'failed') setUiError(t('common.error'));
          eventSource.close();
          void loadVersions();
        }
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      setLoading(false);
      setStreamStatus('error');
      setUiError(t('common.error'));
    };

    return () => eventSource.close();
  }, [currentJobId, selectedNode, t]);

  const loadVersions = async () => {
    if (!id) return;
    setIsVersionsLoading(true);
    setUiError(null);
    try {
      const res = await api.getProjectVersions(id);
      setVersions(res);
      if (res.length > 0 && !selectedVersion) {
        await handleSelectVersion(res[0]);
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
    return `v${d.getFullYear()}${pad(d.getMonth()+1, 2)}${pad(d.getDate(), 2)}${pad(d.getHours(), 2)}${pad(d.getMinutes(), 2)}${pad(d.getSeconds(), 2)}${pad(d.getMilliseconds(), 3)}`;
  };

  const handleRun = async () => {
    if (!id || !requirement.trim()) return;
    setLoading(true);
    setUiError(null);
    setArtifacts({});
    setSelectedFile(null);
    try {
      const timestampVersion = generateVersionId();
      const res = await api.runOrchestrator(id, timestampVersion, requirement);
      setCurrentJobId(res.job_id);
      setRequirement('');
      setSelectedVersion(timestampVersion);
    } catch {
      setLoading(false);
      setUiError(t('common.error'));
    }
  };

  const handleSelectVersion = async (version: string) => {
    if (!id) return;
    setSelectedVersion(version);
    setSelectedFile(null);
    setIsArtifactsLoading(true);
    setUiError(null);
    
    setNodeStatuses({
      planner: 'idle',
      'architecture-mapping': 'idle', 'api-design': 'idle', 'data-design': 'idle',
      'flow-design': 'idle', 'ddd-structure': 'idle', 'integration-design': 'idle',
      'config-design': 'idle', 'test-design': 'idle', 'ops-readiness': 'idle',
      'design-assembler': 'idle', validator: 'idle',
    });
    setNodeLogs({});

    try {
      const data = await api.getProjectArtifacts(id, version);
      setArtifacts(data);
      
      try {
        const logData = await api.getVersionLogs(id, version);
        if (logData && logData.logs) {
           rebuildHistoryState(logData.logs);
        }
      } catch (logErr) {
        console.warn("Could not load historical logs for this version.", logErr);
      }
      
    } catch {
      setArtifacts({});
      setUiError(t('common.loadError'));
    } finally {
      setIsArtifactsLoading(false);
    }
  };

  const rebuildHistoryState = (historyLogs: string[]) => {
      let currentStatuses: Record<string, NodeStatus> = {};
      let currentLogs: Record<string, string[]> = {};
      
      historyLogs.forEach(msg => {
        let targetNode = 'system';

        if (msg.includes('阶段 1: LLM 意图识别')) { targetNode = 'planner'; currentStatuses['planner'] = 'running'; }
        else if (msg.includes('意图识别与参数抽取') || msg.includes('正在连接大模型')) { targetNode = 'planner'; }
        else if (msg.includes('阶段 2: 根据 LLM 决策进行动态路由执行')) { currentStatuses['planner'] = 'success'; }
        else if (msg.includes('阶段 3: 调度 Design Assembler')) { currentStatuses['design-assembler'] = 'running'; targetNode = 'design-assembler'; }
        else if (msg.includes('阶段 4: 触发 CI 质量门禁校验')) { currentStatuses['design-assembler'] = 'success'; currentStatuses['validator'] = 'running'; targetNode = 'validator'; }
        else if (msg.includes('[VALIDATE')) { targetNode = 'validator'; }
        else if (msg.includes('全流程闭环！') || msg.includes('[SUCCESS] All M2 Gates Passed!')) { currentStatuses['validator'] = 'success'; }
        else if (msg.includes('验证失败')) { currentStatuses['validator'] = 'failed'; }
        else {
            const match = msg.match(/^\[([a-z-]+)\]/);
            if (match && match[1] && AGENT_MAPPING[match[1]]) {
                targetNode = match[1];
                if (msg.includes('开始执行') || msg.includes('正在读取') || msg.includes('[LLM Reasoning]')) {
                    currentStatuses[targetNode] = 'running';
                }
            } else {
                const statusMatch = msg.match(/^\[(SUCCESS|ERROR|WARNING)\]\s*\[([a-z-]+)\]/);
                if (statusMatch && statusMatch[2] && AGENT_MAPPING[statusMatch[2]]) {
                    targetNode = statusMatch[2];
                    if (statusMatch[1] === 'SUCCESS') currentStatuses[targetNode] = 'success';
                    if (statusMatch[1] === 'ERROR') currentStatuses[targetNode] = 'failed';
                }
            }
        }
        
        if (!currentLogs[targetNode]) currentLogs[targetNode] = [];
        currentLogs[targetNode].push(msg);
      });
      
      setNodeStatuses(prev => ({...prev, ...currentStatuses}));
      setNodeLogs(currentLogs);
  };

  const getFileIcon = (filename: string) => {
    if (filename.endsWith('.sql')) return <Database size={16} className="text-purple-500" />;
    if (filename.endsWith('.yaml') || filename.endsWith('.json')) return <FileJson size={16} className="text-yellow-500" />;
    return <FileText size={16} className="text-blue-500" />;
  };

  const filteredArtifacts = useMemo(() => {
    if (!selectedNode || !AGENT_MAPPING[selectedNode]) {
      return Object.keys(artifacts).filter(f => !f.endsWith('-reasoning.md'));
    }
    const patterns = AGENT_MAPPING[selectedNode];
    return Object.keys(artifacts).filter((filename) =>
      !filename.endsWith('-reasoning.md') && patterns.some(
        (pattern) => filename.startsWith(pattern) || filename === pattern || (pattern === 'requirements.json' && filename.includes('requirements')),
      ),
    );
  }, [selectedNode, artifacts]);

  const renderNode = (nodeId: string, label: string, isSmall = false) => {
    const status = nodeStatuses[nodeId] || 'idle';
    const isSelected = selectedNode === nodeId;

    let icon = <Circle size={isSmall ? 12 : 14} className="text-gray-300" />;
    let borderColor = 'border-gray-200';
    let bgColor = 'bg-white';

    if (status === 'running') {
      icon = <LucideLoader size={isSmall ? 12 : 14} className="text-blue-500 animate-spin" />;
      borderColor = 'border-blue-300';
      bgColor = 'bg-indigo-50';
    } else if (status === 'success') {
      icon = <CheckCircle size={isSmall ? 12 : 14} className="text-emerald-500" />;
      borderColor = 'border-emerald-200';
      bgColor = 'bg-emerald-50/50';
    } else if (status === 'failed') {
      icon = <XCircle size={isSmall ? 12 : 14} className="text-rose-500" />;
      borderColor = 'border-rose-200';
      bgColor = 'bg-rose-50/50';
    }

    if (isSelected) {
      borderColor = 'border-indigo-500 shadow-[0_0_0_2px_rgba(99,102,241,0.2)]';
      bgColor = status === 'idle' ? 'bg-indigo-50/30' : bgColor;
    }

    return (
      <button
        type="button"
        onClick={() => {
          setSelectedNode(nodeId);
          setSelectedFile(null);
        }}
        className={`flex items-center gap-2 px-3 py-2 rounded-xl border transition-all duration-200 cursor-pointer ${borderColor} ${bgColor} hover:shadow-sm group relative overflow-hidden`}
      >
        <div className="relative z-10">{icon}</div>
        <span className={`relative z-10 text-[11px] font-semibold truncate ${isSelected ? 'text-indigo-900' : 'text-gray-600'} group-hover:text-indigo-600`}>
          {t(`projectDetail.${nodeId}`, { defaultValue: label })}
        </span>
      </button>
    );
  };

  return (
    <div className="max-w-[1600px] mx-auto p-4 sm:p-6 bg-gray-50/30 min-h-screen">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link to="/" className="p-2 bg-white rounded-xl shadow-sm border border-gray-200 text-gray-400 hover:text-indigo-600 hover:border-indigo-200 transition-all" aria-label={t('common.back')}>
            <ArrowLeft size={20} />
          </Link>
          <div>
            <div className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-0.5">{t('projectDetail.workspace')}</div>
            <h1 className="text-xl font-black text-gray-900 flex items-center gap-2 uppercase">
              {id}
              <span className="px-2 py-0.5 bg-gray-200 rounded text-[10px] text-gray-500 font-mono">{selectedVersion || t('projectDetail.noVersion')}</span>
            </h1>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-6 text-xs">
          <LanguageSwitcher />
          <div className="flex flex-col items-end">
             <span className="text-gray-400 font-medium">{t('projectDetail.pipelineStatus')}</span>
             <span className={`font-bold ${loading ? 'text-indigo-600' : 'text-emerald-600'}`}>{loading ? t('projectDetail.activeGeneration') : t('projectDetail.readyIdle')}</span>
          </div>
          <div className="h-8 w-px bg-gray-200" />
          <div className="flex flex-col items-end">
             <span className="text-gray-400 font-medium">{t('projectDetail.streamLink')}</span>
             <span className={`font-bold ${streamStatus === 'connected' ? 'text-emerald-500' : 'text-gray-400'}`}>{streamStatus.toUpperCase()}</span>
          </div>
        </div>
      </div>

      {uiError && (
        <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 flex items-center justify-between shadow-sm animate-in slide-in-from-top-2">
          <div className="flex items-center gap-3">
            <XCircle size={18} />
            <span className="font-medium">{uiError}</span>
          </div>
          <button onClick={loadVersions} className="px-4 py-1.5 bg-white border border-rose-200 rounded-lg hover:bg-rose-100 transition-colors font-bold text-xs uppercase">{t('common.retry')}</button>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-8 items-start">
        {/* Left Control Panel */}
        <div className="xl:col-span-3 flex flex-col gap-6">
          <div className="bg-white p-5 rounded-2xl shadow-sm border border-gray-200 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-3 opacity-10">
              <Activity size={48} className="text-indigo-600" />
            </div>
            <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">{t('projectDetail.newIteration')}</h2>
            <textarea
              className="w-full h-32 p-4 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:bg-white outline-none resize-none text-sm transition-all shadow-inner font-medium placeholder:text-gray-300"
              placeholder={t('projectDetail.requirementsPlaceholder')}
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
            />
            <button
              onClick={handleRun}
              disabled={loading || !requirement.trim()}
              className="mt-4 w-full bg-indigo-600 text-white px-4 py-3 rounded-xl font-bold hover:bg-indigo-700 disabled:opacity-40 shadow-lg shadow-indigo-200 transition-all flex items-center justify-center gap-2 group active:scale-95"
            >
              <Play size={16} className="group-hover:translate-x-0.5 transition-transform" />
              {t('projectDetail.generateBtn')}
            </button>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden flex flex-col max-h-[400px]">
             <div className="p-5 border-b border-gray-100 flex items-center justify-between">
                <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('projectDetail.versionHistory')}</h2>
                <button onClick={loadVersions} className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors">
                  <RefreshCw size={14} className={isVersionsLoading ? 'animate-spin' : ''} />
                </button>
             </div>
             <div className="overflow-y-auto p-2 space-y-1">
               {versions.map((v) => (
                  <button
                    key={v}
                    onClick={() => handleSelectVersion(v)}
                    className={`w-full flex items-center justify-between p-3 rounded-xl transition-all text-xs text-left ${selectedVersion === v ? 'bg-indigo-50 text-indigo-700 font-bold border-l-4 border-indigo-600' : 'hover:bg-gray-50 text-gray-500 font-medium'}`}
                  >
                    <span className="truncate">{v}</span>
                    {selectedVersion === v && <div className="h-1.5 w-1.5 rounded-full bg-indigo-600 shadow-[0_0_8px_rgba(79,70,229,0.8)]" />}
                  </button>
                ))}
             </div>
          </div>
        </div>

        {/* Right Content Area */}
        <div className="xl:col-span-9 flex flex-col gap-6">
          {/* Compact Pipeline Mini-Map */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
               <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('projectDetail.pipelineTitle')}</h2>
               <div className="flex gap-4">
                  <div className="flex items-center gap-1.5 text-[10px] font-bold text-gray-400 uppercase">
                    <div className="h-2 w-2 rounded-full bg-gray-200" /> {t('projectDetail.idle')}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] font-bold text-indigo-500 uppercase">
                    <div className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" /> {t('projectDetail.running')}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-500 uppercase">
                    <div className="h-2 w-2 rounded-full bg-emerald-500" /> {t('projectDetail.success')}
                  </div>
               </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 relative">
              {renderNode('planner', 'Planner')}
              
              <div className="h-4 w-px bg-gray-200 mx-1 hidden md:block" />
              
              <div className="flex-1 min-w-[300px] bg-gray-50/50 p-3 rounded-2xl border border-dashed border-gray-200 flex flex-wrap gap-2">
                {renderNode('architecture-mapping', 'Architecture', true)}
                {renderNode('api-design', 'API Contract', true)}
                {renderNode('data-design', 'Data Model', true)}
                {renderNode('flow-design', 'Flow & State', true)}
                {renderNode('ddd-structure', 'DDD Objects', true)}
                {renderNode('integration-design', 'Integrations', true)}
                {renderNode('test-design', 'Test Matrix', true)}
                {renderNode('ops-readiness', 'Ops Runbook', true)}
              </div>

              <div className="h-4 w-px bg-gray-200 mx-1 hidden md:block" />

              {renderNode('design-assembler', 'Assembler')}
              <div className="w-4 h-px bg-gray-200 hidden md:block" />
              {renderNode('validator', 'Gatekeeper')}
            </div>
          </div>

          {selectedNode && (
            <div className="flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
              
              {/* Dual Log View */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {/* Standard Execution Terminal */}
                <div className="bg-gray-900 rounded-2xl shadow-xl border border-gray-800 flex flex-col overflow-hidden h-72">
                  <div className="bg-gray-950 px-4 py-3 border-b border-gray-800 flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1.5">
                        <div className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                        <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                      </div>
                      <span className="text-gray-500 text-[10px] font-black uppercase tracking-widest ml-4">{t('projectDetail.executionStream')}</span>
                    </div>
                    <span className="text-indigo-400 text-[10px] font-mono">{selectedNode}</span>
                  </div>
                  <div 
                    ref={terminalContainerRef}
                    className="p-5 flex-1 overflow-y-auto font-mono text-[11px] space-y-2 leading-relaxed custom-scrollbar"
                  >
                    {nodeLogs[selectedNode] ? (
                      nodeLogs[selectedNode].filter(log => !log.includes('[LLM Reasoning]')).map((log, i) => {
                        let textStyle = "text-gray-300";
                        if (log.includes('❌') || log.includes('[ERROR]')) textStyle = "text-rose-400 font-bold";
                        if (log.includes('✅') || log.includes('[SUCCESS]')) textStyle = "text-emerald-400";
                        if (log.includes('[WARNING]')) textStyle = "text-amber-400";

                        return (
                          <div key={i} className={`flex gap-3 ${textStyle}`}>
                            <span className="text-gray-600 opacity-30 select-none">{(i+1).toString().padStart(3, '0')}</span>
                            <span className="break-all">{log}</span>
                          </div>
                        );
                      })
                    ) : (
                      <div className="text-gray-600 italic flex h-full items-center justify-center">No logs...</div>
                    )}
                  </div>
                </div>

                {/* Dedicated LLM Reasoning Panel */}
                <div className="bg-white rounded-2xl shadow-xl border border-indigo-100 flex flex-col overflow-hidden h-72">
                  <div className="bg-indigo-50/50 px-4 py-3 border-b border-indigo-100 flex justify-between items-center">
                    <span className="text-indigo-900 text-[10px] font-black uppercase tracking-widest flex items-center gap-2">
                      <Activity size={12} className="text-indigo-600" />
                      {t('projectDetail.reasoningChain')}
                    </span>
                  </div>
                  <div className="p-5 flex-1 overflow-y-auto text-sm text-indigo-950 space-y-4 leading-relaxed bg-[radial-gradient(#e0e7ff_1px,transparent_1px)] [background-size:20px_20px]">
                    {nodeLogs[selectedNode] && nodeLogs[selectedNode].some(log => log.includes('[LLM Reasoning]')) ? (
                      nodeLogs[selectedNode]
                        .filter(log => log.includes('[LLM Reasoning]'))
                        .map((log, i) => {
                          const cleanLog = log.replace(/^\[.*?\]\s*\[LLM Reasoning\]\s*/, '');
                          return (
                            <div key={i} className="flex gap-4 items-start bg-white/80 p-3 rounded-xl border border-indigo-50 shadow-sm backdrop-blur-sm">
                               <div className="mt-1 w-2 h-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(79,70,229,0.5)] flex-shrink-0" />
                               <p className="italic text-xs font-medium text-indigo-800 leading-relaxed">{cleanLog}</p>
                            </div>
                          );
                        })
                    ) : (
                      <div className="text-indigo-200 italic flex h-full items-center justify-center text-xs font-medium">
                        {loading ? t('projectDetail.analyzing') : t('projectDetail.noReasoning')}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Large Artifact Viewer */}
              <div className="bg-white rounded-2xl shadow-xl border border-gray-200 flex flex-col overflow-hidden min-h-[700px]">
                <div className="bg-gray-50/80 px-6 py-4 border-b border-gray-100 flex items-center justify-between backdrop-blur-md">
                  <div className="flex items-center gap-3">
                    <FileText size={18} className="text-indigo-600" />
                    <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">{t('projectDetail.artifactsExplorer')}</span>
                  </div>
                  <div className="px-3 py-1 bg-white border border-gray-200 rounded-full text-[10px] font-bold text-gray-500">
                    {filteredArtifacts.length} {t('projectDetail.assetsGenerated')}
                  </div>
                </div>

                {isArtifactsLoading ? (
                  <div className="flex-1 flex flex-col items-center justify-center gap-4">
                     <LucideLoader size={32} className="text-indigo-500 animate-spin" />
                     <span className="text-sm font-bold text-gray-400 animate-pulse">{t('projectDetail.retrieving')}</span>
                  </div>
                ) : filteredArtifacts.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center p-20 text-center">
                    <div className="max-w-xs flex flex-col items-center gap-4">
                      <div className="p-4 bg-gray-100 rounded-full text-gray-300">
                        <FileJson size={48} />
                      </div>
                      <p className="text-sm font-bold text-gray-400 leading-relaxed uppercase tracking-wide">{t('projectDetail.noAssets')}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
                    <div className="md:w-72 border-b md:border-b-0 md:border-r border-gray-100 p-4 overflow-y-auto bg-gray-50/30">
                      <div className="space-y-1">
                        {filteredArtifacts.map((filename) => (
                          <button
                            key={filename}
                            onClick={() => setSelectedFile(filename)}
                            className={`w-full flex items-center gap-3 p-3 text-xs rounded-xl transition-all ${selectedFile === filename ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-200 font-bold' : 'text-gray-600 hover:bg-gray-200/50 font-medium'}`}
                          >
                            <div className={selectedFile === filename ? 'text-indigo-200' : ''}>
                              {getFileIcon(filename)}
                            </div>
                            <span className="truncate flex-1 text-left">{filename}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="flex-1 p-8 overflow-y-auto bg-white custom-scrollbar" style={{ maxHeight: '900px' }}>
                      {selectedFile ? (
                        selectedFile.endsWith('.md') ? (
                          <div className="prose prose-slate prose-indigo max-w-none prose-headings:font-black prose-headings:uppercase prose-headings:tracking-tight prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-800">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ code: CodeBlock }}>
                              {artifacts[selectedFile]}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <div className="rounded-2xl border border-gray-200 overflow-hidden bg-gray-950 shadow-2xl">
                             <div className="bg-gray-900 px-4 py-2 border-b border-gray-800 flex items-center justify-between">
                                <span className="text-[10px] font-mono text-gray-500 uppercase">{selectedFile}</span>
                                <button onClick={() => navigator.clipboard.writeText(artifacts[selectedFile])} className="text-gray-500 hover:text-white transition-colors"><Copy size={14}/></button>
                             </div>
                             <pre className="text-[13px] font-mono text-gray-300 p-6 overflow-x-auto leading-relaxed">
                                {artifacts[selectedFile]}
                             </pre>
                          </div>
                        )
                      ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center gap-6 opacity-30">
                          <div className="relative">
                             <div className="absolute inset-0 bg-indigo-500 blur-3xl rounded-full opacity-10 animate-pulse" />
                             <FileText size={80} className="relative text-indigo-900" />
                          </div>
                          <span className="text-sm font-black text-indigo-950 uppercase tracking-[0.2em]">{t('projectDetail.selectAsset')}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
