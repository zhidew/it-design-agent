import React, { useMemo, useState } from 'react';
import { ChevronDown, Clock3, Wrench } from 'lucide-react';

export interface ToolEventViewModel {
  event_id: string;
  event_type: 'tool_event';
  run_id: string;
  timestamp: string;
  node_id: string;
  node_type: string;
  tool_name: string;
  status: 'success' | 'error';
  error_code: string;
  duration_ms: number;
  tool_input: Record<string, unknown>;
  tool_output: Record<string, unknown>;
}

interface ToolEventCardProps {
  event: ToolEventViewModel;
}

const MAX_PREVIEW_LENGTH = 220;

function summarizeValue(value: Record<string, unknown>): string {
  const serialized = JSON.stringify(value, null, 2);
  return serialized.length <= MAX_PREVIEW_LENGTH
    ? serialized
    : `${serialized.slice(0, MAX_PREVIEW_LENGTH)}...`;
}

export function ToolEventCard({ event }: ToolEventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const inputPreview = useMemo(() => summarizeValue(event.tool_input), [event.tool_input]);
  const outputPreview = useMemo(() => summarizeValue(event.tool_output), [event.tool_output]);
  const hasLongOutput = outputPreview.length >= MAX_PREVIEW_LENGTH;

  return (
    <div className="rounded-2xl border border-sky-200 bg-gradient-to-br from-sky-950 via-slate-900 to-slate-950 p-4 text-slate-100 shadow-[0_12px_40px_rgba(14,116,144,0.18)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-sky-400/15 p-2 text-sky-300">
              <Wrench size={14} />
            </span>
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.24em] text-sky-300">Tool Call</div>
              <div className="text-sm font-black tracking-wide text-white">{event.tool_name}</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-300">
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">{event.node_type}</span>
            <span className={`rounded-full px-2.5 py-1 ${event.status === 'success' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-rose-400/15 text-rose-300'}`}>
              {event.status}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
              <Clock3 size={10} />
              {event.duration_ms} ms
            </span>
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">{event.error_code}</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-200 transition-colors hover:bg-white/10"
        >
          {expanded ? 'Collapse' : 'Expand'}
          <ChevronDown size={12} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <section className="rounded-2xl border border-white/8 bg-black/20 p-3">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Params</div>
          <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-sky-100">{inputPreview}</pre>
        </section>
        <section className="rounded-2xl border border-white/8 bg-black/20 p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Result</div>
            {hasLongOutput && (
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-500">
                {expanded ? 'Full payload' : 'Preview'}
              </span>
            )}
          </div>
          <pre className="mt-2 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-emerald-100">
            {expanded ? JSON.stringify(event.tool_output, null, 2) : outputPreview}
          </pre>
        </section>
      </div>
    </div>
  );
}
