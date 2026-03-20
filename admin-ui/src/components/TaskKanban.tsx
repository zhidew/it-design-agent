import React, { memo, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Circle,
  Loader as LucideLoader,
  MinusCircle,
  XCircle,
} from 'lucide-react';

export type NodeStatus = 'todo' | 'running' | 'waiting_human' | 'success' | 'failed' | 'skipped' | 'idle';

export interface Task {
  id: string;
  agent_type: string;
  status: NodeStatus;
  priority: number;
}

interface TaskKanbanProps {
  tasks: Task[];
  nodeStatuses: Record<string, NodeStatus>;
  selectedNode: string | null;
  onSelectNode: (nodeId: string) => void;
  t: (key: string) => string;
  currentPhase?: string;
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
}) => {
  const activeStages = useMemo(() => {
    const activeAgentTypes = new Set(tasks.map((task) => task.agent_type));
    if (tasks.length === 0) {
      return ALL_STAGES;
    }
    return ALL_STAGES.filter((stage) => stage.agents.some((agentId) => activeAgentTypes.has(agentId)));
  }, [tasks]);
  const gridTemplateColumns = `repeat(${Math.max(activeStages.length, 1)}, minmax(0, 1fr))`;

  const renderNode = (nodeId: string, label: string, isPhaseActive: boolean) => {
    const status = nodeStatuses[nodeId] || 'idle';
    const isSelected = selectedNode === nodeId;

    let icon = <Circle size={10} className="text-gray-300" />;
    let borderColor = 'border-gray-100';
    let bgColor = 'bg-white';
    let textColor = 'text-gray-400';
    let animation = '';

    if (status === 'running') {
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
        onClick={() => onSelectNode(nodeId)}
        className={`relative flex items-center gap-2 w-full p-2.5 rounded-xl border ${borderColor} ${bgColor} ${textColor} ${animation} transition-all duration-300 hover:translate-y-[-1px] text-[9px] uppercase tracking-tighter font-black shadow-sm group`}
      >
        <span className="flex-shrink-0">{icon}</span>
        <span className="flex-1 text-left truncate">{label}</span>
      </button>
    );
  };

  return (
    <div className="w-full space-y-8">
      <div className="relative px-2 py-2">
        <div className="absolute top-1/2 left-8 right-8 h-[1px] bg-gray-100 -translate-y-[12px] z-0" />

        <div
          className="relative z-10 grid items-start gap-4"
          style={{ gridTemplateColumns }}
        >
          {activeStages.map((stage, idx) => {
            const isActive = currentPhase === stage.id;
            const stageAgentsInQueue = stage.agents.filter((agentId) => tasks.some((task) => task.agent_type === agentId));
            const statuses = stageAgentsInQueue.map((agentId) => nodeStatuses[agentId] || 'idle');
            const isAllSuccess = statuses.length > 0 && statuses.every((status) => status === 'success');
            const hasFailed = statuses.some((status) => status === 'failed');
            const hasWaitingHuman = statuses.some((status) => status === 'waiting_human');
            const hasSuccess = statuses.some((status) => status === 'success');

            let circleColor = 'bg-white border-gray-200 text-gray-300';
            let textColor = 'text-gray-400';
            let icon = <span className="text-[10px] font-black">{idx + 1}</span>;

            if (isAllSuccess) {
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
            } else if (isActive) {
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
        </div>
      </div>

      <div
        className="grid items-start gap-4"
        style={{ gridTemplateColumns }}
      >
        {activeStages.map((stage) => {
          const isActive = currentPhase === stage.id;
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
                {stageAgentsInQueue.map((agentId) => renderNode(agentId, t(`agents.${agentId}`), isActive))}
              </div>
              {stageAgentsInQueue.length === 0 && (
                <div className="flex min-h-[68px] items-center justify-center rounded-xl border border-dashed border-gray-100 bg-gray-50/60 px-2 text-center text-[9px] font-bold uppercase tracking-tight text-gray-300">
                  {t(`stages.${stage.id}`)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

function buildTasksSignature(tasks: Task[]): string {
  return tasks.map((task) => `${task.agent_type}:${task.status}:${task.priority}`).join('|');
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
  buildTasksSignature(prev.tasks) === buildTasksSignature(next.tasks) &&
  buildNodeStatusesSignature(prev.nodeStatuses) === buildNodeStatusesSignature(next.nodeStatuses)
));
