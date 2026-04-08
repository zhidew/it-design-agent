import {
  type ExpertLike,
  type ExpertImpactOverlap,
  type ExpertReverseImpact,
  getExpertDisplayName,
  getResolvedExpertReverseImpact,
} from '../utils/expertReverseImpact';

type ExpertReverseImpactPanelProps = {
  expertId: string;
  experts: ExpertLike[];
  impact?: ExpertReverseImpact | null;
  title?: string;
  isZh?: boolean;
};

const panelStyle = {
  border: '1px solid rgba(148, 163, 184, 0.35)',
  borderRadius: '12px',
  padding: '16px',
  background: 'rgba(248, 250, 252, 0.9)',
} as const;

const titleStyle = {
  margin: 0,
  fontSize: '15px',
  fontWeight: 600,
  color: '#0f172a',
} as const;

const subtitleStyle = {
  margin: '6px 0 0',
  fontSize: '13px',
  lineHeight: 1.5,
  color: '#475569',
} as const;

const sectionTitleStyle = {
  margin: 0,
  fontSize: '13px',
  fontWeight: 600,
  color: '#334155',
} as const;

const listStyle = {
  margin: '8px 0 0',
  paddingLeft: '18px',
  color: '#1e293b',
  fontSize: '13px',
  lineHeight: 1.6,
} as const;

const emptyTextStyle = {
  margin: '8px 0 0',
  fontSize: '13px',
  lineHeight: 1.5,
  color: '#64748b',
} as const;

const sectionGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: '12px',
  marginTop: '16px',
} as const;

const overlapCardStyle = {
  border: '1px solid rgba(148, 163, 184, 0.28)',
  borderRadius: '10px',
  background: '#ffffff',
  padding: '12px',
} as const;

const overlapMetaStyle = {
  margin: '6px 0 0',
  fontSize: '12px',
  lineHeight: 1.5,
  color: '#475569',
} as const;

const renderExpertIdList = (experts: ExpertLike[], expertIds: string[]) => {
  if (expertIds.length === 0) {
    return <p style={emptyTextStyle}>None detected.</p>;
  }

  return (
    <ul style={listStyle}>
      {expertIds.map((expertId) => (
        <li key={expertId}>{getExpertDisplayName(experts, expertId)}</li>
      ))}
    </ul>
  );
};

const renderOverlapList = (
  experts: ExpertLike[],
  overlaps: ExpertImpactOverlap[],
  emptyCopy: string,
  sharedLabel: string,
  pickValues: (overlap: ExpertImpactOverlap) => string[],
) => {
  if (overlaps.length === 0) {
    return <p style={emptyTextStyle}>{emptyCopy}</p>;
  }

  return (
    <div style={{ display: 'grid', gap: '10px', marginTop: '8px' }}>
      {overlaps.map((overlap) => (
        <div key={`${sharedLabel}-${overlap.related_expert_id}`} style={overlapCardStyle}>
          <p style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
            {getExpertDisplayName(experts, overlap.related_expert_id)}
          </p>
          <p style={overlapMetaStyle}>{sharedLabel}: {pickValues(overlap).join(', ')}</p>
        </div>
      ))}
    </div>
  );
};

export function ExpertReverseImpactPanel({
  expertId,
  experts,
  impact,
  title = 'Reverse impact analysis',
  isZh = false,
}: ExpertReverseImpactPanelProps) {
  const resolvedImpact = getResolvedExpertReverseImpact(experts, expertId, impact);
  const copy = isZh
    ? {
        title,
        helper: '在推进依赖评审前，先确认这个专家会影响哪些下游专家、产物消费者以及边界/产出重叠。',
        empty: '当前未检测到受影响专家或重叠风险。',
        directDownstream: '直接下游专家',
        fullDownstream: '完整下游链路',
        artifactConsumers: '消费该专家产物的专家',
        outputOverlap: '产出重叠',
        boundaryOverlap: '边界重叠',
        none: '未发现',
        noOutputOverlap: '未发现产出重叠。',
        noBoundaryOverlap: '未发现边界重叠。',
        sharedOutputs: '共享产出',
        sharedOwnership: '共享边界所有权',
      }
    : {
        title,
        helper:
          'Review downstream experts, artifact consumers, and scope overlaps before promoting this expert through dependency review.',
        empty: 'No impacted experts or overlap risks were detected for the selected expert.',
        directDownstream: 'Direct downstream experts',
        fullDownstream: 'Full downstream chain',
        artifactConsumers: 'Artifact consumers',
        outputOverlap: 'Output overlap',
        boundaryOverlap: 'Boundary overlap',
        none: 'None detected.',
        noOutputOverlap: 'No output overlap detected.',
        noBoundaryOverlap: 'No boundary overlap detected.',
        sharedOutputs: 'Shared outputs',
        sharedOwnership: 'Shared ownership',
      };

  if (!resolvedImpact) {
    return null;
  }

  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>{copy.title}</h3>
      <p style={subtitleStyle}>{copy.helper}</p>
      {!resolvedImpact.review_required ? (
        <p style={{ ...emptyTextStyle, marginTop: '14px' }}>{copy.empty}</p>
      ) : (
        <>
          <div style={sectionGridStyle}>
            <div>
              <p style={sectionTitleStyle}>{copy.directDownstream}</p>
              {resolvedImpact.direct_downstream_expert_ids.length === 0 ? (
                <p style={emptyTextStyle}>{copy.none}</p>
              ) : (
                renderExpertIdList(experts, resolvedImpact.direct_downstream_expert_ids)
              )}
            </div>
            <div>
              <p style={sectionTitleStyle}>{copy.fullDownstream}</p>
              {resolvedImpact.all_downstream_expert_ids.length === 0 ? (
                <p style={emptyTextStyle}>{copy.none}</p>
              ) : (
                renderExpertIdList(experts, resolvedImpact.all_downstream_expert_ids)
              )}
            </div>
            <div>
              <p style={sectionTitleStyle}>{copy.artifactConsumers}</p>
              {resolvedImpact.artifact_consumer_expert_ids.length === 0 ? (
                <p style={emptyTextStyle}>{copy.none}</p>
              ) : (
                renderExpertIdList(experts, resolvedImpact.artifact_consumer_expert_ids)
              )}
            </div>
          </div>
          <div style={sectionGridStyle}>
            <div>
              <p style={sectionTitleStyle}>{copy.outputOverlap}</p>
              {renderOverlapList(
                experts,
                resolvedImpact.output_overlap,
                copy.noOutputOverlap,
                copy.sharedOutputs,
                (overlap) => overlap.shared_outputs,
              )}
            </div>
            <div>
              <p style={sectionTitleStyle}>{copy.boundaryOverlap}</p>
              {renderOverlapList(
                experts,
                resolvedImpact.boundary_overlap,
                copy.noBoundaryOverlap,
                copy.sharedOwnership,
                (overlap) => overlap.shared_boundary_owns,
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
