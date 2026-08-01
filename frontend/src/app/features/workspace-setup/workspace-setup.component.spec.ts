import { ComponentFixture, TestBed } from '@angular/core/testing';
import { OidcSecurityService } from 'angular-auth-oidc-client';
import { of } from 'rxjs';
import { WorkspaceApiService } from '../../core/api/workspace-api.service';
import {
  ProductCapabilities,
  RepositorySummary,
  UserSummary,
  WorkspaceSummary
} from '../../core/models/workspace.models';
import { WorkspaceSetupComponent } from './workspace-setup.component';

const user: UserSummary = {
  id: 'user-1',
  email: 'engineer@example.com',
  display_name: 'Engineer',
  auth_provider: 'oidc'
};

const workspace: WorkspaceSummary = {
  id: 'workspace-1',
  name: 'Platform Reliability',
  slug: 'platform-reliability',
  role: 'owner',
  repository_count: 1,
  member_count: 1,
  created_at: '2026-07-30T00:00:00Z'
};

const repository: RepositorySummary = {
  id: 'repository-1',
  workspace_id: workspace.id,
  provider: 'github',
  provider_repository_id: '1001',
  full_name: 'acme/commerce',
  default_branch: 'main',
  visibility: 'private',
  connection_state: 'connected',
  data_mode: 'connected',
  selected: true,
  last_synced_at: '2026-07-30T00:00:00Z',
  created_at: '2026-07-30T00:00:00Z'
};

const capabilities: ProductCapabilities = {
  environment: 'production',
  auth_provider: 'oidc',
  development_identity: false,
  synthetic_data: false,
  github_app: false,
  github_checks: false,
  email_delivery: 'smtp',
  connected_telemetry: false,
  oidc_authority: 'https://identity.example.com',
  oidc_client_id: 'deployguard-web',
  oidc_scope: 'openid profile email'
};

describe('WorkspaceSetupComponent', () => {
  let fixture: ComponentFixture<WorkspaceSetupComponent>;
  let component: WorkspaceSetupComponent;
  let api: Record<string, ReturnType<typeof vi.fn>>;
  let oidc: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    window.history.replaceState({}, '', '/?view=workspace');
    api = {
      capabilities: vi.fn(() => of(capabilities)),
      token: vi.fn(() => null),
      storeToken: vi.fn(),
      clearToken: vi.fn(),
      me: vi.fn(() => of(user)),
      workspaces: vi.fn(() => of([workspace])),
      repositories: vi.fn(() => of([repository])),
      selectContext: vi.fn(() =>
        of({
          workspace_id: workspace.id,
          repository_id: repository.id,
          scenario_id: 'github-repository-1'
        })
      ),
      members: vi.fn(() => of([])),
      connectorHealth: vi.fn(() => of([])),
      invitations: vi.fn(() => of([])),
      auditEvents: vi.fn(() => of([])),
      githubStatus: vi.fn(),
      connectedChanges: vi.fn(() => of([])),
      acceptInvitation: vi.fn(() => of(workspace))
    };
    oidc = {
      checkAuth: vi.fn(() => of({ isAuthenticated: false })),
      authorizeWithPopUp: vi.fn(),
      logoff: vi.fn(() => of(undefined))
    };

    await TestBed.configureTestingModule({
      imports: [WorkspaceSetupComponent],
      providers: [
        { provide: WorkspaceApiService, useValue: api },
        { provide: OidcSecurityService, useValue: oidc }
      ]
    }).compileComponents();
  });

  function create(): void {
    fixture = TestBed.createComponent(WorkspaceSetupComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  }

  it('parses a production invitation link before authentication', () => {
    window.history.replaceState(
      {},
      '',
      '/accept-invite?token=one-time-token'
    );

    create();

    expect(component.pendingInvitationToken()).toBe('one-time-token');
    expect(component.acceptForm.getRawValue().token).toBe('one-time-token');
    expect(api['acceptInvitation']).not.toHaveBeenCalled();
  });

  it('claims a parsed invitation after OIDC authentication', () => {
    window.history.replaceState(
      {},
      '',
      '/accept-invite?token=one-time-token'
    );
    oidc['checkAuth'].mockReturnValue(of({ isAuthenticated: true }));

    create();

    expect(api['acceptInvitation']).toHaveBeenCalledWith('one-time-token');
    expect(component.pendingInvitationToken()).toBeNull();
    expect(window.location.pathname).toBe('/');
    expect(new URL(window.location.href).searchParams.get('token')).toBeNull();
  });

  it('persists an explicit workspace selection before notifying the root', () => {
    create();
    component.user.set(user);
    const emitted = vi.fn();
    component.contextChanged.subscribe(emitted);

    component.selectWorkspace(workspace);

    expect(api['selectContext']).toHaveBeenCalledWith(
      workspace.id,
      repository.id
    );
    expect(emitted).toHaveBeenCalledWith({
      workspace_id: workspace.id,
      repository_id: repository.id,
      scenario_id: 'github-repository-1'
    });
  });
});
