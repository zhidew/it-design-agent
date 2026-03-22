import React, { memo, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Circle,
  Loader as LucideLoader,
  MinusCircle,
  Sparkles,
  XCircle,
} from 'lucide-react';

export type NodeStatus = 'todo' | 'running' | 'waiting_human' | 'success' | 'failed' | 'skipped' | 'idle';

export interface Task {
  id: string;
  agent_type: string;
  status: NodeStatus;
  priority?: number;
  phase?: string;
}

interface TaskKanbanProps {
  tasks: Task[];
  nodeStatuses: Record<string, NodeStatus>;
  selectedNode: string | null;
  onSelectNode: (nodeId: string) => void;
  t: (key: string) => string;
  currentPhase?: string;
  selectedPipeline?: string[]; // Pipeline from planner reasoning
  isInitializing?: boolean; // True when workflow just started
  showPlannedStages?: boolean;
}

const ALL_STAGES = [
  { id: 'ANALYSIS', agents: ['planner'] },
  { id: 'ARCHITECTURE', agents: ['architecture-mapping', 'integration-design'] },
  { id: 'MODELING', agents: ['data-design', 'ddd-structure'] },
  { id: 'INTERFACE', agents: ['flow-design', 'api-design', 'config-design'] },
  { id: 'QUALITY', agents: ['test-design', 'ops-design'] },
  { id: 'DELIVERY', agents: ['design-assembler', 'validator'] },
];

