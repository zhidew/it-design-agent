export type ExpertImpactOverlap = {
  related_expert_id: string;
  shared_outputs: string[];
  shared_boundary_owns: string[];
};

export type ExpertReverseImpact = {
  expert_id: string;
  direct_downstream_expert_ids: string[];
  all_downstream_expert_ids: string[];
  artifact_consumer_expert_ids: string[];
  output_overlap: ExpertImpactOverlap[];
  boundary_overlap: ExpertImpactOverlap[];
  review_required: boolean;
};

export type ExpertLike = {
  id?: string;
  name?: string;
  display_name?: string;
  title?: string;
  dependencies?: string[];
  upstream_artifacts?: string[];
  expected_outputs?: string[];
  boundary_owns?: string[];
  metadata?: {
    boundary_contract?: {
      owns?: string[];
    };
  };
};

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const asStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const readNestedArray = (record: Record<string, unknown>, path: string[]): string[] => {
  let current: unknown = record;

  for (const segment of path) {
    current = asRecord(current)[segment];
  }

  return asStringArray(current);
};

export const getExpertId = (expert: unknown): string => {
  const record = asRecord(expert);
  return typeof record.id === 'string' ? record.id : '';
};

export const getExpertDisplayName = (experts: ExpertLike[], expertId: string): string => {
  const expert = experts.find((item) => getExpertId(item) === expertId);

  if (!expert) {
    return expertId;
  }

  const displayName =
    typeof expert.display_name === 'string'
      ? expert.display_name
      : typeof expert.name === 'string'
        ? expert.name
        : typeof expert.title === 'string'
          ? expert.title
          : null;

  return displayName && displayName !== expertId ? `${displayName} (${expertId})` : expertId;
};

export const getExpertDependencies = (expert: unknown): string[] => {
  const record = asRecord(expert);
  return asStringArray(record.dependencies);
};

export const getExpertUpstreamArtifacts = (expert: unknown): string[] => {
  const record = asRecord(expert);
  return asStringArray(record.upstream_artifacts);
};

export const getExpertExpectedOutputs = (expert: unknown): string[] => {
  const record = asRecord(expert);
  return asStringArray(record.expected_outputs);
};

export const getExpertBoundaryOwns = (expert: unknown): string[] => {
  const record = asRecord(expert);

  return [
    ...readNestedArray(record, ['metadata', 'boundary_contract', 'owns']),
    ...asStringArray(record.boundary_owns),
  ].filter((value, index, array) => array.indexOf(value) === index);
};

export const buildExpertReverseImpact = (
  experts: ExpertLike[],
  expertId: string,
): ExpertReverseImpact | null => {
  if (!expertId) {
    return null;
  }

  const selectedExpert = experts.find((expert) => getExpertId(expert) === expertId);

  if (!selectedExpert) {
    return null;
  }

  const directDownstream = experts
    .filter((expert) => getExpertId(expert) !== expertId)
    .filter((expert) => getExpertDependencies(expert).includes(expertId))
    .map((expert) => getExpertId(expert))
    .filter(Boolean);

  const visited = new Set<string>();
  const queue = [...directDownstream];

  while (queue.length > 0) {
    const currentId = queue.shift();

    if (!currentId || visited.has(currentId)) {
      continue;
    }

    visited.add(currentId);

    experts
      .filter((expert) => getExpertId(expert) !== expertId)
      .filter((expert) => getExpertDependencies(expert).includes(currentId))
      .map((expert) => getExpertId(expert))
      .filter(Boolean)
      .forEach((downstreamId) => {
        if (!visited.has(downstreamId)) {
          queue.push(downstreamId);
        }
      });
  }

  const selectedOutputs = new Set(getExpertExpectedOutputs(selectedExpert));
  const selectedBoundaryOwns = new Set(getExpertBoundaryOwns(selectedExpert));

  const artifactConsumers = experts
    .filter((expert) => getExpertId(expert) !== expertId)
    .filter((expert) => getExpertUpstreamArtifacts(expert).includes(expertId))
    .map((expert) => getExpertId(expert))
    .filter(Boolean);

  const overlaps = experts
    .filter((expert) => getExpertId(expert) !== expertId)
    .map((expert) => {
      const relatedExpertId = getExpertId(expert);
      const sharedOutputs = getExpertExpectedOutputs(expert).filter((item) => selectedOutputs.has(item));
      const sharedBoundaryOwns = getExpertBoundaryOwns(expert).filter((item) => selectedBoundaryOwns.has(item));

      return {
        related_expert_id: relatedExpertId,
        shared_outputs: sharedOutputs,
        shared_boundary_owns: sharedBoundaryOwns,
      } satisfies ExpertImpactOverlap;
    })
    .filter((item) => item.related_expert_id);

  const outputOverlap = overlaps.filter((item) => item.shared_outputs.length > 0);
  const boundaryOverlap = overlaps.filter((item) => item.shared_boundary_owns.length > 0);

  return {
    expert_id: expertId,
    direct_downstream_expert_ids: directDownstream,
    all_downstream_expert_ids: Array.from(visited),
    artifact_consumer_expert_ids: artifactConsumers,
    output_overlap: outputOverlap,
    boundary_overlap: boundaryOverlap,
    review_required:
      directDownstream.length > 0 ||
      artifactConsumers.length > 0 ||
      outputOverlap.length > 0 ||
      boundaryOverlap.length > 0,
  };
};

export const getResolvedExpertReverseImpact = (
  experts: ExpertLike[],
  expertId: string,
  preferredImpact?: ExpertReverseImpact | null,
): ExpertReverseImpact | null => {
  if (preferredImpact?.expert_id === expertId) {
    return preferredImpact;
  }

  return buildExpertReverseImpact(experts, expertId);
};
