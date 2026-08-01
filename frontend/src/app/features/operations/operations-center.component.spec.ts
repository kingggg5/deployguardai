import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { makeOverview } from '../../test-fixtures';
import { OperationsApiService } from '../../core/api/operations-api.service';
import { WorkspaceApiService } from '../../core/api/workspace-api.service';
import {
  OperationalEvent,
  OperatorNotification,
  RiskPolicy,
  ServiceRecord
} from '../../core/models/operations.models';
import {
  ProductCapabilities,
  RepositorySummary,
  WorkspaceSummary
} from '../../core/models/workspace.models';
import { OperationsCenterComponent } from './operations-center.component';

const workspace: WorkspaceSummary = {
  id: 'workspace-1',
  name: 'Platform Reliability',
  slug: 'platform-reliability',
  role: 'owner',
  repository_count: 1,
  member_count: 3,
  created_at: '2026-07-28T08:00:00Z'
};

const capabilities: ProductCapabilities = {
  environment: 'test',
  auth_provider: 'oidc',
  development_identity: false,
  github_app: true,
  github_checks: true,
  email_delivery: 'smtp',
  connected_telemetry: true,
  oidc_authority: 'https://id.example',
  oidc_client_id: 'deployguard',
  oidc_scope: 'openid profile email'
};

const repository: RepositorySummary = {
  id: 'repo-1',
  workspace_id: workspace.id,
  provider: 'github',
  provider_repository_id: '1001',
  full_name: 'acme/commerce',
  default_branch: 'main',
  visibility: 'private',
  connection_state: 'connected',
  data_mode: 'connected',
  selected: true,
  last_synced_at: '2026-07-29T08:00:00Z',
  created_at: '2026-07-28T08:00:00Z'
};

const serviceRecord: ServiceRecord = {
  id: 'service-1',
  workspace_id: workspace.id,
  name: 'Checkout API',
  slug: 'checkout-api',
  description: 'Coordinates checkout requests.',
  tier: 'tier_1',
  lifecycle: 'active',
  owner_team: 'Commerce Platform',
  repository_id: repository.id,
  dependencies: ['payments-api'],
  runbook_url: 'https://runbooks.example/checkout',
  tags: ['checkout'],
  created_at: '2026-07-28T08:00:00Z',
  updated_at: '2026-07-29T08:00:00Z'
};

const policy: RiskPolicy = {
  enabled: true,
  warn_threshold: 55,
  block_threshold: 80,
  require_tests: true,
  require_rollback: true,
  max_blast_radius: 8,
  version: 1,
  created_at: '2026-07-28T08:00:00Z',
  updated_at: '2026-07-29T08:00:00Z'
};

const eventRecord: OperationalEvent = {
  id: 'event-1',
  provider_event_id: 'github-1001',
  workspace_id: workspace.id,
  repository_id: repository.id,
  service_id: serviceRecord.id,
  incident_id: 'inc-checkout',
  source: 'github',
  event_type: 'deployment.completed',
  occurred_at: '2026-07-29T08:00:00Z',
  severity: 'warning',
  summary: 'Checkout deployment completed.',
  attributes: {},
  provenance: { delivery: 'signed_webhook' },
  ingestion_status: 'correlated',
  ingested_at: '2026-07-29T08:00:01Z'
};

const notification: OperatorNotification = {
  id: 'notification-1',
  workspace_id: workspace.id,
  user_id: 'user-1',
  kind: 'incident_lifecycle',
  title: 'Incident acknowledged',
  message: 'Checkout latency regression is being investigated.',
  resource_type: 'incident',
  resource_id: 'inc-checkout',
  read_at: null,
  created_at: '2026-07-29T08:01:00Z'
};

const operatorNote = {
  id: 'note-1',
  timestamp: '2026-07-29T08:02:00Z',
  type: 'note',
  title: 'Operator note',
  detail: 'Rollback validated.',
  service_id: null
};

