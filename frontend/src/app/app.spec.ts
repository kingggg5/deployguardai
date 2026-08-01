import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';
import { App } from './app';
import { DeployGuardApiService } from './core/api/deployguard-api.service';
import { WorkspaceApiService } from './core/api/workspace-api.service';
import { doraMetricsFixture, makeOverview, scenarioFixtures } from './test-fixtures';

describe('DeployGuard investigation ledger', () => {
  let fixture: ComponentFixture<App>;
  let component: App;
  let api: {
    getScenarios: ReturnType<typeof vi.fn>;
    getOverview: ReturnType<typeof vi.fn>;
    getDoraMetrics: ReturnType<typeof vi.fn>;
    activateScenario: ReturnType<typeof vi.fn>;
    submitFeedback: ReturnType<typeof vi.fn>;
    analyzeChange: ReturnType<typeof vi.fn>;
    getChange: ReturnType<typeof vi.fn>;
    exportPostMortem: ReturnType<typeof vi.fn>;
  };
  let workspaceApi: {
    workspaces: ReturnType<typeof vi.fn>;
    repositories: ReturnType<typeof vi.fn>;
    currentContext: ReturnType<typeof vi.fn>;
    selectContext: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    window.history.replaceState({}, '', '/');
    api = {
      getScenarios: vi.fn(() => of(scenarioFixtures)),
      getOverview: vi.fn(() => of(makeOverview())),
      getDoraMetrics: vi.fn(() => of(doraMetricsFixture)),
      activateScenario: vi.fn(() => of(makeOverview('queue-backlog'))),
      analyzeChange: vi.fn(() => of(makeOverview().active_change)),
      getChange: vi.fn(() => of(makeOverview().active_change)),
      exportPostMortem: vi.fn(() => of('# Incident Post-Mortem')),
      submitFeedback: vi.fn(() =>
        of(
          makeOverview('checkout-latency', [
            {
              hypothesis_id: 'hyp-db',
              verdict: 'confirmed',
              note: 'The lock holder matches the changed transaction.',
              submitted_at: '2026-07-26T12:04:00Z'
            }
          ]).active_incident!
        )
      )
    };
    workspaceApi = {
      workspaces: vi.fn(() =>
        of([
          {
            id: 'workspace-1',
            name: 'Platform Reliability',
            slug: 'platform-reliability',
            role: 'owner',
            repository_count: 1,
            member_count: 2,
            created_at: '2026-07-26T10:00:00Z'
          }
        ])
      ),
      repositories: vi.fn(() =>
        of([
          {
            id: 'repository-1',
            workspace_id: 'workspace-1',
            provider: 'github',
            provider_repository_id: '1001',
            full_name: 'acme/commerce',
            default_branch: 'main',
            visibility: 'private',
            connection_state: 'connected',
            data_mode: 'connected',
            selected: true,
            last_synced_at: '2026-07-26T10:00:00Z',
            created_at: '2026-07-26T10:00:00Z'
          }
        ])
      ),
      currentContext: vi.fn(() =>
        of({
          workspace_id: 'workspace-1',
          repository_id: 'repository-1',
          scenario_id: 'checkout-latency'
        })
      ),
      selectContext: vi.fn(() =>
        of({
          workspace_id: 'workspace-1',
          repository_id: 'repository-1',
          scenario_id: 'checkout-latency'
        })
      )
    };

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        { provide: DeployGuardApiService, useValue: api },
        { provide: WorkspaceApiService, useValue: workspaceApi }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(App);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('renders the loaded synthetic investigation with ranked evidence', () => {
    const content = fixture.nativeElement.textContent as string;
    expect(content).toContain('Synthetic data');
    expect(content).toContain('acme/commerce');
    expect(content).toContain('Checkout latency regression');
    expect(content).toContain('Root-cause hypotheses');
    expect(content).toContain('Order persistence lock contention');
  });

  it('opens workspace activation without requiring an overview first', () => {
    api.getOverview.mockClear();
    api.getScenarios.mockClear();
    component.activeTab.set('workspace');
    component.overview.set(null);
    component.isLoading.set(true);

    component.ngOnInit();

    expect(component.isLoading()).toBe(false);
    expect(api.getOverview).not.toHaveBeenCalled();
    expect(api.getScenarios).not.toHaveBeenCalled();
  });

  it('switches scenario through the API and replaces the active overview', () => {
    component.setActiveTab('scenarios');
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll(
      '.scenario-action'
    ) as NodeListOf<HTMLButtonElement>;
    expect(buttons).toHaveLength(2);
    buttons[1].click();
    fixture.detectChanges();
    component.setActiveTab('investigation');
    fixture.detectChanges();

    expect(api.activateScenario).toHaveBeenCalledWith('queue-backlog');
    expect(component.activeScenarioId()).toBe('queue-backlog');
    expect(fixture.nativeElement.textContent).toContain('Worker queue saturation');
  });

  it('keeps SVG node geometry fixed when Evidence X-ray is toggled', () => {
    const nodesBefore = fixture.nativeElement.querySelectorAll(
      '.topology-node'
    ) as NodeListOf<SVGGElement>;
    const transformsBefore = Array.from(nodesBefore).map((node) =>
      node.getAttribute('transform')
    );

    component.toggleEvidenceXray();
    fixture.detectChanges();

    const nodesAfter = fixture.nativeElement.querySelectorAll(
      '.topology-node'
    ) as NodeListOf<SVGGElement>;
    const transformsAfter = Array.from(nodesAfter).map((node) =>
      node.getAttribute('transform')
    );
    expect(transformsAfter).toEqual(transformsBefore);
    expect(fixture.nativeElement.textContent).toContain('impact 95');
  });

  it('falls back to service evidence when topology evidence ids are not incident ids', () => {
    const current = component.overview();
    expect(current).not.toBeNull();
    if (!current) return;

    component.overview.set({
      ...current,
      active_change: {
        ...current.active_change,
        blast_radius: {
          ...current.active_change.blast_radius,
          nodes: current.active_change.blast_radius.nodes.map((node) =>
            node.id === 'checkout-api'
              ? { ...node, evidence_ids: ['topology-checkout-api'] }
              : node
          )
        }
      }
    });
    component.selectedHypothesisId.set(null);
    component.selectedNodeId.set('checkout-api');

    expect(component.visibleEvidence().map((item) => item.id)).toEqual([
      'ev-trace'
    ]);
  });

  it('submits a non-empty human verdict and applies the returned incident', () => {
    component.feedbackNote.set('The lock holder matches the changed transaction.');
    component.submitFeedback('confirmed');
    fixture.detectChanges();

    expect(api.submitFeedback).toHaveBeenCalledWith('inc-checkout', {
      hypothesis_id: 'hyp-db',
      verdict: 'confirmed',
      note: 'The lock holder matches the changed transaction.'
    });
    expect(component.feedbackForSelectedHypothesis()).toHaveLength(1);
    expect(component.feedbackSuccess()).toContain('Verdict recorded');
  });

  it('pauses replay without discarding the selected event', () => {
    component.scrubReplay(0);
    component.startReplay();
    component.pauseReplay();

    expect(component.isReplaying()).toBe(false);
    expect(component.replayIndex()).toBe(0);
  });

  it('submits a complete manual change analysis through the API', () => {
    component.updateAnalysisDraft({
      title: 'Validate checkout cache policy',
      repository: 'acme/commerce',
      author: 'platform-team',
      changedServices: ['checkout-api'],
      filesChanged: 4,
      linesAdded: 80,
      linesDeleted: 12,
      testCoveragePercent: 86,
      observabilityPercent: 92
    });

    component.submitChangeAnalysis();

    expect(api.analyzeChange).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Validate checkout cache policy',
        changed_services: ['checkout-api'],
        test_coverage: 0.86,
        observability_score: 0.92
      })
    );
    expect(component.analysisResult()).not.toBeNull();
  });

  it('switches repository from the scope selector through the scenario API', () => {
    const trigger = fixture.nativeElement.querySelector(
      '.scope-trigger'
    ) as HTMLButtonElement;
    trigger.click();
    fixture.detectChanges();

    const options = fixture.nativeElement.querySelectorAll(
      '.scope-option'
    ) as NodeListOf<HTMLButtonElement>;
    options[1].click();
    fixture.detectChanges();

    expect(api.activateScenario).toHaveBeenCalledWith('queue-backlog');
  });

  it('copies a deep link containing the current view and scenario', async () => {
    const writeText = vi.fn((value: string) => {
      void value;
      return Promise.resolve();
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    });

    component.setActiveTab('dora');
    await component.copyCurrentView();

    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('view=dora')
    );
    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('scenario=checkout-latency')
    );
    expect(component.shareSuccess()).toContain('View link copied');
  });

  it('builds an immutable tenant-scoped link when sharing change risk', async () => {
    const writeText = vi.fn((value: string) => {
      void value;
      return Promise.resolve();
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    });

    component.setActiveTab('change_risk');
    await component.copyCurrentView();

    const copied = new URL(writeText.mock.calls[0][0]);
    expect(copied.searchParams.get('change')).toBe(
      makeOverview().active_change.id
    );
    expect(copied.searchParams.get('workspace')).toBe('workspace-1');
    expect(copied.searchParams.get('repository')).toBe('repository-1');
  });

  it('selects and validates tenant context before resolving an immutable change', () => {
    const linkedChange = {
      ...makeOverview().active_change,
      id: 'change-linked',
      title: 'Pinned checkout rollout',
      workspace_id: 'workspace-1',
      repository_id: 'repository-1',
      // Domain display metadata does not need to equal the provider full name.
      repository: 'logical/checkout-domain'
    };
    api.getChange.mockReturnValue(of(linkedChange));
    window.history.replaceState(
      {},
      '',
      '/?view=change_risk&change=change-linked&workspace=workspace-1&repository=repository-1'
    );

    component.restoreViewFromUrl();
    fixture.detectChanges();

    expect(workspaceApi.selectContext).toHaveBeenCalledWith(
      'workspace-1',
      'repository-1',
      null
    );
    expect(api.getChange).toHaveBeenCalledWith('change-linked');
    expect(workspaceApi.selectContext.mock.invocationCallOrder[0]).toBeLessThan(
      api.getChange.mock.invocationCallOrder[0]
    );
    expect(component.displayedRiskChange()?.id).toBe('change-linked');
    expect(fixture.nativeElement.textContent).toContain(
      'Pinned checkout rollout'
    );
    expect(window.location.search).toContain('change=change-linked');
  });

  it('resolves a change-only link inside the persisted tenant context', () => {
    const linkedChange = {
      ...makeOverview().active_change,
      id: 'change-current-context'
    };
    api.getChange.mockReturnValue(of(linkedChange));
    window.history.replaceState(
      {},
      '',
      '/?view=change_risk&change=change-current-context'
    );

    component.restoreViewFromUrl();

    expect(workspaceApi.currentContext).toHaveBeenCalled();
    expect(api.getChange).toHaveBeenCalledWith('change-current-context');
    expect(component.displayedRiskChange()?.id).toBe(
      'change-current-context'
    );
  });

  it('does not fetch or fall back when a linked repository is outside the tenant scope', () => {
    api.getChange.mockClear();
    window.history.replaceState(
      {},
      '',
      '/?view=change_risk&change=change-private&workspace=workspace-1&repository=repository-private'
    );

    component.restoreViewFromUrl();
    fixture.detectChanges();

    expect(api.getChange).not.toHaveBeenCalled();
    expect(component.hasImmutableChangeTarget()).toBe(true);
    expect(component.linkedChange()).toBeNull();
    expect(component.displayedRiskChange()).toBeNull();
    expect(component.loadError()).toContain(
      'repository in this change link is not available'
    );
  });

  it('does not silently replace a missing linked change with the active change', () => {
    api.getChange.mockReturnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 404,
            error: { detail: 'Change not found' }
          })
      )
    );
    window.history.replaceState(
      {},
      '',
      '/?view=change_risk&change=change-missing&workspace=workspace-1&repository=repository-1'
    );

    component.restoreViewFromUrl();

    expect(component.hasImmutableChangeTarget()).toBe(true);
    expect(component.linkedChange()).toBeNull();
    expect(component.displayedRiskChange()).toBeNull();
    expect(component.loadError()).toBe('Change not found');
  });

  it('clears a stale change target when Operations selects a new context', () => {
    window.history.replaceState(
      {},
      '',
      '/?view=operations&change=change-old&workspace=workspace-old&repository=repository-old'
    );
    component.activeTab.set('operations');
    component.hasImmutableChangeTarget.set(true);

    component.handleOperationsContextChanged({
      workspace_id: 'workspace-2',
      repository_id: 'repository-2',
      scenario_id: null
    });

    const current = new URL(window.location.href);
    expect(current.searchParams.get('change')).toBeNull();
    expect(current.searchParams.get('workspace')).toBe('workspace-2');
    expect(current.searchParams.get('repository')).toBe('repository-2');
    expect(component.hasImmutableChangeTarget()).toBe(false);
  });
});
