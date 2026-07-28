import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { App } from './app';
import { DeployGuardApiService } from './core/api/deployguard-api.service';
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
    exportPostMortem: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    window.history.replaceState({}, '', '/');
    api = {
      getScenarios: vi.fn(() => of(scenarioFixtures)),
      getOverview: vi.fn(() => of(makeOverview())),
      getDoraMetrics: vi.fn(() => of(doraMetricsFixture)),
      activateScenario: vi.fn(() => of(makeOverview('queue-backlog'))),
      analyzeChange: vi.fn(() => of(makeOverview().active_change)),
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
          ]).active_incident
        )
      )
    };

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [{ provide: DeployGuardApiService, useValue: api }]
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
    const writeText = vi.fn(() => Promise.resolve());
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
});
