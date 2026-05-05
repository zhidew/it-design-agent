import type { DesignArtifact, ImpactRecord, SectionReview } from '../api';

const sampleImpact: ImpactRecord = {
  impact_id: 'impact-1',
  project_id: 'demo',
  version_id: 'v1',
  source_artifact_id: 'artifact-schema',
  impacted_artifact_id: 'artifact-api',
  impact_status: 'needs_revalidation',
  trigger_type: 'revision',
  trigger_ref_id: 'patch-1',
  reason: 'Schema changed.',
  evidence: { change_type: 'schema_change' },
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:00:00Z',
};

const sampleSectionReview: SectionReview = {
  section_review_id: 'review-1',
  artifact_id: 'artifact-api',
  anchor_id: 'anchor-1',
  status: 'disputed',
  reviewer_note: 'Check address response.',
  revision_session_id: 'session-1',
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:00:00Z',
};

export const governanceFixture: DesignArtifact = {
  artifact_id: 'artifact-api',
  project_id: 'demo',
  version_id: 'v1',
  run_id: 'run-1',
  expert_id: 'api-design',
  artifact_type: 'md',
  artifact_version: 2,
  parent_artifact_id: 'artifact-api-v1',
  status: 'ready_for_review',
  title: 'api-design.md',
  file_name: 'api-design.md',
  file_path: 'artifacts/api-design.md',
  content_hash: 'hash-1',
  summary: 'API Design',
  reflection: {
    report_id: 'reflection-1',
    artifact_id: 'artifact-api',
    expert_id: 'api-design',
    status: 'warning',
    confidence: 0.82,
    checks: {
      coverage_check: { status: 'passed', message: 'Covered.' },
    },
    issues: [{ severity: 'warning', summary: 'Confirm address summary.' }],
    blocks_downstream: false,
    created_at: '2026-05-05T00:00:00Z',
  },
  consistency: {
    report_id: 'consistency-1',
    artifact_id: 'artifact-api',
    project_id: 'demo',
    version_id: 'v1',
    status: 'warning',
    checks: [{ check_id: 'artifact_vs_database_schema', status: 'warning', message: 'Review schema terms.' }],
    conflict_ids: ['conflict-1'],
    suggested_actions: ['Review warning before acceptance.'],
    created_at: '2026-05-05T00:00:00Z',
    conflicts: [
      {
        conflict_id: 'conflict-1',
        report_id: 'consistency-1',
        project_id: 'demo',
        version_id: 'v1',
        artifact_id: 'artifact-api',
        conflict_type: 'artifact_vs_context',
        semantic: 'missing_context',
        severity: 'warning',
        status: 'open',
        summary: 'Address response needs confirmation.',
        evidence_refs: [],
        suggested_actions: ['Discuss the affected selection.'],
        decision_id: null,
        created_at: '2026-05-05T00:00:00Z',
        updated_at: '2026-05-05T00:00:00Z',
      },
    ],
  },
  decision_logs: [],
  impact_records: [sampleImpact],
  incoming_impacts: [],
  section_reviews: [sampleSectionReview],
};

export const summarizeGovernanceFixture = (artifact: DesignArtifact) => {
  const openConflicts = artifact.consistency?.conflicts?.filter((conflict) => conflict.status === 'open') ?? [];
  const activeImpacts = [...(artifact.impact_records ?? []), ...(artifact.incoming_impacts ?? [])].filter(
    (impact) => impact.impact_status !== 'no_impact',
  );
  const disputedSections = (artifact.section_reviews ?? []).filter((review) => review.status !== 'accepted');
  return {
    openConflictCount: openConflicts.length,
    activeImpactCount: activeImpacts.length,
    disputedSectionCount: disputedSections.length,
    reviewStatus: openConflicts.some((conflict) => conflict.severity === 'blocking') ? 'blocked' : 'needs_review',
  };
};

const summary = summarizeGovernanceFixture(governanceFixture);
if (summary.openConflictCount !== 1 || summary.activeImpactCount !== 1 || summary.disputedSectionCount !== 1) {
  throw new Error('Governance fixture summary does not match expected UI counters.');
}