describe('OperationsCenterComponent', () => {
  let fixture: ComponentFixture<OperationsCenterComponent>;
  let component: OperationsCenterComponent;
  let operationsApi: Record<string, ReturnType<typeof vi.fn>>;
  let workspaceApi: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    operationsApi = {
      services: vi.fn(() => of([serviceRecord])),
      createService: vi.fn(() =>
        of({ ...serviceRecord, id: 'service-2', slug: 'orders-worker', name: 'Orders Worker' })
      ),
      service: vi.fn(() => of(serviceRecord)),
      updateService: vi.fn(() => of(serviceRecord)),
      riskPolicy: vi.fn(() => of(policy)),
      updateRiskPolicy: vi.fn(() => of({ ...policy, version: 2 })),
      events: vi.fn(() => of([eventRecord])),
      deployments: vi.fn(() => of([])),
      createEvent: vi.fn(() => of(eventRecord)),
      updateIncidentLifecycle: vi.fn(() =>
        of({
          incident_id: 'inc-checkout',
          workspace_id: workspace.id,
          status: 'investigating',
          severity: 'sev2',
          assignee_user_id: null,
          resolved_at: null,
          timeline: []
        })
      ),
      addIncidentNote: vi.fn(() => of(operatorNote)),
      notifications: vi.fn(() => of([notification])),
      markNotificationRead: vi.fn(() =>
        of({ ...notification, read_at: '2026-07-29T08:03:00Z' })
      )
    };
    workspaceApi = {
      capabilities: vi.fn(() => of(capabilities)),
      workspaces: vi.fn(() => of([workspace])),
      currentContext: vi.fn(() =>
        of({
          workspace_id: workspace.id,
          repository_id: repository.id,
          scenario_id: 'checkout-latency'
        })
      ),
      selectContext: vi.fn((workspaceId: string, repositoryId: string | null) =>
        of({
          workspace_id: workspaceId,
          repository_id: repositoryId,
          scenario_id: null
        })
      ),
      repositories: vi.fn(() => of([repository])),
      members: vi.fn(() =>
        of([
          {
            user: {
              id: 'user-1',
              email: 'owner@example.com',
              display_name: 'Release Owner',
              auth_provider: 'oidc'
            },
            role: 'owner',
            joined_at: '2026-07-28T08:00:00Z'
          }
        ])
      ),
      token: vi.fn(() => 'session-token')
    };

    await TestBed.configureTestingModule({
      imports: [OperationsCenterComponent],
      providers: [
        { provide: OperationsApiService, useValue: operationsApi },
        { provide: WorkspaceApiService, useValue: workspaceApi }
      ]
    }).compileComponents();
  });

  function createComponent(): void {
    fixture = TestBed.createComponent(OperationsCenterComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('language', 'en');
    fixture.componentRef.setInput('incident', makeOverview().active_incident);
    fixture.detectChanges();
  }

  it('renders API-backed connection truth, catalog rows, and inbox state', () => {
    createComponent();
    const content = fixture.nativeElement.textContent as string;

    expect(content).toContain('Run the system from evidence, not assumptions');
    expect(content).toContain('GitHub App enabled');
    expect(content).toContain('Receiving events');
    expect(content).toContain('Checkout API');
    expect(content).toContain('1 unread');
    expect(content).toContain('Incident acknowledged');
  });

  it('prevents an invalid threshold order from reaching the API', () => {
    createComponent();
    component.setSection('policy');
    component.policyForm.patchValue({
      warnThreshold: 90,
      blockThreshold: 80
    });
    fixture.detectChanges();

    component.savePolicy();
    fixture.detectChanges();

    expect(component.policyForm.hasError('thresholdOrder')).toBe(true);
    expect(operationsApi['updateRiskPolicy']).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain(
      'Warn threshold must be lower than block threshold.'
    );
  });

  it('registers a validated service with normalized CSV metadata', () => {
    createComponent();
    component.serviceForm.setValue({
      name: 'Orders Worker',
      slug: 'orders-worker',
      description: 'Consumes orders.',
      tier: 'tier_2',
      lifecycle: 'active',
      ownerTeam: 'Fulfilment',
      repositoryId: repository.id,
      dependencies: ['service-1'],
      runbookUrl: 'https://runbooks.example/orders',
      tags: 'orders, worker'
    });

    component.createService();

    expect(operationsApi['createService']).toHaveBeenCalledWith(
      workspace.id,
      expect.objectContaining({
        slug: 'orders-worker',
        owner_team: 'Fulfilment',
        dependencies: ['service-1'],
        tags: ['orders', 'worker']
      })
    );
    expect(component.services()).toHaveLength(2);
    expect(component.notice()).toContain('Service registered');
  });

  it('sends event filters and marks an inbox row as read', () => {
    createComponent();
    component.eventFilterForm.patchValue({
      source: 'github',
      severity: 'warning',
      ingestionStatus: 'correlated'
    });
    component.applyEventFilters();

    expect(operationsApi['events']).toHaveBeenLastCalledWith(
      workspace.id,
      expect.objectContaining({
        source: 'github',
        severity: 'warning',
        ingestion_status: 'correlated',
        limit: 100
      })
    );

    component.markRead(notification);

    expect(operationsApi['markNotificationRead']).toHaveBeenCalledWith(
      notification.id
    );
    expect(component.unreadCount()).toBe(0);
  });

  it('persists workspace context before loading tenant-scoped controls', () => {
    const secondWorkspace: WorkspaceSummary = {
      ...workspace,
      id: 'workspace-2',
      name: 'Payments Reliability',
      slug: 'payments-reliability'
    };
    const secondRepository: RepositorySummary = {
      ...repository,
      id: 'repo-2',
      workspace_id: secondWorkspace.id,
      full_name: 'acme/payments'
    };
    workspaceApi['workspaces'].mockReturnValue(
      of([workspace, secondWorkspace])
    );
    workspaceApi['repositories'].mockImplementation((workspaceId: string) =>
      of(workspaceId === secondWorkspace.id ? [secondRepository] : [repository])
    );
    createComponent();
    const changed = vi.fn();
    component.contextChanged.subscribe(changed);

    component.selectWorkspaceId(secondWorkspace.id);

    expect(workspaceApi['selectContext']).toHaveBeenCalledWith(
      secondWorkspace.id,
      secondRepository.id
    );
    expect(changed).toHaveBeenCalledWith(
      expect.objectContaining({
        workspace_id: secondWorkspace.id,
        repository_id: secondRepository.id
      })
    );
    expect(component.activeWorkspace()?.id).toBe(secondWorkspace.id);
  });

  it('resets incident-scoped lifecycle and pending notes when incident changes', () => {
    createComponent();
    component.noteForm.setValue({ note: 'Rollback validated.' });
    component.addNote();
    component.lifecycle.set({
      incident_id: 'inc-checkout',
      workspace_id: workspace.id,
      status: 'investigating',
      severity: 'sev2',
      assignee_user_id: null,
      resolved_at: null,
      timeline: [operatorNote]
    });
    expect(component.incidentTimeline().map((entry) => entry.id)).toContain(
      operatorNote.id
    );

    const nextIncident = makeOverview('queue-backlog').active_incident!;
    fixture.componentRef.setInput('incident', nextIncident);
    fixture.detectChanges();

    expect(component.lifecycle()).toBeNull();
    expect(component.pendingTimeline()).toEqual([]);
    expect(component.incidentTimeline()).toEqual(nextIncident.timeline);
  });

  it('renders the authoritative lifecycle timeline returned by the API', () => {
    createComponent();
    const incident = makeOverview().active_incident!;
    const lifecycleEntry = {
      id: 'lifecycle-1',
      timestamp: '2026-07-29T08:04:00Z',
      type: 'lifecycle',
      title: 'Incident investigating',
      detail: 'Status changed from acknowledged to investigating.',
      service_id: null
    };
    operationsApi['updateIncidentLifecycle'].mockReturnValue(
      of({
        incident_id: incident.id,
        workspace_id: workspace.id,
        status: 'investigating',
        severity: 'sev2',
        assignee_user_id: null,
        resolved_at: null,
        timeline: [...incident.timeline, lifecycleEntry]
      })
    );

    component.lifecycleForm.setValue({
      status: 'investigating',
      severity: 'sev2',
      assigneeUserId: 'user-1'
    });
    component.updateLifecycle();
    component.setSection('incident');
    fixture.detectChanges();

    expect(component.incidentStatus()).toBe('investigating');
    expect(operationsApi['updateIncidentLifecycle']).toHaveBeenCalledWith(
      incident.id,
      expect.objectContaining({ assignee_user_id: 'user-1' })
    );
    expect(component.incidentTimeline().at(-1)?.id).toBe(lifecycleEntry.id);
    expect(fixture.nativeElement.textContent).toContain(
      'Incident investigating'
    );
  });

  it('locks lifecycle mutations after an incident is resolved', () => {
    const resolved = {
      ...makeOverview().active_incident,
      status: 'resolved' as const,
      resolved_at: '2026-07-29T09:00:00Z'
    };
    fixture = TestBed.createComponent(OperationsCenterComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('incident', resolved);
    fixture.detectChanges();
    component.setSection('incident');
    fixture.detectChanges();

    component.updateLifecycle();

    expect(component.isIncidentTerminal()).toBe(true);
    expect(operationsApi['updateIncidentLifecycle']).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain(
      'Lifecycle fields are locked'
    );
  });

  it('deduplicates a pending note when an authoritative refresh includes it', () => {
    createComponent();
    component.noteForm.setValue({ note: 'Rollback validated.' });
    component.addNote();
    expect(
      component.incidentTimeline().filter((entry) => entry.id === operatorNote.id)
    ).toHaveLength(1);

    const refreshed = makeOverview().active_incident!;
    fixture.componentRef.setInput('incident', {
      ...refreshed,
      timeline: [...refreshed.timeline, operatorNote]
    });
    fixture.detectChanges();

    expect(component.pendingTimeline()).toEqual([]);
    expect(
      component.incidentTimeline().filter((entry) => entry.id === operatorNote.id)
    ).toHaveLength(1);
  });

  it('renders explicit empty ledgers without inventing connections', () => {
    operationsApi['services'].mockReturnValue(of([]));
    operationsApi['events'].mockReturnValue(of([]));
    operationsApi['notifications'].mockReturnValue(of([]));
    workspaceApi['repositories'].mockReturnValue(of([]));
    createComponent();

    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('No services registered');
    expect(content).toContain('Inbox is empty');
    expect(content).toContain('Enabled · no events yet');
  });

  it('shows a recoverable authentication error state', () => {
    workspaceApi['workspaces'].mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 401,
            error: { detail: 'Authentication required' }
          })
      )
    );
    createComponent();
    fixture.detectChanges();

    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Authentication required');
    expect(content).toContain('Retry');
    expect(content).toContain('Start with an authenticated workspace');
  });
});
