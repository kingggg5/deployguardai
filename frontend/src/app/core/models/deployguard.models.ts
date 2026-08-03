export type DataMode = 'synthetic' | 'connected';
export type RiskLevel = 'low' | 'moderate' | 'high' | 'critical';
export type DeploymentStatus =
  | 'planned'
  | 'analyzed'
  | 'deploying'
  | 'deployed'
  | 'rolled_back'
  | 'blocked'
  | string;
export type IncidentStatus = 'open' | 'investigating' | 'mitigated' | 'resolved' | string;
export type FeedbackVerdict = 'confirmed' | 'rejected' | 'partial';

export interface HealthResponse {
  status: string;
  database: string;
  service: string;
  data_mode: DataMode;
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  repository: string;
  data_mode: DataMode;
  is_active: boolean;
  active_change_id: string | null;
  active_incident_id: string | null;
}

export interface OverviewStats {
  open_incidents: number;
  high_risk_changes: number;
  services_monitored: number;
  evidence_quality: number;
}

export interface RiskDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  reason: string;
  evidence_ids: string[];
}

export interface RiskLedger {
  overall_score: number;
  level: RiskLevel;
  data_quality: number;
  dimensions: RiskDimension[];
  recommendations: string[];
}

export interface BlastRadiusNode {
  id: string;
  label: string;
  kind: 'service' | 'database' | 'queue' | 'external' | string;
  team: string;
  tier: string;
  health: 'healthy' | 'degraded' | 'critical' | 'unknown' | string;
  impact_score: number;
  hop_distance: number;
  evidence_ids: string[];
}

export interface BlastRadiusEdge {
  source: string;
  target: string;
  relation: string;
  confidence: number;
  active: boolean;
}

export interface BlastRadius {
  nodes: BlastRadiusNode[];
  edges: BlastRadiusEdge[];
}

export interface ChangeDetail {
  id: string;
  workspace_id?: string;
  repository_id?: string;
  scenario_id: string;
  data_mode: DataMode;
  analysis_schema_version: string;
  engine_version: string;
  scoring_policy_version: string;
  graph_version: string;
  title: string;
  repository: string;
  author: string;
  commit_sha: string;
  branch: string;
  created_at: string;
  deployment_status: DeploymentStatus;
  deployment_environment: string;
  changed_services: string[];
  files_changed: number;
  lines_added: number;
  lines_deleted: number;
  flags: string[];
  risk: RiskLedger;
  blast_radius: BlastRadius;
}

export interface IncidentTimelineEvent {
  id: string;
  timestamp: string;
  type: 'deploy' | 'symptom' | 'alert' | 'mitigation' | 'recovery' | 'feedback' | string;
  title: string;
  detail: string;
  service_id: string | null;
  actor_user_id?: string | null;
}

export interface IncidentEvidence {
  id: string;
  type: string;
  source: string;
  timestamp: string;
  summary: string;
  value: string | number | null;
  quality: number;
  service_id: string | null;
  supports: string[];
  contradicts: string[];
}

export interface IncidentHypothesis {
  id: string;
  rank: number;
  cause_service: string;
  cause: string;
  confidence: number;
  score: number;
  evidence_ids: string[];
  counter_evidence_ids: string[];
  reasoning: string;
  next_step: string;
  status: 'likely' | 'possible' | 'unsupported' | 'contradicted' | string;
}

export interface IncidentFeedback {
  verdict: FeedbackVerdict | string;
  hypothesis_id: string;
  note: string;
  submitted_at: string;
}

export interface IncidentDetail {
  id: string;
  scenario_id: string;
  data_mode: DataMode;
  analysis_schema_version: string;
  engine_version: string;
  scoring_policy_version: string;
  graph_version: string;
  title: string;
  severity: string;
  status: IncidentStatus;
  assignee_user_id?: string | null;
  started_at: string;
  resolved_at: string | null;
  affected_services: string[];
  correlated_change_id: string | null;
  summary: string;
  timeline: IncidentTimelineEvent[];
  evidence: IncidentEvidence[];
  hypotheses: IncidentHypothesis[];
  feedback: IncidentFeedback[];
}

export interface Overview {
  generated_at: string;
  data_mode: DataMode;
  active_scenario_id: string;
  stats: OverviewStats;
  active_change: ChangeDetail;
  active_incident: IncidentDetail | null;
}

export interface AnalyzeChangeRequest {
  title: string;
  repository: string;
  author: string;
  files_changed: number;
  lines_added: number;
  lines_deleted: number;
  changed_services: string[];
  flags: string[];
  test_coverage: number;
  rollback_ready: boolean;
  observability_score: number;
  previous_failures: number;
}

export interface FeedbackRequest {
  hypothesis_id: string;
  verdict: FeedbackVerdict;
  note: string;
}

export interface ApiErrorEnvelope {
  detail: string | { msg?: string }[];
  code?: string;
}

export interface TopologyPoint {
  id: string;
  x: number;
  y: number;
}

export interface DoraMetrics {
  period: string;
  deployment_frequency_per_week: number;
  change_lead_time_minutes: number;
  change_failure_rate: number;
  mean_time_to_restore_minutes: number;
  deployment_rework_rate: number;
  total_deployments: number;
  total_incidents: number;
}
