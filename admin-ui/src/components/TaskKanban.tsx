import React, { useMemo } from 'react';
import { Circle, CheckCircle, XCircle, Loader as LucideLoader, Activity, AlertTriangle } from 'lucide-react';

export type NodeStatus = 'todo' | 'running' | 'success' | 'failed' | 'blocked' | 'idle' | 'review';

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
  humanInterventionRequired?: boolean;
  lastWorker?: string;
  currentPhase?: string;
}

const ALL_STAGES = [
  { id: 'ANALYSIS', agents: ['planner'] },
  { id: 'ARCHITECTURE', agents: ['architecture-mapping', 'integration-design'] },
  { id: 'MODELING', agents: ['data-design', 'ddd-structure'] },
  { id: 'INTERFACE', agents: ['flow-design', 'api-design', 'config-design'] },
  { id: 'READINESS', agents: ['test-design', 'ops-readiness'] },
  { id: 'DELIVERY', agents: ['design-assembler', 'validator'] },
];

export const TaskKanban: React.FC<TaskKanbanProps> = ({ 
  tasks,
  nodeStatuses, 
  selectedNode, 
  onSelectNode,
  t,
  currentPhase
}) => {
  
  // 1. 动态计算活跃阶段：彻底过滤掉没有任务的阶段
  const activeStages = useMemo(() => {
    const activeAgentTypes = new Set(tasks.map(t => t.agent_type));
    // 如果任务列表为空（刚开始），显示默认 6 个，加载完后立即切换
    if (tasks.length === 0) return ALL_STAGES;
    return ALL_STAGES.filter(stage => 
      stage.agents.some(agentId => activeAgentTypes.has(agentId))
    );
  }, [tasks]);

  const renderNode = (nodeId: string, label: string, isPhaseActive: boolean) => {
    let status = nodeStatuses[nodeId] || 'idle';
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
    <div className="space-y-8 flex flex-col items-center">
      {/* 1. 动态时间轴：使用 Flex 弹性排列并居中 */}
      <div className="relative flex items-center justify-center w-full px-4 overflow-x-auto no-scrollbar py-2">
        {/* 背景线：自动适配动态数量 */}
        <div className="absolute top-1/2 left-[15%] right-[15%] h-[1px] bg-gray-100 -translate-y-[12px] z-0" />
        
        <div className="flex gap-12 relative z-10">
          {activeStages.map((stage, idx) => {
            const isActive = currentPhase === stage.id;
            
            const stageAgentsInQueue = stage.agents.filter(agentId => tasks.some(t => t.agent_type === agentId));
            const statuses = stageAgentsInQueue.map(id => nodeStatuses[id] || 'idle');
            const isAllSuccess = statuses.length > 0 && statuses.every(s => s === 'success');
            const hasFailed = statuses.some(s => s === 'failed');
            const hasSuccess = statuses.some(s => s === 'success');
            
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
              <div key={stage.id} className="flex flex-col items-center gap-3 transition-all duration-500 min-w-[140px]">
                <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 transition-all duration-500 ${circleColor}`}>
                  {icon}
                </div>
                <span className={`text-[9px] font-black uppercase tracking-tight text-center leading-tight transition-colors ${textColor}`}>
                  {t(`stages.${stage.id}`)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 2. 动态任务区：使用 Flex 弹性排列并完美对齐上方 Stepper */}
      <div className="flex justify-center w-full">
        <div className="flex gap-12 items-start">
          {activeStages.map(stage => {
            const isActive = currentPhase === stage.id;
            const stageAgentsInQueue = stage.agents.filter(agentId => tasks.some(t => t.agent_type === agentId));
            
            return (
              <div key={stage.id} className={`flex flex-col gap-2 p-2.5 rounded-2xl border transition-all duration-500 min-h-[110px] w-[140px] ${
                isActive ? 'bg-white border-indigo-100 shadow-xl shadow-indigo-50/50 ring-1 ring-indigo-50' : 
                'bg-white/60 border-gray-100 shadow-sm opacity-90'
              }`}>
                <div className="flex flex-col gap-1.5">
                  {stageAgentsInQueue.map(agentId => renderNode(agentId, t(`agents.${agentId}`), isActive))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
