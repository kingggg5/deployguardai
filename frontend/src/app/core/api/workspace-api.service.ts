import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { DEPLOYGUARD_API_BASE } from '../config/deployguard-config';
import {
  AuditEventSummary,
  ConnectedChangeSummary,
  DevelopmentSession,
  InvitationCreated,
  InvitationSummary,
  GitHubConnectionSummary,
  GitHubRepositoryCandidate,
  MembershipSummary,
  ProductCapabilities,
  RepositorySummary,
  WorkspaceRole,
  WorkspaceSummary,
  UserContext,
  UserSummary
} from '../models/workspace.models';

@Injectable({ providedIn: 'root' })
export class WorkspaceApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = inject(DEPLOYGUARD_API_BASE);
  private readonly tokenKey = 'deployguard-development-session';

  capabilities(): Observable<ProductCapabilities> {
    return this.http.get<ProductCapabilities>(`${this.apiBase}/capabilities`);
  }

  me(): Observable<UserSummary> {
    return this.http.get<UserSummary>(`${this.apiBase}/auth/me`, {
      headers: this.headers()
    });
  }

  developmentSession(
    email?: string,
    displayName?: string
  ): Observable<DevelopmentSession> {
    return this.http.post<DevelopmentSession>(
      `${this.apiBase}/auth/development-session`,
      { email: email || null, display_name: displayName || null }
    );
  }

  storeToken(token: string): void {
    try {
      globalThis.localStorage?.setItem(this.tokenKey, token);
    } catch {
      // The user can still use the current in-memory response when storage is blocked.
    }
  }

  token(): string | null {
    try {
      return globalThis.localStorage?.getItem(this.tokenKey) ?? null;
    } catch {
      return null;
    }
  }

  clearToken(): void {
    try {
      globalThis.localStorage?.removeItem(this.tokenKey);
    } catch {
      // Storage is optional.
    }
  }

  workspaces(): Observable<WorkspaceSummary[]> {
    return this.http.get<WorkspaceSummary[]>(`${this.apiBase}/workspaces`, {
      headers: this.headers()
    });
  }

  currentContext(): Observable<UserContext> {
    return this.http.get<UserContext>(`${this.apiBase}/me/context`, {
      headers: this.headers()
    });
  }

  selectContext(
    workspaceId: string,
    repositoryId: string | null = null,
    scenarioId: string | null = null
  ): Observable<UserContext> {
    return this.http.put<UserContext>(
      `${this.apiBase}/me/context`,
      {
        workspace_id: workspaceId,
        repository_id: repositoryId,
        scenario_id: scenarioId
      },
      { headers: this.headers() }
    );
  }

  createWorkspace(name: string, slug: string): Observable<WorkspaceSummary> {
    return this.http.post<WorkspaceSummary>(
      `${this.apiBase}/workspaces`,
      { name, slug },
      { headers: this.headers() }
    );
  }

  repositories(workspaceId: string): Observable<RepositorySummary[]> {
    return this.http.get<RepositorySummary[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/repositories`,
      { headers: this.headers() }
    );
  }

  startGitHubInstall(
    workspaceId: string
  ): Observable<{ install_url: string; expires_at: string }> {
    return this.http.post<{ install_url: string; expires_at: string }>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/providers/github/install`,
      {},
      { headers: this.headers() }
    );
  }

  githubStatus(workspaceId: string): Observable<GitHubConnectionSummary> {
    return this.http.get<GitHubConnectionSummary>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/providers/github`,
      { headers: this.headers() }
    );
  }

  githubRepositories(
    workspaceId: string
  ): Observable<GitHubRepositoryCandidate[]> {
    return this.http.get<GitHubRepositoryCandidate[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/providers/github/repositories`,
      { headers: this.headers() }
    );
  }

  syncGitHubRepositories(
    workspaceId: string,
    repositoryIds: string[]
  ): Observable<{ imported: number; deselected: number; synced_at: string }> {
    return this.http.post<{
      imported: number;
      deselected: number;
      synced_at: string;
    }>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/providers/github/repositories/sync`,
      { repository_ids: repositoryIds },
      { headers: this.headers() }
    );
  }

  connectedChanges(
    workspaceId: string,
    repositoryId: string
  ): Observable<ConnectedChangeSummary[]> {
    return this.http.get<ConnectedChangeSummary[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/repositories/${encodeURIComponent(repositoryId)}/changes`,
      { headers: this.headers() }
    );
  }

  connectDevelopmentRepository(
    workspaceId: string,
    fullName: string,
    defaultBranch: string,
    visibility: string
  ): Observable<RepositorySummary> {
    return this.http.post<RepositorySummary>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/repositories`,
      {
        full_name: fullName,
        default_branch: defaultBranch,
        visibility
      },
      { headers: this.headers() }
    );
  }

  members(workspaceId: string): Observable<MembershipSummary[]> {
    return this.http.get<MembershipSummary[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/members`,
      { headers: this.headers() }
    );
  }

  invitations(workspaceId: string): Observable<InvitationSummary[]> {
    return this.http.get<InvitationSummary[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/invitations`,
      { headers: this.headers() }
    );
  }

  invite(
    workspaceId: string,
    email: string,
    role: Exclude<WorkspaceRole, 'owner'>
  ): Observable<InvitationCreated> {
    return this.http.post<InvitationCreated>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/invitations`,
      { email, role },
      { headers: this.headers() }
    );
  }

  revokeInvitation(
    workspaceId: string,
    invitationId: string
  ): Observable<InvitationSummary> {
    return this.http.delete<InvitationSummary>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/invitations/${encodeURIComponent(invitationId)}`,
      { headers: this.headers() }
    );
  }

  acceptInvitation(token: string): Observable<WorkspaceSummary> {
    return this.http.post<WorkspaceSummary>(
      `${this.apiBase}/invitations/accept`,
      { token },
      { headers: this.headers() }
    );
  }

  auditEvents(workspaceId: string): Observable<AuditEventSummary[]> {
    return this.http.get<AuditEventSummary[]>(
      `${this.apiBase}/workspaces/${encodeURIComponent(workspaceId)}/audit-events`,
      { headers: this.headers() }
    );
  }

  private headers(): HttpHeaders {
    const token = this.token();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }
}