const TaskKanbanComponent: React.FC<TaskKanbanProps> = ({
  tasks,
  nodeStatuses,
  selectedNode,
  onSelectNode,
  t,
  currentPhase,
  selectedPipeline,
  isInitializing,
  showPlannedStages = false,
}) => {
  const hasTaskBackedPipeline = tasks.some((task) => task.agent_type !== 'planner');
  const hasConfirmedPipeline = (selectedPipeline?.length || 0) > 0 || hasTaskBackedPipeline;

  // Check if we're in initialization mode (tasks empty but workflow running)
  const showInitMode = !!(isInitializing && tasks.length === 0);

  // Check if we're in "Blueprint Mode" (Cold Start)
  const isBlueprintMode = !hasConfirmedPipeline && tasks.length === 0;

  // Check if we're in analysis phase (only planner is active)
  const isInAnalysisPhase = useMemo(() => {
    if (isBlueprintMode) return false;
    if (!hasConfirmedPipeline && !hasTaskBackedPipeline) {
      return true;
    }
    if (showInitMode) return true;

    const plannerTask = tasks.find((t) => t.agent_type === 'planner');
    const nonPlannerTasks = tasks.filter((t) => t.agent_type !== 'planner');

    // Case 1: Only planner in queue, and it's running or waiting for human
    if (tasks.length === 1 && plannerTask) {
      return plannerTask.status === 'running' || plannerTask.status === 'waiting_human';
    }

    // Case 2: Planner is active (running/waiting_human) and all other agents are still todo (not started)
    if (plannerTask && nonPlannerTasks.length > 0) {
      const plannerIsActive = plannerTask.status === 'running' || plannerTask.status === 'waiting_human';
      const allOthersAreTodo = nonPlannerTasks.every((t) => t.status === 'todo');
      return plannerIsActive && allOthersAreTodo;
    }

    return false;
  }, [hasConfirmedPipeline, hasTaskBackedPipeline, showInitMode, tasks, isBlueprintMode]);

  // Determine active agents: prefer tasks, fallback to selectedPipeline
  const activeAgentTypes = useMemo(() => {
    const fromTasks = new Set(
      tasks.map((task) => task.agent_type)
    );
    if (fromTasks.size > 0) {
      return fromTasks;
    }
    // During init, show planner as active
    if (showInitMode) {
      return new Set(['planner']);
    }
    return new Set<string>();
  }, [tasks, selectedPipeline, showInitMode]);

  // Derive stages dynamically based on active tasks and their phases
  const activeStages = useMemo(() => {
    if (isBlueprintMode) {
      return ALL_STAGES;
    }
    if (isInAnalysisPhase) {
      return ALL_STAGES.filter((stage) => stage.id === 'ANALYSIS');
    }
    
    // Get unique phases from tasks
    const phaseIdsFromTasks = new Set(
      tasks
        .map(t => t.phase)
        .filter((p): p is string => !!p)
    );

    if (phaseIdsFromTasks.size > 0) {
      // Return stages that match the phases found in tasks, preserving ALL_STAGES order
      return ALL_STAGES.filter(stage => phaseIdsFromTasks.has(stage.id));
    }

    if (activeAgentTypes.size === 0) {
      return [];
    }
    
    // Fallback: Filter ALL_STAGES to only include stages with active agents
    return ALL_STAGES.filter((stage) => stage.agents.some((agentId) => activeAgentTypes.has(agentId)));
  }, [isInAnalysisPhase, tasks, activeAgentTypes, isBlueprintMode]);

  // Get pending stages (from selectedPipeline but not yet in tasks)
  // Only show pending stages when NOT in analysis phase
  const pendingStages = useMemo(() => {
    // Never show pending stages during analysis or blueprint phase
    if (isInAnalysisPhase || isBlueprintMode) return [];
    if (!showPlannedStages || !selectedPipeline || tasks.length === 0) return [];
    
    const activeStageIds = new Set(activeStages.map(s => s.id));
    
    return ALL_STAGES.filter(
      (stage) => !activeStageIds.has(stage.id) &&
        stage.agents.some((agentId) => selectedPipeline.includes(agentId))
    );
  }, [isInAnalysisPhase, showPlannedStages, selectedPipeline, tasks, activeStages, isBlueprintMode]);

  const gridTemplateColumns = isInAnalysisPhase
    ? '1fr 3fr'
    : `repeat(${Math.max(activeStages.length + (showInitMode ? 1 : pendingStages.length), 1)}, minmax(0, 1fr))`;

  const renderNode = (nodeId: string, label: string, _isActive: boolean, isLoading: boolean = false) => {
    const status = isLoading ? 'running' : (nodeStatuses[nodeId] || 'idle');
    const isSelected = selectedNode === nodeId;

    let icon = <Circle size={10} className="text-gray-300" />;
    let borderColor = 'border-gray-100';
    let bgColor = 'bg-white';
    let textColor = 'text-gray-400';
    let animation = '';

    if (status === 'running' || isLoading) {
      icon = <LucideLoader size={10} className="text-indigo-500 animate-spin" />;
      borderColor = 'border-indigo-400 shadow-[0_0_12px_rgba(99,102,241,0.2)]';
      bgColor = 'bg-indigo-50';
      textColor = 'text-indigo-900 font-bold';
      animation = 'animate-pulse';
    } else if (status === 'success') {
      icon = <CheckCircle size={10} className="text-emerald-500" />;
      borderColor = 'border-emerald-200';
      bgColor = 'bg-emerald-50/30';
      textColor = 'text-emerald-900 font-semibold';
    } else if (status === 'failed') {
      icon = <XCircle size={10} className="text-rose-500" />;
      borderColor = 'border-rose-200';
      bgColor = 'bg-rose-50/20';
      textColor = 'text-rose-900 font-semibold';
    } else if (status === 'waiting_human') {
      icon = <AlertTriangle size={10} className="text-amber-500" />;
      borderColor = 'border-amber-300';
      bgColor = 'bg-amber-50/40';
      textColor = 'text-amber-900 font-semibold';
    } else if (status === 'skipped') {
      icon = <MinusCircle size={10} className="text-gray-400" />;
      borderColor = 'border-gray-200';
      bgColor = 'bg-gray-50';
      textColor = 'text-gray-500 font-semibold';
    }

    if (isSelected) {
      borderColor = 'border-indigo-600 ring-4 ring-indigo-50';
    }

    return (
      <button
        key={nodeId}
        onClick={() => !isLoading && onSelectNode(nodeId)}
        disabled={isLoading}
        className={`relative flex items-center gap-2 w-full p-2.5 rounded-xl border ${borderColor} ${bgColor} ${textColor} ${animation} transition-all duration-300 hover:translate-y-[-1px] text-[9px] uppercase tracking-tighter font-black shadow-sm group ${isLoading ? 'cursor-wait' : ''}`}
      >
        <span className="flex-shrink-0">{icon}</span>
        <span className="flex-1 text-left truncate">{label}</span>
      </button>
    );
  };

  // Render initialization placeholder with breathing animation
  const renderInitPlaceholder = () => (
    <div className="flex min-w-0 flex-col items-center gap-3 transition-all duration-500">
      <div className="relative flex h-7 w-7 items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-indigo-200 animate-ping opacity-75" />
        <div className="absolute inset-1 rounded-full bg-indigo-100 animate-pulse" />
        <Sparkles size={14} className="relative text-indigo-500 animate-pulse" />
      </div>
      <span className="text-[9px] font-black uppercase tracking-tight text-center leading-tight text-indigo-400 animate-pulse">
        {t('stages.initializing') || 'Initializing...'}
      </span>
    </div>
  );

  // Render pending stage with dashed style
  const renderPendingStage = (stage: typeof ALL_STAGES[0], idx: number) => (
    <div key={`pending-${stage.id}`} className="flex min-w-0 flex-col items-center gap-3 transition-all duration-500 opacity-50">
      <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-dashed border-gray-300">
        <span className="text-[10px] font-black text-gray-400">{idx + 1}</span>
      </div>
      <span className="text-[9px] font-black uppercase tracking-tight text-center leading-tight text-gray-400">
        {t(`stages.${stage.id}`)}
      </span>
    </div>
  );

  // Render analysis phase waiting placeholder
  const renderAnalysisWaitingPlaceholder = () => (
    <div className="flex min-w-0 flex-col items-center gap-3 transition-all duration-500">
      <div className="relative flex h-7 w-7 items-center justify-center">
        <div className="absolute inset-0 rounded-full bg-gray-200 animate-ping opacity-30" />
        <div className="absolute inset-1 rounded-full bg-gray-100 animate-pulse" />
        <LucideLoader size={14} className="relative text-gray-400 animate-spin" />
      </div>
      <span className="text-[9px] font-black uppercase tracking-tight text-center leading-tight text-gray-400 animate-pulse">
        {t('stages.waiting') || 'Waiting...'}
      </span>
    </div>
  );

  return (
    <div className="w-full space-y-8">
      <div className="relative px-2 py-2">
        <div className="absolute top-1/2 left-8 right-8 h-[1px] bg-gray-100 -translate-y-[12px] z-0" />

        <div
          className="relative z-10 grid items-start gap-4"
          style={{ gridTemplateColumns }}
        >
          {activeStages.map((stage, idx) => {
            const isActive = currentPhase === stage.id || (showInitMode && stage.id === 'ANALYSIS');
            const stageAgentsInQueue = stage.agents.filter((agentId) => tasks.some((task) => task.agent_type === agentId));
            const statuses = stageAgentsInQueue.map((agentId) => nodeStatuses[agentId] || 'idle');
            const isAllSuccess = statuses.length > 0 && statuses.every((status) => status === 'success');
            
            // Special handling for ANALYSIS stage to prevent premature success checkmark
            // while the planner might still be finalizing its state.
            const isAnalysisStageReallyDone = stage.id === 'ANALYSIS' 
              ? (isAllSuccess && currentPhase !== 'ANALYSIS')
              : isAllSuccess;

            const hasFailed = statuses.some((status) => status === 'failed');
            const hasWaitingHuman = statuses.some((status) => status === 'waiting_human');
            const hasSuccess = statuses.some((status) => status === 'success');
            const hasRunning = statuses.some((status) => status === 'running');

            let circleColor = 'bg-white border-gray-200 text-gray-300';
            let textColor = 'text-gray-400';
            let icon = <span className="text-[10px] font-black">{idx + 1}</span>;

            if (showInitMode && stage.id === 'ANALYSIS') {
              circleColor = 'bg-indigo-500 border-indigo-500 text-white shadow-lg shadow-indigo-200';
              textColor = 'text-indigo-600';
              icon = <Activity size={14} className="animate-pulse" />;
            } else if (isBlueprintMode) {
              circleColor = 'bg-gray-50 border-dashed border-gray-300 text-gray-300';
              textColor = 'text-gray-400 opacity-60';
              icon = <Circle size={10} className="opacity-40" />;
            } else if (isAnalysisStageReallyDone) {
              circleColor = 'bg-emerald-500 border-emerald-500 text-white';
              textColor = 'text-emerald-600';
              icon = <CheckCircle size={14} />;
            } else if (hasFailed && hasSuccess) {
              circleColor = 'bg-amber-500 border-amber-500 text-white';
              textColor = 'text-amber-600';
              icon = <AlertTriangle size={14} />;
            } else if (hasWaitingHuman) {
              circleColor = 'bg-amber-400 border-amber-400 text-white';
              textColor = 'text-amber-600';
              icon = <AlertTriangle size={14} />;
            } else if (hasFailed) {
              circleColor = 'bg-rose-500 border-rose-500 text-white';
              textColor = 'text-rose-600';
              icon = <XCircle size={14} />;
            } else if (isActive || hasRunning) {
              circleColor = 'bg-white border-indigo-600 text-indigo-600 shadow-md scale-110';
              textColor = 'text-indigo-600';
              icon = <Activity size={14} className="animate-pulse" />;
            }

            return (
              <div key={stage.id} className="flex min-w-0 flex-col items-center gap-3 transition-all duration-500">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 transition-all duration-500 ${circleColor}`}>
                  {icon}
                </div>
                <span className={`text-[9px] font-black uppercase tracking-tight text-center leading-tight transition-colors break-words ${textColor}`}>
                  {t(`stages.${stage.id}`)}
                </span>
              </div>
            );
          })}

          {isInAnalysisPhase && renderAnalysisWaitingPlaceholder()}
          {!isInAnalysisPhase && showInitMode && renderInitPlaceholder()}
          {!isInAnalysisPhase && pendingStages.map((stage, idx) => renderPendingStage(stage, activeStages.length + idx))}
        </div>
      </div>

      <div
        className="grid items-start gap-4"
        style={{ gridTemplateColumns }}
      >
        {activeStages.map((stage) => {
          if (isBlueprintMode) {
            return (
              <div
                key={stage.id}
                className="flex min-w-0 flex-col gap-2 p-2.5 rounded-2xl border border-dashed border-gray-100 bg-gray-50/10 min-h-[110px] opacity-40 transition-all duration-700"
              >
                <div className="flex flex-col gap-1.5">
                  {stage.agents.map((agentId) => (
                    <div
                      key={agentId}
                      className="flex items-center gap-2 w-full p-2.5 rounded-xl border border-dashed border-gray-100 bg-white/40 text-gray-300 text-[9px] uppercase tracking-tighter font-black"
                    >
                      <Circle size={10} className="opacity-30" />
                      <span className="truncate">{t(`agents.${agentId}`)}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          }

          const isActive = currentPhase === stage.id || (showInitMode && stage.id === 'ANALYSIS');
          const stageAgentsInQueue = stage.agents.filter((agentId) => tasks.some((task) => task.agent_type === agentId));

          return (
            <div
              key={stage.id}
              className={`flex min-w-0 flex-col gap-2 p-2.5 rounded-2xl border transition-all duration-500 min-h-[110px] ${isActive
                ? 'bg-white border-indigo-100 shadow-xl shadow-indigo-50/50 ring-1 ring-indigo-50'
                : 'bg-white/60 border-gray-100 shadow-sm opacity-90'
                }`}
            >
              <div className="flex flex-col gap-1.5">
                {stageAgentsInQueue.map((agentId) => {
                  const isLoading = agentId === 'planner' && (showInitMode || !hasConfirmedPipeline);
                  return renderNode(agentId, t(`agents.${agentId}`), isActive, isLoading);
                })}
              </div>
            </div>
          );
        })}

        {isInAnalysisPhase && !isBlueprintMode && (
          <div className="flex min-w-0 flex-col gap-2 p-2.5 rounded-2xl border border-dashed border-gray-200 bg-gray-50/30 min-h-[110px]">
            <div className="flex flex-1 items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-gray-200 animate-ping opacity-30" />
                  <div className="absolute inset-0 rounded-full bg-gray-100 animate-pulse" />
                  <LucideLoader size={20} className="relative text-gray-400 animate-spin" />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-tight text-gray-500 animate-pulse">
                  {t('pipeline.expertsWaiting') || '设计专家正在等待加载...'}
                </span>
              </div>
            </div>
          </div>
        )}

        {isBlueprintMode && (
          <div className="hidden" /> // Already covered by skeleton cards
        )}

        {!isInAnalysisPhase && !isBlueprintMode && showInitMode && (
          <div className="flex min-w-0 flex-col gap-2 p-2.5 rounded-2xl border border-dashed border-indigo-200 bg-indigo-50/30 min-h-[110px]">
            <div className="flex flex-1 items-center justify-center">
              <div className="flex flex-col items-center gap-2">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-indigo-200 animate-ping opacity-50" />
                  <LucideLoader size={16} className="relative text-indigo-500 animate-spin" />
                </div>
                <span className="text-[9px] font-bold uppercase tracking-tight text-indigo-500 animate-pulse">
                  {t('pipeline.preparing') || 'Preparing pipeline...'}
                </span>
              </div>
            </div>
          </div>
        )}

        {!isInAnalysisPhase && pendingStages.map((stage) => (
          <div
            key={`pending-${stage.id}`}
            className="flex min-w-0 flex-col gap-2 p-2.5 rounded-2xl border border-dashed border-gray-200 bg-gray-50/30 min-h-[110px] opacity-50"
          >
            <div className="flex min-h-[68px] items-center justify-center rounded-xl border border-dashed border-gray-200 bg-gray-50/60 px-2 text-center text-[9px] font-bold uppercase tracking-tight text-gray-300">
              {t(`stages.${stage.id}`)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

function buildTasksSignature(tasks: Task[]): string {
  return tasks.map((task) => `${task.agent_type}:${task.status}:${task.priority}:${task.phase || ''}`).join('|');
}

function buildNodeStatusesSignature(nodeStatuses: Record<string, NodeStatus>): string {
  return Object.entries(nodeStatuses)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}:${value}`)
    .join('|');
}

export const TaskKanban = memo(TaskKanbanComponent, (prev, next) => (
  prev.selectedNode === next.selectedNode &&
  prev.currentPhase === next.currentPhase &&
  prev.t === next.t &&
  prev.selectedPipeline === next.selectedPipeline &&
  prev.isInitializing === next.isInitializing &&
  prev.showPlannedStages === next.showPlannedStages &&
  buildTasksSignature(prev.tasks) === buildTasksSignature(next.tasks) &&
  buildNodeStatusesSignature(prev.nodeStatuses) === buildNodeStatusesSignature(next.nodeStatuses)
));
