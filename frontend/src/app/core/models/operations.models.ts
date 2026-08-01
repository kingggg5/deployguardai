import { IncidentTimelineEvent } from './deployguard.models';

export type ServiceTier = 'tier_1' | 'tier_2' | 'tier_3' | 'tier_4';
export type ServiceLifecycle = 'active' | 'deprecated' | 'experimental';

export interface ServiceRecord {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string;
  tier: ServiceTier;
  lifecycle: ServiceLifecycle;
  owner_team: string;
  repository_id: string | null;
  dependencies: string[];
  runbook_url: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}
export interface ServiceCreateRequest {
  name: string;
  slug: string;
  description: string;
  tier: ServiceTier;
  lifecycle: ServiceLifecycle;
  owner_team: string;
  repository_id: string | null;
  dependencies: string[];
  runbook_url: string | null;
  tags: string[];
}

export type ServiceUpdateRequest = Partial<ServiceCreateRequest>;

export interface RiskPolicy {
  enabled: boolean;
  warn_threshold: number;
  block_threshold: number;
  require_tests: boolean;
  require_rollback: boolean;
  max_blast_radius: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RiskPolicyUpdateRequest {
  enabled: boolean;
  warn_threshold: number;
  block_threshold: number;
  require_tests: boolean;
  require_rollback: boolean;
  max_blast_radius: number;
  version: number;
}

export type EventSeverity = 'debug' | 'info' | 'warning' | 'error' | 'critical';
export type EventIngestionStatus = 'accepted' | 'correlated';

export interface OperationalEvent {
  id: string;
  provider_event_id: string;
  workspace_id: string;
  repository_id: string | null;
  service_id: string | null;
  incident_id: string | null;
  source: string;
  event_type: string;
  occurred_at: string;
  severity: EventSeverity;
  summary: string;
  attributes: Record<string, unknown>;
  provenance: Record<string, unknown>;
  ingestion_status: EventIngestionStatus;
  ingested_at: string;
}

export interface OperationalEventCreateRequest {
  provider_event_id: string;
  repository_id: string | null;
  service_id: string | null;
  incident_id: string | null;
  source: string;
  event_type: string;
  occurred_at: string;
  severity: EventSeverity;
  summary: string;
  attributes: Record<string, unknown>;
  provenance: Record<string, unknown>;
}

export interface OperationalEventFilters {
  source?: string;
  event_type?: string;
  severity?: EventSeverity;
  repository_id?: string;
  service_id?: string;
  ingestion_status?: EventIngestionStatus;
  occurred_after?: string;
  occurred_before?: string;
  limit?: number;
}

export type DeploymentStatus =
  | 'queued'
  | 'in_progress'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'inactive'
  | 'unknown';

export interface DeploymentRecord {
  id: string;
  workspace_id: string;
  repository_id: string;
  change_id: string | null;
  provider: string;
  provider_deployment_id: string;
  environment: string;
  commit_sha: string;
  ref: string | null;
  status: DeploymentStatus;
  provider_url: string | null;
  service_ids: string[];
  last_event_id: string | null;
  provider_created_at: string;
  provider_updated_at: string;
  finished_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DeploymentFilters {
  repository_id?: string;
  environment?: string;
  status?: DeploymentStatus;
  limit?: number;
}

export type IncidentLifecycleStatus =
  | 'open'
  | 'acknowledged'
  | 'investigating'
  | 'mitigated'
  | 'resolved';
export type IncidentSeverity = 'sev1' | 'sev2' | 'sev3' | 'sev4';

export interface IncidentLifecycleUpdateRequest {
  status?: IncidentLifecycleStatus;
  assignee_user_id?: string;
  severity?: IncidentSeverity;
}

export interface IncidentLifecycle {
  incident_id: string;
  workspace_id: string;
  status: IncidentLifecycleStatus;
  severity: IncidentSeverity;
  assignee_user_id: string | null;
  resolved_at: string | null;
  timeline: IncidentTimelineEvent[];
}

export interface IncidentNoteRequest {
  note: string;
}

export type NotificationKind = 'incident_lifecycle' | 'incident_note';

export interface OperatorNotification {
  id: string;
  workspace_id: string;
  user_id: string;
  kind: NotificationKind;
  title: string;
  message: string;
  resource_type: string;
  resource_id: string;
  read_at: string | null;
  created_at: string;
}
