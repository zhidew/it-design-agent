import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, FileJson, Database, MessageSquareText, GitCompare, Check, X, Wand2, ShieldAlert, AlertTriangle, GitBranch, CheckCircle2 } from 'lucide-react';
import { CodeBlock } from './CodeBlock'; // Assuming we'll extract CodeBlock too
import { api, type ArtifactAnchor, type DesignArtifact, type RevisionPatch, type RevisionSession } from '../api';

interface ArtifactViewerProps {
  projectId: string;
  version: string | null;
  artifacts: Record<string, string>;
  designArtifacts: DesignArtifact[];
  selectedFile: string | null;
  onSelectFile: (filename: string) => void;
  filteredArtifacts: string[];
  onArtifactsChanged?: () => void;
  t: (key: string) => string;
}

const getApiErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    if (typeof response?.data?.detail === 'string') {
      return response.data.detail;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
};

export const ArtifactViewer: React.FC<ArtifactViewerProps> = ({
  projectId,
  version,
  artifacts,
  designArtifacts,
  selectedFile,
  onSelectFile,
  filteredArtifacts,
  onArtifactsChanged,
  t
}) => {
  const [selectedExcerpt, setSelectedExcerpt] = useState('');
  const [discussionScope, setDiscussionScope] = useState<'artifact' | 'selection'>('selection');
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [replacementText, setReplacementText] = useState('');
  const [revisionSession, setRevisionSession] = useState<RevisionSession | null>(null);
  const [anchor, setAnchor] = useState<ArtifactAnchor | null>(null);
  const [patchPreview, setPatchPreview] = useState<RevisionPatch | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);

  const getFileIcon = (filename: string) => {
    if (filename.endsWith('.sql')) return <Database size={16} className="text-purple-500" />;
    if (filename.endsWith('.yaml') || filename.endsWith('.json')) return <FileJson size={16} className="text-yellow-500" />;
    return <FileText size={16} className="text-blue-500" />;
  };

  const activeDesignArtifact = useMemo(() => {
    if (!selectedFile) return null;
    const candidates = designArtifacts.filter((item) => item.file_name === selectedFile || item.file_path.endsWith(`/${selectedFile}`));
    return candidates.sort((left, right) => right.artifact_version - left.artifact_version)[0] || null;
  }, [designArtifacts, selectedFile]);

  const reflection = activeDesignArtifact?.reflection;
  const consistency = activeDesignArtifact?.consistency;
  const consistencyConflicts = consistency?.conflicts || [];
  const decisionLogs = activeDesignArtifact?.decision_logs || [];
  const outgoingImpacts = activeDesignArtifact?.impact_records || [];
  const incomingImpacts = activeDesignArtifact?.incoming_impacts || [];
  const sectionReviews = activeDesignArtifact?.section_reviews || [];
  const canDiscuss = Boolean(projectId && version && selectedFile && activeDesignArtifact);
  const normalizedIntent = revisionSession?.normalized_revision_request || {};
  const candidateConflictIds = Array.isArray(normalizedIntent.candidate_conflicts)
    ? (normalizedIntent.candidate_conflicts as string[])
    : [];
  const candidateConflictCount = candidateConflictIds.length;
  const decisionRequired = Boolean(normalizedIntent.decision_required);
  const blockingConflictCount = consistencyConflicts.filter((conflict) => conflict.severity === 'blocking' && conflict.status === 'open').length;
  const warningConflictCount = consistencyConflicts.filter((conflict) => conflict.severity === 'warning' && conflict.status === 'open').length;
  const openImpactCount = [...incomingImpacts, ...outgoingImpacts].filter((impact) => impact.impact_status !== 'no_impact').length;
  const disputedSectionCount = sectionReviews.filter((review) => ['disputed', 'revision_pending', 'blocked_by_conflict'].includes(review.status)).length;
  const overallReviewStatus = blockingConflictCount > 0 || activeDesignArtifact?.status === 'system_check_failed'
    ? 'blocked'
    : activeDesignArtifact?.status === 'accepted' || activeDesignArtifact?.status === 'auto_accepted'
      ? 'accepted'
      : warningConflictCount > 0 || openImpactCount > 0 || disputedSectionCount > 0 || reflection?.status === 'warning'
        ? 'needs_review'
        : 'ready_for_review';

  const governanceTone = overallReviewStatus === 'blocked'
    ? 'rose'
    : overallReviewStatus === 'accepted'
      ? 'emerald'
      : overallReviewStatus === 'needs_review'
        ? 'amber'
        : 'indigo';

  const openDrawer = (scope: 'artifact' | 'selection', excerpt = '', nextFeedback = '') => {
    setDiscussionScope(scope);
    setSelectedExcerpt(excerpt);
    setReplacementText(excerpt);
    setFeedback(nextFeedback);
    setRevisionSession(null);
    setAnchor(null);
    setPatchPreview(null);
    setDrawerError(null);
    setIsDrawerOpen(true);
  };

  const handleCaptureSelection = () => {
    const selection = window.getSelection()?.toString().trim() || '';
    if (!selection) {
      setDrawerError('请先选中一段内容。');
      return;
    }
    openDrawer('selection', selection);
  };

  const handleStartArtifactDiscussion = (initialFeedback = '') => {
    openDrawer('artifact', '', initialFeedback);
  };

  const ensureSelectionAnchor = async () => {
    if (!version || !selectedFile || !activeDesignArtifact || !selectedExcerpt.trim()) {
      throw new Error('请先选中一段内容。');
    }
    if (anchor) return anchor;
    const createdAnchor = await api.createArtifactAnchor(projectId, version, activeDesignArtifact.artifact_id, {
      file_name: selectedFile,
      anchor_type: selectedExcerpt.includes('\n```') ? 'code_block' : 'text_range',
      text_excerpt: selectedExcerpt,
    });
    setAnchor(createdAnchor);
    return createdAnchor;
  };

  const handleStartRevision = async () => {
    if (!version || !selectedFile || !activeDesignArtifact) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      const session = await api.createRevisionSession(projectId, version, activeDesignArtifact.artifact_id, feedback);
      const createdAnchor = discussionScope === 'selection' ? await ensureSelectionAnchor() : null;
      const updatedSession = feedback.trim()
        ? await api.addRevisionMessage(projectId, version, session.revision_session_id, feedback)
        : session;
      const finalized = await api.finalizeRevisionSession(projectId, version, updatedSession.revision_session_id);
      setRevisionSession(finalized);
      setAnchor(createdAnchor);
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '创建修订会话失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleCreatePatchPreview = async () => {
    if (!version || !activeDesignArtifact || !revisionSession || !anchor) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      const patch = await api.createRevisionPatchPreview(projectId, version, revisionSession.revision_session_id, {
        artifact_id: activeDesignArtifact.artifact_id,
        anchor_id: anchor.anchor_id,
        replacement_text: replacementText,
        rationale: feedback,
        preserve_policy: 'preserve_unselected_content',
      });
      setPatchPreview(patch);
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '生成补丁预览失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleApplyPatch = async () => {
    if (!version || !patchPreview) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      const applied = await api.applyRevisionPatch(projectId, version, patchPreview.patch_id);
      setPatchPreview(applied);
      await onArtifactsChanged?.();
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '应用补丁失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleResolveConflict = async (conflictId: string, decision: string) => {
    if (!version) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      await api.createConflictDecision(projectId, version, conflictId, {
        decision,
        basis: 'artifact_viewer_review',
        authority: 'user',
      });
      await onArtifactsChanged?.();
      setRevisionSession((current) => current ? { ...current } : current);
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '裁决冲突失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleAcceptArtifact = async () => {
    if (!version || !activeDesignArtifact) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      await api.acceptDesignArtifact(projectId, version, activeDesignArtifact.artifact_id, {
        reviewer_note: 'Accepted from ArtifactViewer.',
        accepted_by: 'user',
      });
      await onArtifactsChanged?.();
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '接受当前版本失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleMarkSectionReview = async (status: string) => {
    if (!version || !activeDesignArtifact) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      const createdAnchor = discussionScope === 'selection' ? await ensureSelectionAnchor() : null;
      await api.markSectionReview(projectId, version, activeDesignArtifact.artifact_id, {
        status,
        anchor_id: createdAnchor?.anchor_id,
        reviewer_note: feedback || selectedExcerpt.slice(0, 180),
        revision_session_id: revisionSession?.revision_session_id,
      });
      await onArtifactsChanged?.();
      if (status === 'accepted') {
        setIsDrawerOpen(false);
      }
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '更新局部审阅状态失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const handleUpdateImpactStatus = async (impactId: string, status: string) => {
    if (!version) return;
    setIsWorking(true);
    setDrawerError(null);
    try {
      await api.updateImpactRecordStatus(projectId, version, impactId, status);
      await onArtifactsChanged?.();
    } catch (err: unknown) {
      setDrawerError(getApiErrorMessage(err, '更新下游影响状态失败。'));
    } finally {
      setIsWorking(false);
    }
  };

  const renderContent = () => {
    if (!selectedFile) return null;
    
    let content = artifacts[selectedFile] || '';
    
    // For JSON files, try to pretty print
    if (selectedFile.endsWith('.json')) {
      try {
        const parsed = JSON.parse(content);
        content = '```json\n' + JSON.stringify(parsed, null, 2) + '\n```';
      } catch {
        // Fallback to raw with highlighting if parse fails
        content = '```json\n' + content + '\n```';
      }
    } else if (selectedFile.endsWith('.sql')) {
      content = '```sql\n' + content + '\n```';
    } else if (selectedFile.endsWith('.yaml') || selectedFile.endsWith('.yml')) {
      content = '```yaml\n' + content + '\n```';
    }

    return (
      <div className="flex-1 overflow-auto bg-white rounded-2xl border border-gray-100 shadow-sm p-6 sm:p-10 min-h-[500px] animate-in fade-in zoom-in-95 duration-300">
        {activeDesignArtifact && (
          <div className="mb-6 border-b border-gray-100 pb-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0 flex-1">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-wider ${
                    governanceTone === 'rose' ? 'bg-rose-50 text-rose-700' : governanceTone === 'emerald' ? 'bg-emerald-50 text-emerald-700' : governanceTone === 'amber' ? 'bg-amber-50 text-amber-700' : 'bg-indigo-50 text-indigo-700'
                  }`}>
                    {overallReviewStatus === 'accepted' ? <CheckCircle2 size={12} /> : overallReviewStatus === 'blocked' ? <AlertTriangle size={12} /> : <ShieldAlert size={12} />}
                    {overallReviewStatus}
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-600">
                    v{activeDesignArtifact.artifact_version}
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-600">
                    {activeDesignArtifact.status}
                  </span>
                  {reflection && (
                    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-wider ${
                      reflection.status === 'passed' ? 'bg-emerald-50 text-emerald-700' : reflection.status === 'blocking' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'
                    }`}>
                      <ShieldAlert size={12} />
                      Reflection {reflection.status} · {Math.round((reflection.confidence || 0) * 100)}%
                    </span>
                  )}
                  {consistency && (
                    <span className={`rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-wider ${
                      consistency.status === 'passed' ? 'bg-emerald-50 text-emerald-700' : consistency.status === 'failed' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'
                    }`}>
                      System {consistency.status}
                    </span>
                  )}
                </div>
                <div className="grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="font-black text-slate-900">{blockingConflictCount}</div>
                    <div className="font-semibold text-slate-500">Blocking conflicts</div>
                  </div>
                  <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="font-black text-slate-900">{warningConflictCount}</div>
                    <div className="font-semibold text-slate-500">Warnings</div>
                  </div>
                  <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="font-black text-slate-900">{openImpactCount}</div>
                    <div className="font-semibold text-slate-500">Downstream impacts</div>
                  </div>
                  <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                    <div className="font-black text-slate-900">{disputedSectionCount}</div>
                    <div className="font-semibold text-slate-500">Section issues</div>
                  </div>
                </div>
              </div>
              <div className="grid gap-2 sm:grid-cols-3 xl:w-[360px]">
                <button
                  type="button"
                  onClick={handleAcceptArtifact}
                  disabled={!canDiscuss || isWorking || ['accepted', 'auto_accepted'].includes(activeDesignArtifact.status) || overallReviewStatus === 'blocked'}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-black text-white transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                  title="接受当前 Artifact 版本"
                >
                  <Check size={14} />
                  接受
                </button>
                <button
                  type="button"
                  onClick={() => handleStartArtifactDiscussion()}
                  disabled={!canDiscuss}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 transition-all hover:border-indigo-200 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  title="对整份产出发起讨论"
                >
                  <MessageSquareText size={14} />
                  讨论
                </button>
                <button
                  type="button"
                  onClick={handleCaptureSelection}
                  disabled={!canDiscuss}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 transition-all hover:border-indigo-200 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  title="选中文本后发起局部讨论"
                >
                  <GitCompare size={14} />
                  选区
                </button>
              </div>
            </div>
          </div>
        )}
        {consistencyConflicts.length > 0 && (
          <div className="mb-4 rounded-xl border border-rose-100 bg-rose-50 p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-rose-700">
              <AlertTriangle size={14} />
              Conflicts
            </div>
            <div className="space-y-2">
              {consistencyConflicts.slice(0, 3).map((conflict) => (
                <div key={conflict.conflict_id} className="rounded-lg bg-white/80 px-3 py-2 text-xs text-slate-700">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="font-bold text-slate-900">{conflict.summary}</div>
                      <div className="text-slate-500">{conflict.conflict_type} · {conflict.semantic} · {conflict.severity}</div>
                    </div>
                    {conflict.status === 'open' && (
                      <button
                        type="button"
                        onClick={() => handleStartArtifactDiscussion(`处理冲突：${conflict.summary}`)}
                        className="rounded-lg border border-rose-100 bg-white px-2 py-1 text-[10px] font-black text-rose-700 hover:bg-rose-50"
                      >
                        处理
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {decisionLogs.length > 0 && (
          <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">Decision Log</div>
            <div className="space-y-2">
              {decisionLogs.slice(0, 2).map((decision) => (
                <div key={decision.decision_id} className="rounded-lg bg-white px-3 py-2 text-xs text-slate-700">
                  <div className="font-bold text-slate-900">{decision.decision}</div>
                  <div className="text-slate-500">{decision.basis} · {decision.authority}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {(outgoingImpacts.length > 0 || incomingImpacts.length > 0) && (
          <div className="mb-4 rounded-xl border border-amber-100 bg-amber-50 p-3">
            <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-700">
              <GitBranch size={14} />
              Impact
            </div>
            {incomingImpacts.slice(0, 2).map((impact) => (
              <div key={impact.impact_id} className="mb-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-slate-700">
                <div className="font-bold text-slate-900">被上游影响：{impact.impact_status}</div>
                <div className="text-slate-500">{impact.reason}</div>
                {impact.impact_status !== 'no_impact' && (
                  <button
                    type="button"
                    onClick={() => handleUpdateImpactStatus(impact.impact_id, 'no_impact')}
                    className="mt-2 rounded-lg border border-amber-100 bg-white px-2 py-1 text-[10px] font-black text-amber-700 hover:bg-amber-50"
                  >
                    标记已校验
                  </button>
                )}
              </div>
            ))}
            {outgoingImpacts.slice(0, 2).map((impact) => (
              <div key={impact.impact_id} className="mb-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-slate-700">
                <div className="font-bold text-slate-900">影响下游：{impact.impact_status}</div>
                <div className="text-slate-500">{impact.reason}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => handleUpdateImpactStatus(impact.impact_id, 'needs_revalidation')}
                    className="rounded-lg border border-amber-100 bg-white px-2 py-1 text-[10px] font-black text-amber-700 hover:bg-amber-50"
                  >
                    需重校验
                  </button>
                  <button
                    type="button"
                    onClick={() => handleUpdateImpactStatus(impact.impact_id, 'needs_regeneration')}
                    className="rounded-lg border border-amber-100 bg-white px-2 py-1 text-[10px] font-black text-amber-700 hover:bg-amber-50"
                  >
                    需重跑
                  </button>
                  <button
                    type="button"
                    onClick={() => handleUpdateImpactStatus(impact.impact_id, 'no_impact')}
                    className="rounded-lg border border-amber-100 bg-white px-2 py-1 text-[10px] font-black text-amber-700 hover:bg-amber-50"
                  >
                    无影响
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {sectionReviews.length > 0 && (
          <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-500">Section Reviews</div>
            <div className="space-y-2">
              {sectionReviews.slice(0, 3).map((review) => (
                <div key={review.section_review_id} className="rounded-lg bg-white px-3 py-2 text-xs text-slate-700">
                  <div className="font-bold text-slate-900">{review.status}</div>
                  <div className="text-slate-500">{review.reviewer_note || review.anchor_id || 'Artifact-level note'}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="prose prose-sm prose-slate max-w-none prose-headings:text-gray-800 prose-headings:font-black prose-a:text-indigo-600 prose-strong:text-gray-900 prose-code:text-indigo-600 prose-pre:bg-transparent prose-pre:p-0">
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            components={{
              code: CodeBlock
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-wrap gap-2 mb-6">
        {filteredArtifacts.length > 0 ? (
          filteredArtifacts.map((filename) => (
            <button
              key={filename}
              onClick={() => onSelectFile(filename)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs transition-all ${
                selectedFile === filename
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-700 shadow-sm font-bold'
                  : 'bg-white border-gray-100 text-gray-500 hover:border-gray-200 hover:bg-gray-50'
              }`}
            >
              {getFileIcon(filename)}
              {filename}
            </button>
          ))
        ) : (
          <div className="w-full py-4 px-2 border border-dashed border-gray-200 rounded-xl flex items-center justify-center">
            <span className="text-xs font-medium text-gray-400 italic">
              {t('projectDetail.noArtifactsProduced') || 'No design artifacts produced yet for this node.'}
            </span>
          </div>
        )}
      </div>

      {renderContent()}

      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30 backdrop-blur-sm">
          <aside className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-5 py-4">
              <div>
                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-600">
                  {discussionScope === 'selection' ? 'Selection Review' : 'Artifact Review'}
                </div>
                <h3 className="text-base font-black text-slate-900">{selectedFile}</h3>
                {activeDesignArtifact && (
                  <div className="mt-1 text-xs font-semibold text-slate-500">
                    {activeDesignArtifact.expert_id} · v{activeDesignArtifact.artifact_version} · {activeDesignArtifact.status}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setIsDrawerOpen(false)}
                className="rounded-lg border border-slate-200 p-2 text-slate-400 hover:text-slate-700"
                title="关闭"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-5 p-5">
              {drawerError && (
                <div className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
                  {drawerError}
                </div>
              )}

              {discussionScope === 'selection' ? (
                <section className="space-y-2">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Selected Range</div>
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
                    {selectedExcerpt || '未捕获选区'}
                  </pre>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => handleMarkSectionReview('accepted')}
                      disabled={isWorking || !selectedExcerpt.trim()}
                      className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                    >
                      标记局部已接受
                    </button>
                    <button
                      type="button"
                      onClick={() => handleMarkSectionReview('disputed')}
                      disabled={isWorking || !selectedExcerpt.trim()}
                      className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-black text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                    >
                      标记局部有疑问
                    </button>
                  </div>
                </section>
              ) : (
                <section className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Scope</div>
                  <div className="mt-1 text-sm font-bold text-slate-800">整份产出</div>
                </section>
              )}

              <section className="space-y-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Feedback</label>
                <textarea
                  value={feedback}
                  onChange={(event) => setFeedback(event.target.value)}
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  placeholder="说明你想补充、质疑或修改什么"
                />
              </section>

              {!revisionSession && (
                <button
                  type="button"
                  onClick={handleStartRevision}
                  disabled={isWorking || !selectedExcerpt.trim()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-black text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
                >
                  <Wand2 size={16} />
                  {isWorking ? '处理中...' : '形成修订意图'}
                </button>
              )}

              {revisionSession && (
                <section className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
                  <div className="text-[10px] font-black uppercase tracking-widest text-indigo-600">Intent</div>
                  <div className="mt-2 text-sm font-semibold text-slate-800">
                    {String(normalizedIntent.revision_type || 'supplement')}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {String(normalizedIntent.revision_reason || '已记录结构化修订意图。')}
                  </div>
                </section>
              )}

              {revisionSession && candidateConflictCount > 0 && (
                <section className={`space-y-3 rounded-xl border p-4 ${
                  decisionRequired ? 'border-rose-100 bg-rose-50' : 'border-amber-100 bg-amber-50'
                }`}>
                  <div className={`inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest ${
                    decisionRequired ? 'text-rose-700' : 'text-amber-700'
                  }`}>
                    <ShieldAlert size={14} />
                    Context Conflict
                  </div>
                  <div className="text-sm font-bold text-slate-800">
                    {decisionRequired ? '需要先裁决，再判断是否影响下游产物' : '检测到 To-Be 或待确认差异'}
                  </div>
                  <div className="text-xs leading-5 text-slate-600">
                    系统判定：{String(normalizedIntent.semantic || 'missing_context')} · 候选冲突 {candidateConflictCount} 个
                  </div>
                  <div className="grid gap-2 text-xs font-semibold text-slate-700">
                    <div className="rounded-lg bg-white/70 px-3 py-2">作为目标设计继续，并生成变更建议</div>
                    <div className="rounded-lg bg-white/70 px-3 py-2">按当前资产事实调整专家产出</div>
                    <div className="rounded-lg bg-white/70 px-3 py-2">先标记待确认，用户修订后再评估下游影响</div>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => handleResolveConflict(String(candidateConflictIds[0] || ''), 'to_be')}
                      disabled={isWorking || candidateConflictIds.length === 0}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                    >
                      作为 To-Be 目标
                    </button>
                    <button
                      type="button"
                      onClick={() => handleResolveConflict(String(candidateConflictIds[0] || ''), 'as_is')}
                      disabled={isWorking || candidateConflictIds.length === 0}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                    >
                      以当前事实为准
                    </button>
                  </div>
                </section>
              )}

              {revisionSession && (
                <section className="space-y-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Replacement</label>
                  <textarea
                    value={replacementText}
                    onChange={(event) => setReplacementText(event.target.value)}
                    rows={7}
                    disabled={discussionScope !== 'selection'}
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 font-mono text-xs outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  />
                  <button
                    type="button"
                    onClick={handleCreatePatchPreview}
                    disabled={isWorking || discussionScope !== 'selection' || !replacementText.trim()}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-black text-slate-700 hover:border-indigo-200 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <GitCompare size={16} />
                    {isWorking ? '处理中...' : '生成 Patch Preview'}
                  </button>
                </section>
              )}

              {patchPreview && (
                <section className="space-y-3 rounded-xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Patch Preview</div>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black text-slate-600">
                      {patchPreview.patch_status}
                    </span>
                  </div>
                  <pre className="max-h-64 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                    {(patchPreview.diff.unified_diff || []).join('\n') || 'No diff.'}
                  </pre>
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600">
                    Policy: {patchPreview.preserve_policy}
                  </div>
                  <button
                    type="button"
                    onClick={handleApplyPatch}
                    disabled={isWorking || patchPreview.patch_status === 'applied'}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-black text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
                  >
                    <Check size={16} />
                    {patchPreview.patch_status === 'applied' ? '已应用并生成新版本' : isWorking ? '应用中...' : '应用补丁'}
                  </button>
                </section>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
};
