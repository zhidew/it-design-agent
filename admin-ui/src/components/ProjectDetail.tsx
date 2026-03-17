import React, { useEffect, useState, useRef, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api';
import { ArrowLeft, Play, RefreshCw, Activity, Check, X, Upload, FileText, Database, Layers, Book, List, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LanguageSwitcher } from './LanguageSwitcher';
import { TaskKanban } from './TaskKanban';
import type { NodeStatus } from './TaskKanban';
import { ArtifactViewer } from './ArtifactViewer';
import { ToolEventCard } from './ToolEventCard';

const AGENT_MAPPING: Record<string, string[]> = {
  planner: ['requirements.json', 'input-requirements.md', 'original-requirements.md'],
  'architecture-mapping': ['architecture.md', 'module-map.json'],
  'integration-design': ['integration-', 'asyncapi.yaml'],
  'config-design': ['config-catalog.yaml', 'config-matrix.md'],
  'data-design': ['schema.sql', 'er.md', 'migration-plan.md'],
  'flow-design': ['sequence-', 'state-'],
  'api-design': ['api-design.md', 'api-internal.yaml', 'api-public.yaml', 'errors-rfc9457.json'],
  'ddd-structure': ['ddd-structure.md', 'class-'],
  'test-design': ['test-inputs.md', 'coverage-map.json'],
  'ops-readiness': ['slo.yaml', 'observability-spec.yaml', 'deployment-runbook.md'],
  'design-assembler': ['detailed-design.md', 'traceability.json', 'review-checklist.md'],
  validator: [], // validator 使用独立的报告展示逻辑，不走产物清单
};

type StreamStatus = 'idle' | 'connecting' | 'connected' | 'error';
type RunStatus = 'queued' | 'running' | 'waiting_human' | 'success' | 'failed';
type ArtifactStatus = 'created' | 'updated';

interface InputFile {
  type: 'ir' | 'physical' | 'logical' | 'dict' | 'lookup';
  file: File;
}

interface WorkflowTask {
  id: string;
  agent_type: string;
  status: NodeStatus;
}

interface WorkflowState {
  run_id?: string | null;
  task_queue: WorkflowTask[];
  history: string[];
  workflow_phase?: string;
  run_status: RunStatus;
  current_node: string | null;
  last_worker?: string | null;
  can_resume: boolean;
  waiting_reason: string | null;
  pending_interrupt?: {
    node_id: string;
    node_type: string;
    interrupt_id?: string | null;
    question: string;
    context?: Record<string, unknown>;
    resume_target: string;
    interrupt_kind?: 'ask_human' | 'review' | string;
  } | null;
  stale_execution_detected?: boolean;
  updated_at: string;
}

interface VersionStateSummary {
  run_status: RunStatus;
  updated_at?: string;
  current_node?: string | null;
}

interface EventBase {
  event_id: string;
  event_type: string;
  run_id: string;
  timestamp: string;
}

interface NodeStartedEvent extends EventBase {
  event_type: 'node_started';
  node_id: string;
  node_type: string;
}

interface NodeCompletedEvent extends EventBase {
  event_type: 'node_completed';
  node_id: string;
  node_type: string;
  status: 'success' | 'failed' | 'skipped';
}

interface TextDeltaEvent extends EventBase {
  event_type: 'text_delta';
  node_id: string;
  node_type: string;
  stream_name: 'history' | 'stdout' | 'stderr';
  delta: string;
}

interface ArtifactUpdatedEvent extends EventBase {
  event_type: 'artifact_updated';
  node_id: string;
  node_type: string;
  artifact_name: string;
  artifact_status: ArtifactStatus;
}

interface ToolEvent extends EventBase {
  event_type: 'tool_event';
  node_id: string;
  node_type: string;
  tool_name: string;
  status: 'success' | 'error';
  error_code: string;
  duration_ms: number;
  tool_input: Record<string, unknown>;
  tool_output: Record<string, unknown>;
}

interface WaitingHumanEvent extends EventBase {
  event_type: 'waiting_human';
  node_id: string;
  node_type: string;
  interrupt_id?: string | null;
  question: string;
  context?: Record<string, unknown>;
  resume_target: string;
}

interface InterruptOption {
  value: string;
  label: string;
  description?: string;
}

interface RunCompletedEvent extends EventBase {
  event_type: 'run_completed';
  status: 'success';
}

interface RunFailedEvent extends EventBase {
  event_type: 'run_failed';
  status: 'failed';
  error_message: string;
}

type OrchestratorEvent =
  | NodeStartedEvent
  | NodeCompletedEvent
  | TextDeltaEvent
  | ArtifactUpdatedEvent
  | ToolEvent
  | WaitingHumanEvent
  | RunCompletedEvent
  | RunFailedEvent;

type ExecutionLogEntry =
  | { kind: 'text'; id: string; text: string; tone: 'default' | 'error' }
  | { kind: 'tool'; id: string; event: ToolEvent };

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
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null);
  const [runEvents, setRunEvents] = useState<OrchestratorEvent[]>([]);
  const [versionStateMap, setVersionStateMap] = useState<Record<string, VersionStateSummary>>({});

  const [isVersionsLoading, setIsVersionsLoading] = useState(false);
  const [isArtifactsLoading, setIsArtifactsLoading] = useState(false);
  const [uiError, setUiError] = useState<string | null>(null);

  const [isLogsOpen, setIsLogsOpen] = useState(true);
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [selectedInterruptOption, setSelectedInterruptOption] = useState<string>('');
  const [resumeActionLoading, setResumeActionLoading] = useState<'approve' | 'revise' | 'answer' | null>(null);
  const [deletingVersion, setDeletingVersion] = useState<string | null>(null);
  const [retryingNode, setRetryingNode] = useState<string | null>(null);
  const [continuingWorkflow, setContinuingWorkflow] = useState(false);

  const pollInterval = useRef<NodeJS.Timeout | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const latestFetchedStateAtRef = useRef<number>(0);

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

  const updateTaskStatus = (tasks: WorkflowTask[], nodeType: string, status: NodeStatus): WorkflowTask[] => (
    tasks.map((task) => task.agent_type === nodeType ? { ...task, status } : task)
  );

  const appendEvent = (event: OrchestratorEvent) => {
    if (seenEventIdsRef.current.has(event.event_id)) {
      return;
    }
    seenEventIdsRef.current.add(event.event_id);
    setRunEvents((prev) => [...prev, event]);
  };

  const syncVersionState = (version: string, summary: VersionStateSummary) => {
    setVersionStateMap((prev) => ({
      ...prev,
      [version]: {
        ...prev[version],
        ...summary,
      },
    }));
  };

  const applyEventToState = (event: OrchestratorEvent) => {
    setCurrentRunId(event.run_id);
    setStreamStatus('connected');
    if (selectedVersion) {
      switch (event.event_type) {
        case 'node_started':
          syncVersionState(selectedVersion, {
            run_status: 'running',
            current_node: event.node_type,
            updated_at: event.timestamp,
          });
          break;
        case 'waiting_human':
          syncVersionState(selectedVersion, {
            run_status: 'waiting_human',
            current_node: event.node_type,
            updated_at: event.timestamp,
          });
          break;
        case 'run_completed':
          syncVersionState(selectedVersion, {
            run_status: 'success',
            current_node: null,
            updated_at: event.timestamp,
          });
          break;
        case 'run_failed':
          syncVersionState(selectedVersion, {
            run_status: 'failed',
            current_node: null,
            updated_at: event.timestamp,
          });
          break;
        default:
          break;
      }
    }

    setWorkflowState((prev) => {
      const baseState: WorkflowState = prev ?? {
        run_id: event.run_id,
        task_queue: [],
        history: [],
        workflow_phase: undefined,
        run_status: 'running',
        current_node: null,
        can_resume: false,
        waiting_reason: null,
        pending_interrupt: null,
        updated_at: event.timestamp,
      };

      switch (event.event_type) {
        case 'node_started':
          return {
            ...baseState,
            run_id: event.run_id,
            run_status: 'running',
            current_node: event.node_type,
            can_resume: false,
            waiting_reason: null,
            updated_at: event.timestamp,
            task_queue: updateTaskStatus(baseState.task_queue, event.node_type, 'running'),
          };
        case 'node_completed':
          return {
            ...baseState,
            run_id: event.run_id,
            updated_at: event.timestamp,
            task_queue: updateTaskStatus(baseState.task_queue, event.node_type, event.status),
          };
        case 'text_delta':
          return event.stream_name === 'history'
            ? {
                ...baseState,
                updated_at: event.timestamp,
                history: [...baseState.history, event.delta],
              }
            : baseState;
        case 'waiting_human':
          return {
            ...baseState,
            run_id: event.run_id,
            run_status: 'waiting_human',
            current_node: event.node_type,
            can_resume: true,
            waiting_reason: event.question,
            pending_interrupt: {
              node_id: event.node_id,
              node_type: event.node_type,
              interrupt_id: event.interrupt_id,
              question: event.question,
              context: event.context,
              resume_target: event.resume_target,
            },
            updated_at: event.timestamp,
          };
        case 'run_completed':
          return {
            ...baseState,
            run_id: event.run_id,
            run_status: 'success',
            current_node: null,
            can_resume: false,
            waiting_reason: null,
            pending_interrupt: null,
            updated_at: event.timestamp,
          };
        case 'run_failed':
          return {
            ...baseState,
            run_id: event.run_id,
            run_status: 'failed',
            current_node: null,
            can_resume: true,
            waiting_reason: event.error_message,
            pending_interrupt: null,
            updated_at: event.timestamp,
          };
        case 'tool_event':
          return {
            ...baseState,
            run_id: event.run_id,
            updated_at: event.timestamp,
          };
        default:
          return baseState;
      }
    });

    switch (event.event_type) {
      case 'node_started':
        setNodeStatuses((prev) => ({ ...prev, [event.node_type]: 'running' }));
        if (selectedVersion) {
          void fetchState();
        }
        break;
      case 'node_completed':
        setNodeStatuses((prev) => ({ ...prev, [event.node_type]: event.status }));
        if (selectedVersion) {
          void fetchState();
        }
        break;
      case 'artifact_updated':
        if (selectedVersion) {
          void loadArtifacts(selectedVersion);
        }
        break;
      case 'waiting_human':
        if (selectedVersion) {
          void fetchState();
        }
        break;
      case 'run_completed':
        if (selectedVersion) {
          void fetchState();
        }
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        break;
      case 'run_failed':
        if (selectedVersion) {
          void fetchState();
        }
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        break;
      case 'tool_event':
        break;
      default:
        break;
    }
  };

  useEffect(() => {
    if (!currentRunId || !selectedVersion) {
      return;
    }

    eventSourceRef.current?.close();
    const source = new EventSource(api.getJobStatusSseUrl(currentRunId));
    eventSourceRef.current = source;
    setStreamStatus('connecting');

    const handleEvent = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as OrchestratorEvent;
      const eventTimestamp = Date.parse(event.timestamp || '') || 0;
      if (latestFetchedStateAtRef.current > 0 && eventTimestamp > 0 && eventTimestamp <= latestFetchedStateAtRef.current) {
        return;
      }
      appendEvent(event);
      applyEventToState(event);
    };

    const eventTypes: OrchestratorEvent['event_type'][] = [
      'node_started',
      'node_completed',
      'text_delta',
      'artifact_updated',
      'tool_event',
      'waiting_human',
      'run_completed',
      'run_failed',
    ];

    eventTypes.forEach((eventType) => source.addEventListener(eventType, handleEvent as EventListener));
    source.onerror = () => {
      setStreamStatus('error');
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };

    return () => {
      eventTypes.forEach((eventType) => source.removeEventListener(eventType, handleEvent as EventListener));
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };
  }, [currentRunId, selectedVersion]);

  const fetchState = async () => {
    if (!id || !selectedVersion) return;
    try {
      const state = await api.getProjectState(id, selectedVersion) as WorkflowState;
      setWorkflowState(state);
      latestFetchedStateAtRef.current = Date.parse(state.updated_at || '') || 0;
      syncVersionState(selectedVersion, {
        run_status: state.run_status,
        current_node: state.current_node,
        updated_at: state.updated_at,
      });
      if (state.run_id) {
        setCurrentRunId(state.run_id);
      }
      
      const newStatuses: Record<string, NodeStatus> = {};
      if (state.task_queue) {
        state.task_queue.forEach((t) => {
          newStatuses[t.agent_type] = t.status;
        });
      }
      setNodeStatuses(newStatuses);
      setStreamStatus(state.run_status === 'running' ? 'connected' : 'idle');

      if (state.run_status !== 'queued') {
        void loadArtifacts(selectedVersion);
      }
      
    } catch (err: any) {
      if (err.response?.status === 404) {
        setWorkflowState(null);
      }
      setStreamStatus('error');
    }
  };

  const loadVersions = async () => {
    if (!id) return;
    setIsVersionsLoading(true);
    try {
      const res = await api.getProjectVersions(id);
      setVersions(res);
      if (res.length > 0) {
        const settled = await Promise.allSettled(
          res.map(async (version) => {
            const state = await api.getProjectState(id, version) as WorkflowState;
            return [version, {
              run_status: state.run_status,
              current_node: state.current_node,
              updated_at: state.updated_at,
            }] as const;
          }),
        );

        const nextStateMap: Record<string, VersionStateSummary> = {};
        settled.forEach((result) => {
          if (result.status === 'fulfilled') {
            const [version, summary] = result.value;
            nextStateMap[version] = summary;
          }
        });
        setVersionStateMap(nextStateMap);
      } else {
        setVersionStateMap({});
      }
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
      setCurrentRunId(null);
      setNodeStatuses({});
      setArtifacts({});
      setSelectedFile(null);
      setWorkflowState(null);
      setRunEvents([]);
      latestFetchedStateAtRef.current = 0;
      setReviewFeedback('');
      setSelectedInterruptOption('');
      seenEventIdsRef.current.clear();
      setSelectedNode('planner');
      setStreamStatus('connecting');

      if (inputFiles.length > 0) {
        await api.uploadBaselineFiles(id, timestampVersion, inputFiles.map(f => f.file));
      }

      const run = await api.runOrchestrator(id, timestampVersion, requirement);
      setCurrentRunId(run.job_id);
      
      setRequirement('');
      setInputFiles([]);
      setSelectedInterruptOption('');
      void loadArtifacts(timestampVersion);
      void loadVersions();
    } catch {
      setUiError(t('common.error'));
      setLoading(false);
    } finally {
      setLoading(false);
    }
  };

  const handleResumeExecution = async (action: 'approve' | 'revise' | 'answer') => {
    if (!id || !selectedVersion) return;
    const pendingInterrupt = workflowState?.pending_interrupt;
    const effectiveAction = action === 'approve' && pendingInterrupt?.interrupt_kind === 'ask_human' ? 'answer' : action;
    setResumeActionLoading(action);
    try {
      setStreamStatus('connecting');
      await api.resumeWorkflow(id, selectedVersion, {
        action: effectiveAction,
        node_id: pendingInterrupt?.node_id,
        interrupt_id: pendingInterrupt?.interrupt_id ?? undefined,
        selected_option: effectiveAction === 'answer' && selectedInterruptOption ? selectedInterruptOption : undefined,
        answer: effectiveAction === 'answer' ? reviewFeedback.trim() : undefined,
        feedback: effectiveAction === 'revise' ? reviewFeedback.trim() : undefined,
      });
      if (effectiveAction === 'approve' || effectiveAction === 'answer') {
        setReviewFeedback('');
        setSelectedInterruptOption('');
      }
      void fetchState();
    } catch {
      setUiError(
        effectiveAction === 'approve'
          ? 'Failed to approve workflow'
          : effectiveAction === 'answer'
            ? 'Failed to submit human answer'
            : 'Failed to resubmit planner feedback'
      );
      setStreamStatus('error');
    } finally {
      setResumeActionLoading(null);
    }
  };

  const handleSelectVersion = (version: string) => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setSelectedVersion(version);
    setCurrentRunId(null);
    setRunEvents([]);
    setNodeStatuses({});
    setWorkflowState(null);
    latestFetchedStateAtRef.current = 0;
    setStreamStatus('idle');
    setReviewFeedback('');
    setSelectedInterruptOption('');
    seenEventIdsRef.current.clear();
    setSelectedFile(null);
    setSelectedNode('planner');
    void loadArtifacts(version);
  };

  const handleDeleteVersion = async (version: string) => {
    if (!id || deletingVersion) return;
    const confirmed = window.confirm(`Delete version ${version}? This will remove its files and persisted workflow state.`);
    if (!confirmed) return;

    setDeletingVersion(version);
    try {
      await api.deleteProjectVersion(id, version);
      setVersions((prev) => prev.filter((item) => item !== version));
      setVersionStateMap((prev) => {
        const next = { ...prev };
        delete next[version];
        return next;
      });

      if (selectedVersion === version) {
        const remainingVersions = versions.filter((item) => item !== version);
        if (remainingVersions.length > 0) {
          handleSelectVersion(remainingVersions[0]);
        } else {
          eventSourceRef.current?.close();
          eventSourceRef.current = null;
          setSelectedVersion(null);
          setCurrentRunId(null);
          setRunEvents([]);
          setNodeStatuses({});
          setWorkflowState(null);
          latestFetchedStateAtRef.current = 0;
          setArtifacts({});
          setSelectedFile(null);
          setSelectedNode('planner');
          setStreamStatus('idle');
        }
      }
    } catch (err: any) {
      setUiError(err?.response?.data?.detail || 'Failed to delete version');
    } finally {
      setDeletingVersion(null);
    }
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

  const executionEntries = useMemo<ExecutionLogEntry[]>(() => {
    if (runEvents.length > 0) {
      return runEvents.map((event) => {
        switch (event.event_type) {
          case 'node_started':
            return { kind: 'text', id: event.event_id, text: `[EVENT] ${event.node_type} started`, tone: 'default' as const };
          case 'node_completed':
            return { kind: 'text', id: event.event_id, text: `[EVENT] ${event.node_type} completed with status ${event.status}`, tone: event.status === 'failed' ? 'error' as const : 'default' as const };
          case 'text_delta':
            return { kind: 'text', id: event.event_id, text: event.delta, tone: event.delta.includes('[ERROR]') ? 'error' as const : 'default' as const };
          case 'artifact_updated':
            return { kind: 'text', id: event.event_id, text: `[EVENT] ${event.node_type} ${event.artifact_status} artifact ${event.artifact_name}`, tone: 'default' as const };
          case 'tool_event':
            return { kind: 'tool', id: event.event_id, event };
          case 'waiting_human':
            return { kind: 'text', id: event.event_id, text: `[EVENT] Waiting for human input at ${event.node_type}: ${event.question}`, tone: 'default' as const };
          case 'run_completed':
            return { kind: 'text', id: event.event_id, text: '[EVENT] Run completed successfully', tone: 'default' as const };
          case 'run_failed':
            return { kind: 'text', id: event.event_id, text: `[EVENT] Run failed: ${event.error_message}`, tone: 'error' as const };
          default:
            return null;
        }
      }).filter((entry): entry is ExecutionLogEntry => entry !== null);
    }

    if (!workflowState?.history) return [];
    return workflowState.history.map((log, idx) => ({
      kind: 'text' as const,
      id: `history-${idx}`,
      text: log,
      tone: log.includes('[ERROR]') ? 'error' as const : 'default' as const,
    }));
  }, [runEvents, workflowState?.history]);

  const reasoningLogs = useMemo(() => {
    if (!selectedNode) return [];

    if (selectedNode !== 'planner' && selectedNode !== 'validator') {
      const reasoningFile = `${selectedNode}-reasoning.md`;
      if (artifacts[reasoningFile]) {
        return [artifacts[reasoningFile]];
      }
      return [];
    }

    if (selectedNode === 'planner' && artifacts['planner-reasoning.md']) {
      return [artifacts['planner-reasoning.md']];
    }

    if (selectedNode === 'validator' && artifacts['validator.log']) {
      return [artifacts['validator.log']];
    }

    return [];
  }, [selectedNode, artifacts]);

  // validator 节点使用独立的报告展示，不显示设计产物清单
  const isValidatorNode = selectedNode === 'validator';

  const effectiveNodeStatuses = useMemo<Record<string, NodeStatus>>(() => {
    const serverStatuses: Record<string, NodeStatus> = {};
    (workflowState?.task_queue || []).forEach((task) => {
      serverStatuses[task.agent_type] = task.status;
    });

    for (const [nodeType, status] of Object.entries(nodeStatuses)) {
      if (!(nodeType in serverStatuses)) {
        serverStatuses[nodeType] = status;
      }
    }

    return serverStatuses;
  }, [workflowState?.task_queue, nodeStatuses]);

  const selectedTask = useMemo(
    () => workflowState?.task_queue?.find((task) => task.agent_type === selectedNode) ?? null,
    [workflowState?.task_queue, selectedNode],
  );
  const pendingInterrupt = workflowState?.pending_interrupt ?? null;
  const isClarificationInterrupt = pendingInterrupt?.interrupt_kind === 'ask_human';
  const interruptOptions = useMemo(() => {
    const rawOptions = pendingInterrupt?.context?.options;
    if (!Array.isArray(rawOptions)) {
      return [];
    }
    return rawOptions
      .map((option): InterruptOption | null => {
        if (!option || typeof option !== 'object') {
          return null;
        }
        const value = String((option as Record<string, unknown>).value ?? '').trim();
        if (!value) {
          return null;
        }
        const label = String((option as Record<string, unknown>).label ?? value).trim() || value;
        const description = String((option as Record<string, unknown>).description ?? '').trim();
        return { value, label, description };
      })
      .filter((option): option is InterruptOption => option !== null);
  }, [pendingInterrupt]);
  const hasPendingTodoTasks = useMemo(
    () => Boolean(workflowState?.task_queue?.some((task) => task.status === 'todo')),
    [workflowState?.task_queue],
  );

  useEffect(() => {
    if (interruptOptions.length === 0) {
      if (selectedInterruptOption) {
        setSelectedInterruptOption('');
      }
      return;
    }

    if (!interruptOptions.some((option) => option.value === selectedInterruptOption)) {
      setSelectedInterruptOption('');
    }
  }, [interruptOptions, selectedInterruptOption]);

  useEffect(() => {
    if (!workflowState?.current_node) {
      return;
    }
    const hasSelectedTask = Boolean(
      selectedNode && workflowState?.task_queue?.some((task) => task.agent_type === selectedNode),
    );
    if (!hasSelectedTask) {
      setSelectedNode(workflowState.current_node);
    }
  }, [workflowState?.current_node, workflowState?.task_queue, selectedNode]);

  useEffect(() => {
    if (filteredArtifacts.length === 0) {
      if (selectedFile !== null) {
        setSelectedFile(null);
      }
      return;
    }

    if (!selectedFile || !filteredArtifacts.includes(selectedFile)) {
      setSelectedFile(filteredArtifacts[0]);
    }
  }, [filteredArtifacts, selectedFile]);

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

  const getVersionStatusMeta = (status?: RunStatus) => {
    switch (status) {
      case 'running':
        return {
          label: 'RUNNING',
          dot: 'bg-indigo-500',
          pill: 'bg-indigo-50 text-indigo-700 border-indigo-200',
        };
      case 'waiting_human':
        return {
          label: 'WAITING',
          dot: 'bg-amber-500',
          pill: 'bg-amber-50 text-amber-700 border-amber-200',
        };
      case 'success':
        return {
          label: 'DONE',
          dot: 'bg-emerald-500',
          pill: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        };
      case 'failed':
        return {
          label: 'FAILED',
          dot: 'bg-rose-500',
          pill: 'bg-rose-50 text-rose-700 border-rose-200',
        };
      case 'queued':
        return {
          label: 'QUEUED',
          dot: 'bg-slate-400',
          pill: 'bg-slate-50 text-slate-600 border-slate-200',
        };
      default:
        return {
          label: 'UNKNOWN',
          dot: 'bg-gray-300',
          pill: 'bg-gray-50 text-gray-500 border-gray-200',
        };
    }
  };

  const handleRetryNode = async () => {
    if (!id || !selectedVersion || !selectedNode) return;
    setRetryingNode(selectedNode);
    try {
      setStreamStatus('connecting');
      await api.retryWorkflowNode(id, selectedVersion, selectedNode);
      void fetchState();
    } catch (err: any) {
      setUiError(err?.response?.data?.detail || 'Failed to retry selected node');
      setStreamStatus('error');
    } finally {
      setRetryingNode(null);
    }
  };

  const handleContinueWorkflow = async () => {
    if (!id || !selectedVersion) return;
    if (workflowState?.run_status !== 'queued') {
      setUiError('Workflow can only be continued from a queued state.');
      return;
    }
    setContinuingWorkflow(true);
    try {
      setStreamStatus('connecting');
      await api.continueWorkflow(id, selectedVersion);
      void fetchState();
    } catch (err: any) {
      setUiError(err?.response?.data?.detail || 'Failed to continue workflow');
      setStreamStatus('error');
    } finally {
      setContinuingWorkflow(false);
    }
  };

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
              {renderUploadBtn('ir', t('projectDetail.uploadIR'), <FileText size={14} />, true)}
              {renderUploadBtn('physical', t('projectDetail.uploadPhysical'), <Database size={14} />)}
              {renderUploadBtn('logical', t('projectDetail.uploadLogical'), <Layers size={14} />)}
              {renderUploadBtn('dict', t('projectDetail.uploadDict'), <Book size={14} />)}
              {renderUploadBtn('lookup', t('projectDetail.uploadLookup'), <List size={14} />)}
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
                (() => {
                  const summary = versionStateMap[v];
                  const statusMeta = getVersionStatusMeta(summary?.run_status);
                  return (
                    <div
                      key={v}
                      className={`w-full flex items-center justify-between gap-3 p-4 rounded-2xl transition-all text-xs text-left ${
                        selectedVersion === v 
                          ? 'bg-white border-2 border-indigo-500 shadow-md text-gray-900 font-bold' 
                          : 'bg-transparent border border-transparent text-gray-500 hover:bg-gray-100'
                      }`}
                    >
                      <button
                        onClick={() => handleSelectVersion(v)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="font-mono truncate">{v}</div>
                        <div className="mt-2 flex items-center gap-2">
                          <span className={`h-2 w-2 rounded-full ${statusMeta.dot}`} />
                          <span className={`inline-flex items-center rounded-full border px-2 py-1 text-[9px] font-black uppercase tracking-wider ${statusMeta.pill}`}>
                            {statusMeta.label}
                          </span>
                        </div>
                      </button>
                      <div className="flex items-center gap-2">
                        {selectedVersion === v && <div className="h-2 w-2 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]" />}
                        <button
                          onClick={() => handleDeleteVersion(v)}
                          disabled={deletingVersion !== null}
                          className="rounded-xl border border-rose-200 bg-white p-2 text-rose-500 transition-all hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                          title={`Delete ${v}`}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })()
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
                 {workflowState?.run_status === 'queued' && hasPendingTodoTasks && (
                   <button
                     onClick={handleContinueWorkflow}
                     disabled={continuingWorkflow || retryingNode !== null}
                     className="px-4 py-2 bg-indigo-100 text-indigo-700 rounded-xl text-xs font-black uppercase tracking-wider hover:bg-indigo-200 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                   >
                     {continuingWorkflow ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} fill="currentColor" />}
                     Continue Workflow
                   </button>
                 )}
                 {selectedTask?.status === 'failed' && (
                   <button
                     onClick={handleRetryNode}
                     disabled={retryingNode !== null || continuingWorkflow}
                     className="px-4 py-2 bg-rose-100 text-rose-700 rounded-xl text-xs font-black uppercase tracking-wider hover:bg-rose-200 transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                   >
                     {retryingNode === selectedNode ? <RefreshCw size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                     Retry Node
                   </button>
                 )}
               </div>
            </div>

            <TaskKanban 
              tasks={workflowState?.task_queue || []}
              nodeStatuses={effectiveNodeStatuses}
              selectedNode={selectedNode}
              onSelectNode={setSelectedNode}
              t={t}
              currentPhase={workflowState?.workflow_phase}
            />

          </section>

          {workflowState?.run_status === 'failed' && (
            <section className="bg-rose-50 rounded-3xl border border-rose-200 shadow-sm p-8 space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <div className="inline-flex items-center rounded-full bg-rose-100 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-rose-700">
                    Intervention Needed
                  </div>
                  <h2 className="text-xl font-black tracking-tight text-rose-950">
                    {workflowState.stale_execution_detected ? 'Execution looks stalled' : 'Workflow needs attention'}
                  </h2>
                  <p className="text-sm font-medium text-rose-900/80">
                    {workflowState.waiting_reason || 'The workflow stopped unexpectedly. Review the latest logs and retry the affected node.'}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  {workflowState.current_node && (
                    <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-wider text-rose-700 border border-rose-200">
                      {workflowState.current_node}
                    </span>
                  )}
                  <span className="text-[10px] font-bold uppercase tracking-wider text-rose-500">
                    Last update: {new Date(workflowState.updated_at).toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                {selectedTask?.status === 'failed' && (
                  <button
                    onClick={handleRetryNode}
                    disabled={retryingNode !== null || continuingWorkflow}
                    className="flex-1 rounded-2xl bg-rose-600 px-5 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-rose-300"
                  >
                    {retryingNode === selectedNode ? 'Retrying...' : 'Retry Current Node'}
                  </button>
                )}
                {workflowState?.run_status === 'queued' && hasPendingTodoTasks && (
                  <button
                    onClick={handleContinueWorkflow}
                    disabled={continuingWorkflow || retryingNode !== null}
                    className="flex-1 rounded-2xl bg-white px-5 py-4 text-sm font-black uppercase tracking-widest text-rose-700 border border-rose-200 transition-all hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {continuingWorkflow ? 'Resuming...' : 'Resume Queue'}
                  </button>
                )}
              </div>
            </section>
          )}

          {workflowState?.run_status === 'waiting_human' && (
            <section className="bg-amber-50 rounded-3xl border border-amber-200 shadow-sm p-8 space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <div className="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-amber-700">
                    Waiting Human
                  </div>
                  <h2 className="text-xl font-black tracking-tight text-amber-950">
                    {isClarificationInterrupt ? 'Planner needs clarification' : 'Planner is waiting for review'}
                  </h2>
                  <p className="text-sm font-medium text-amber-900/80">
                    {workflowState.waiting_reason || 'Provide the missing detail or review feedback before the workflow continues.'}
                  </p>
                </div>
                {workflowState.current_node && (
                  <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-wider text-amber-700 border border-amber-200">
                    {workflowState.current_node}
                  </span>
                )}
              </div>

              {pendingInterrupt && (
                <div className="rounded-2xl border border-amber-200 bg-white/80 px-4 py-3 space-y-2">
                  <div className="text-[10px] font-black uppercase tracking-widest text-amber-700">Interrupt</div>
                  <div className="text-xs font-medium text-amber-950 space-y-1">
                    <div>node_id: {pendingInterrupt.node_id}</div>
                    {pendingInterrupt.interrupt_id && <div>interrupt_id: {pendingInterrupt.interrupt_id}</div>}
                  </div>
                  {pendingInterrupt.context && Object.keys(pendingInterrupt.context).length > 0 && (
                    <pre className="whitespace-pre-wrap text-xs font-medium text-amber-950 overflow-x-auto">
                      {JSON.stringify(pendingInterrupt.context, null, 2)}
                    </pre>
                  )}
                </div>
              )}

              {isClarificationInterrupt && interruptOptions.length > 0 && (
                <div className="space-y-3">
                  <label className="text-[10px] font-black uppercase tracking-widest text-amber-700">
                    Suggested options
                  </label>
                  <div className="grid gap-3">
                    {interruptOptions.map((option) => {
                      const isSelected = selectedInterruptOption === option.value;
                      return (
                        <label
                          key={option.value}
                          className={`flex cursor-pointer gap-3 rounded-2xl border px-4 py-3 transition-all ${
                            isSelected
                              ? 'border-amber-400 bg-white shadow-sm'
                              : 'border-amber-200 bg-white/70 hover:border-amber-300'
                          }`}
                        >
                          <input
                            type="radio"
                            name="interrupt-option"
                            value={option.value}
                            checked={isSelected}
                            onChange={(e) => setSelectedInterruptOption(e.target.value)}
                            className="mt-1 h-4 w-4 border-amber-300 text-amber-600 focus:ring-amber-400"
                          />
                          <div className="space-y-1">
                            <div className="text-sm font-black text-amber-950">{option.label}</div>
                            {option.description && (
                              <div className="text-xs font-medium text-amber-900/80">{option.description}</div>
                            )}
                            <div className="text-[11px] font-mono text-amber-700">{option.value}</div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-amber-700">
                  {isClarificationInterrupt ? 'Additional details (optional)' : 'Revision feedback'}
                </label>
                <textarea
                  value={reviewFeedback}
                  onChange={(e) => setReviewFeedback(e.target.value)}
                  placeholder={
                    isClarificationInterrupt
                      ? 'If none of the options fit, explain your answer here. You can also add constraints, scope, or business context.'
                      : 'Explain what should change before planner runs again.'
                  }
                  className="w-full min-h-28 rounded-2xl border border-amber-200 bg-white px-4 py-3 text-sm font-medium text-gray-800 focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                {isClarificationInterrupt ? (
                  <button
                    onClick={() => handleResumeExecution('answer')}
                    disabled={resumeActionLoading !== null || (!selectedInterruptOption && reviewFeedback.trim().length === 0)}
                    className="flex-1 rounded-2xl bg-emerald-600 px-5 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                  >
                    {resumeActionLoading === 'answer' ? 'Submitting...' : 'Submit Answer'}
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => handleResumeExecution('approve')}
                      disabled={resumeActionLoading !== null}
                      className="flex-1 rounded-2xl bg-emerald-600 px-5 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                    >
                      {resumeActionLoading === 'approve' ? 'Approving...' : 'Approve Continue'}
                    </button>
                    <button
                      onClick={() => handleResumeExecution('revise')}
                      disabled={resumeActionLoading !== null || reviewFeedback.trim().length === 0}
                      className="flex-1 rounded-2xl bg-amber-600 px-5 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-amber-300"
                    >
                      {resumeActionLoading === 'revise' ? 'Submitting...' : 'Revise Retry'}
                    </button>
                  </>
                )}
              </div>
            </section>
          )}

          <section className="space-y-6">
            <div className="flex items-center gap-3 px-2">
              <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
                {selectedNode === 'planner' 
                  ? t('projectDetail.inputMaterials') 
                  : isValidatorNode 
                    ? t('projectDetail.scanReport')
                    : t('projectDetail.designArtifacts')}
              </h2>
              <div className="h-px flex-1 bg-gray-100" />
            </div>

            {reasoningLogs.length > 0 && (
              <div className="bg-white rounded-3xl border border-gray-100 shadow-sm p-6 space-y-4">
                <div className="flex items-center gap-3">
                  <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-widest">
                    {selectedNode === 'planner' 
                      ? t('projectDetail.reasoningChain') 
                      : isValidatorNode 
                        ? t('projectDetail.validationResult')
                        : t('projectDetail.subagentReasoning')}
                  </h3>
                  {selectedNode && (
                    <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[9px] font-black uppercase tracking-wider text-gray-500">
                      {selectedNode}
                    </span>
                  )}
                </div>
                <div className="bg-gray-900 rounded-2xl p-4 font-mono text-[11px] leading-relaxed text-gray-300 overflow-y-auto max-h-72 space-y-1">
                  {reasoningLogs.map((log: string, idx: number) => (
                    <div key={idx} className="flex gap-3 whitespace-pre-wrap">
                      <span className="text-gray-600 flex-shrink-0">[{idx+1}]</span>
                      <span className={isValidatorNode && log.includes('FAILED') ? 'text-rose-400' : isValidatorNode && log.includes('SUCCESS') ? 'text-emerald-400' : 'text-emerald-400/80'}>{log}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {!isValidatorNode && (
              <ArtifactViewer 
                artifacts={artifacts}
                selectedFile={selectedFile}
                onSelectFile={setSelectedFile}
                filteredArtifacts={filteredArtifacts}
                t={t}
              />
            )}
          </section>

          <section className="bg-white rounded-3xl border border-gray-100 shadow-sm p-8 space-y-4">
            <button 
              onClick={() => setIsLogsOpen(!isLogsOpen)}
              className="flex items-center justify-between w-full group"
            >
              <div className="flex items-center gap-3">
                <h2 className="text-[10px] font-black text-gray-400 uppercase tracking-widest group-hover:text-indigo-500 transition-colors">
                  {t('projectDetail.orchestrationLogs')}
                </h2>
                {workflowState?.current_node && (
                  <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[9px] font-black uppercase tracking-wider text-indigo-600">
                    {workflowState.current_node}
                  </span>
                )}
                {loading && <RefreshCw size={10} className="animate-spin text-indigo-500" />}
              </div>
              <div className={`text-gray-300 transition-transform duration-300 ${isLogsOpen ? 'rotate-180' : ''}`}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
              </div>
            </button>

            {isLogsOpen && (
              <div className="bg-gray-900 rounded-2xl p-4 font-mono text-[11px] leading-relaxed text-gray-300 overflow-y-auto max-h-72 space-y-1 animate-in slide-in-from-top-2 duration-300">
                {executionEntries.length > 0 ? (
                  executionEntries.map((entry, idx) => (
                    entry.kind === 'tool' ? (
                      <div key={entry.id} className="space-y-2">
                        <div className="flex gap-3 text-[10px] font-black uppercase tracking-wider text-gray-500">
                          <span className="text-gray-600">[{idx + 1}]</span>
                          <span>Structured Tool Event</span>
                        </div>
                        <ToolEventCard event={entry.event} />
                      </div>
                    ) : (
                      <div key={entry.id} className="flex gap-3 whitespace-pre-wrap">
                        <span className="text-gray-600 flex-shrink-0">[{idx + 1}]</span>
                        <span className={entry.tone === 'error' ? 'text-rose-400' : 'text-emerald-400/80'}>
                          {entry.text}
                        </span>
                      </div>
                    )
                  ))
                ) : (
                  <div className="text-gray-600 italic text-[10px]">{t('projectDetail.noRelevantContext')}</div>
                )}
              </div>
            )}
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
