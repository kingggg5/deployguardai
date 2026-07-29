export type WorkspaceRole = 'viewer' | 'responder' | 'admin' | 'owner';

export interface UserSummary {
  id: string;
  email: string;
  display_name: string;
  auth_provider: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  role: WorkspaceRole;
  repository_count: number;
  member_count: number;
  created_at: string;
}

export interface UserContext {
  workspace_id: string | null;
  repository_id: string | null;
  scenario_id: string | null;
}

export interface DevelopmentSession {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  provider: 'development';
  user: UserSummary;
  workspaces: WorkspaceSummary[];
}

export interface RepositorySummary {
  id: string;
  workspace_id: string;
  provider: 'development' | 'github';
  provider_repository_id: string;
  full_name: string;
  default_branch: string;
  visibility: string;
  connection_state: string;
  data_mode: 'synthetic' | 'connected';
  selected: boolean;
  last_synced_at: string | null;
  created_at: string;
}

export interface MembershipSummary {
  user: UserSummary;
  role: WorkspaceRole;
  joined_at: string;
}

export interface InvitationSummary {
  id: string;
  workspace_id: string;
  email: string;
  role: Exclude<WorkspaceRole, 'owner'>;
  status: 'pending' | 'accepted' | 'revoked' | 'expired';
  created_at: string;
  expires_at: string;
}

export interface InvitationCreated extends InvitationSummary {
  delivery_mode: 'smtp' | 'development_outbox' | 'disabled';
  delivery_status: 'sent' | 'failed' | 'development_outbox' | 'disabled';
  claim_token?: string;
  accept_path?: string;
}

export interface ProductCapabilities {
  environment: string;
  auth_provider: 'development' | 'oidc' | 'disabled';
  development_identity: boolean;
  github_app: boolean;
  github_checks: boolean;
  email_delivery: 'smtp' | 'development_outbox' | 'disabled';
  connected_telemetry: boolean;
  oidc_authority: string | null;
  oidc_client_id: string | null;
  oidc_scope: string | null;
}

export interface GitHubConnectionSummary {
  id: string;
  workspace_id: string;
  installation_id: string;
  account_login: string;
  account_type: string;
  connection_state: string;
  permissions: Record<string, string>;
  repository_selection: string;
  last_synced_at: string | null;
  error_code: string | null;
}

export interface GitHubRepositoryCandidate {
  provider_repository_id: string;
  full_name: string;
  default_branch: string;
  visibility: 'private' | 'internal' | 'public';
  html_url: string;
  archived: boolean;
  selected: boolean;
  pushed_at: string | null;
}

export interface ConnectedChangeSummary {
  id: string;
  title: string;
  repository: string;
  author: string;
  created_at: string;
  data_mode: 'connected';
  risk: {
    overall_score: number;
    level: 'low' | 'moderate' | 'high' | 'critical';
  };
}

export interface AuditEventSummary {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  request_id: string;
  event_metadata: Record<string, unknown>;
  created_at: string;
}
