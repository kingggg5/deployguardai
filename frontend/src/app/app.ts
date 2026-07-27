import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { finalize, forkJoin } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DeployGuardApiService } from './core/api/deployguard-api.service';
import {
  BlastRadiusEdge,
  BlastRadiusNode,
  DoraMetrics,
  FeedbackVerdict,
  IncidentEvidence,
  IncidentHypothesis,
  Overview,
  ScenarioSummary,
  TopologyPoint
} from './core/models/deployguard.models';

type MobilePane = 'changes' | 'topology' | 'ledger' | 'recorder';

import { Language, TRANSLATIONS } from './core/i18n';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit, OnDestroy {
  private readonly api = inject(DeployGuardApiService);
  private readonly destroyRef = inject(DestroyRef);
  private replayTimer: ReturnType<typeof setInterval> | null = null;

  readonly lang = signal<Language>('th');
  readonly isDarkMode = signal<boolean>(false);
  readonly activeTab = signal<'investigation' | 'change_risk' | 'dora' | 'scenarios'>('investigation');
  readonly doraMetrics = signal<DoraMetrics | null>(null);
  readonly scenarios = signal<ScenarioSummary[]>([]);
  readonly overview = signal<Overview | null>(null);
  readonly isLoading = signal(true);
  readonly isRefreshing = signal(false);
  readonly switchingScenarioId = signal<string | null>(null);
  readonly loadError = signal('');
  readonly isEvidenceXray = signal(false);
  readonly selectedNodeId = signal<string | null>(null);
  readonly selectedHypothesisId = signal<string | null>(null);
  readonly feedbackNote = signal('');
  readonly feedbackError = signal('');
  readonly feedbackSuccess = signal('');
  readonly isSubmittingFeedback = signal(false);
  readonly activeMobilePane = signal<MobilePane>('topology');
  readonly replayIndex = signal(-1);
  readonly isReplaying = signal(false);

  t(key: string): string {
    return TRANSLATIONS[this.lang()][key] || key;
  }

  toggleTheme(): void {
    const next = !this.isDarkMode();
    this.isDarkMode.set(next);
    if (next) {
      document.body.classList.add('dark-theme');
    } else {
      document.body.classList.remove('dark-theme');
    }
  }

  setLang(language: Language): void {
    this.lang.set(language);
  }

  readonly activeChange = computed(() => this.overview()?.active_change ?? null);
  readonly activeIncident = computed(() => this.overview()?.active_incident ?? null);
  readonly activeScenarioId = computed(() => this.overview()?.active_scenario_id ?? '');
  readonly selectedNode = computed(() => {
    const id = this.selectedNodeId();
    return this.activeChange()?.blast_radius.nodes.find((node) => node.id === id) ?? null;
  });
  readonly selectedHypothesis = computed(() => {
    const id = this.selectedHypothesisId();
    return this.activeIncident()?.hypotheses.find((hypothesis) => hypothesis.id === id) ?? null;
  });
  readonly orderedHypotheses = computed(() =>
    [...(this.activeIncident()?.hypotheses ?? [])]
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 3)
  );
  readonly topologyPoints = computed(() => this.buildTopologyPoints());
  readonly visibleEvidence = computed(() => {
    const evidence = this.activeIncident()?.evidence ?? [];
    const hypothesis = this.selectedHypothesis();
    if (hypothesis) {
      const ids = new Set([...hypothesis.evidence_ids, ...hypothesis.counter_evidence_ids]);
      return evidence.filter((item) => ids.has(item.id));
    }

    const node = this.selectedNode();
    if (node?.evidence_ids.length) {
      const ids = new Set(node.evidence_ids);
      const explicitlyLinked = evidence.filter((item) => ids.has(item.id));
      if (explicitlyLinked.length) return explicitlyLinked;

      const serviceEvidence = evidence.filter(
        (item) => item.service_id === node.id
      );
      if (serviceEvidence.length) return serviceEvidence;
    }

    return evidence.slice(0, 5);
  });
  readonly feedbackForSelectedHypothesis = computed(() => {
    const hypothesisId = this.selectedHypothesisId();
    return (this.activeIncident()?.feedback ?? []).filter(
      (feedback) => feedback.hypothesis_id === hypothesisId
    );
  });

  ngOnInit(): void {
    this.refreshDashboard();
  }

  ngOnDestroy(): void {
    this.stopReplay();
  }

  refreshDashboard(silent = false): void {
    if (this.isRefreshing()) return;
    if (silent) {
      this.isRefreshing.set(true);
    } else {
      this.isLoading.set(true);
    }
    this.loadError.set('');

    forkJoin({
      scenarios: this.api.getScenarios(),
      overview: this.api.getOverview(),
      dora: this.api.getDoraMetrics()
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          this.isLoading.set(false);
          this.isRefreshing.set(false);
        })
      )
      .subscribe({
        next: ({ scenarios, overview, dora }) => {
          this.scenarios.set(scenarios);
          this.applyOverview(overview);
          this.doraMetrics.set(dora);
        },
        error: (error: unknown) => {
          this.loadError.set(
            this.errorMessage(error, 'The investigation ledger could not be loaded.')
          );
        }
      });
  }

  activateScenario(scenario: ScenarioSummary): void {
    if (this.switchingScenarioId() || scenario.id === this.activeScenarioId()) return;
    this.switchingScenarioId.set(scenario.id);
    this.loadError.set('');
    this.feedbackSuccess.set('');

    this.api
      .activateScenario(scenario.id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.switchingScenarioId.set(null))
      )
      .subscribe({
        next: (overview) => {
          this.applyOverview(overview);
          this.scenarios.update((items) =>
            items.map((item) => ({ ...item, is_active: item.id === scenario.id }))
          );
        },
        error: (error: unknown) => {
          this.loadError.set(
            this.errorMessage(error, `Scenario “${scenario.name}” could not be activated.`)
          );
        }
      });
  }

  selectNode(node: BlastRadiusNode | string): void {
    const id = typeof node === 'string' ? node : node.id;
    this.selectedNodeId.set(id);
    this.selectedHypothesisId.set(null);
    this.activeMobilePane.set('ledger');
  }

  getPoint(id: string): TopologyPoint {
    return this.topologyPoints().get(id) ?? { id, x: 200, y: 200 };
  }

  selectHypothesis(hypothesis: IncidentHypothesis): void {
    this.selectedHypothesisId.set(hypothesis.id);
    this.selectedNodeId.set(hypothesis.cause_service);
    this.feedbackError.set('');
    this.feedbackSuccess.set('');
  }

  toggleEvidenceXray(): void {
    this.isEvidenceXray.update((value) => !value);
  }

  submitFeedback(verdict: FeedbackVerdict): void {
    const incident = this.activeIncident();
    const hypothesis = this.selectedHypothesis();
    if (!incident || !hypothesis || this.isSubmittingFeedback()) return;
    const note = this.feedbackNote().trim();
    if (!note) {
      this.feedbackError.set('Add a short investigation note before recording a verdict.');
      return;
    }

    this.isSubmittingFeedback.set(true);
    this.feedbackError.set('');
    this.feedbackSuccess.set('');

    this.api
      .submitFeedback(incident.id, {
        hypothesis_id: hypothesis.id,
        verdict,
        note
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.isSubmittingFeedback.set(false))
      )
      .subscribe({
        next: (updatedIncident) => {
          this.overview.update((current) => {
            if (!current) return current;
            return {
              ...current,
              active_incident: updatedIncident
            };
          });
          this.feedbackNote.set('');
          this.feedbackSuccess.set(`Verdict recorded for hypothesis #${hypothesis.rank}.`);
        },
        error: (error: unknown) => {
          this.feedbackError.set(
            this.errorMessage(error, 'The verdict could not be recorded. Try again.')
          );
        }
      });
  }

  startReplay(): void {
    const eventCount = this.activeIncident()?.timeline.length ?? 0;
    if (!eventCount) return;
    this.stopReplay();

    if (globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      this.replayIndex.set(eventCount - 1);
      return;
    }

    this.replayIndex.set(0);
    this.isReplaying.set(true);
    this.replayTimer = setInterval(() => {
      const next = this.replayIndex() + 1;
      if (next >= eventCount) {
        this.replayIndex.set(eventCount - 1);
        this.stopReplay(false);
        return;
      }
      this.replayIndex.set(next);
    }, 520);
  }

  stopReplay(reset = true): void {
    if (this.replayTimer) {
      clearInterval(this.replayTimer);
      this.replayTimer = null;
    }
    this.isReplaying.set(false);
    if (reset) this.replayIndex.set(-1);
  }

  setMobilePane(pane: MobilePane): void {
    this.activeMobilePane.set(pane);
  }

  nodePoint(nodeId: string): TopologyPoint {
    return this.topologyPoints().get(nodeId) ?? { id: nodeId, x: 510, y: 170 };
  }

  nodeEvidenceCount(node: BlastRadiusNode): number {
    return node.evidence_ids.length;
  }

  isEdgeRevealed(edge: BlastRadiusEdge, index: number): boolean {
    if (!edge.active) return false;
    if (this.replayIndex() < 0) return true;
    const eventCount = Math.max(1, this.activeIncident()?.timeline.length ?? 1);
    const progress = (this.replayIndex() + 1) / eventCount;
    return index < Math.ceil(progress * this.activeChangeEdges().length);
  }

  activeChangeEdges(): BlastRadiusEdge[] {
    return this.activeChange()?.blast_radius.edges ?? [];
  }

  evidenceRelation(evidence: IncidentEvidence): 'supports' | 'contradicts' | 'context' {
    const hypothesis = this.selectedHypothesis();
    if (!hypothesis) return 'context';
    if (hypothesis.counter_evidence_ids.includes(evidence.id)) return 'contradicts';
    if (hypothesis.evidence_ids.includes(evidence.id)) return 'supports';
    return 'context';
  }

  feedbackLabel(verdict: string): string {
    if (verdict === 'confirmed') return 'Confirmed';
    if (verdict === 'rejected') return 'Rejected';
    if (verdict === 'partial') return 'Partial cause';
    return verdict;
  }

  trackById(_: number, value: { id: string }): string {
    return value.id;
  }

  private applyOverview(overview: Overview): void {
    this.stopReplay();
    this.overview.set(overview);
    const nodes = overview.active_change.blast_radius.nodes;
    const currentNodeExists = nodes.some((node) => node.id === this.selectedNodeId());
    if (!currentNodeExists) {
      this.selectedNodeId.set(
        nodes.find((node) => node.impact_score > 0)?.id ?? nodes[0]?.id ?? null
      );
    }

    const hypotheses = [...overview.active_incident.hypotheses].sort(
      (a, b) => a.rank - b.rank
    );
    const currentHypothesisExists = hypotheses.some(
      (hypothesis) => hypothesis.id === this.selectedHypothesisId()
    );
    if (!currentHypothesisExists) {
      this.selectedHypothesisId.set(hypotheses[0]?.id ?? null);
    }
    this.feedbackNote.set('');
    this.feedbackError.set('');
  }

  private buildTopologyPoints(): Map<string, TopologyPoint> {
    const nodes = this.activeChange()?.blast_radius.nodes ?? [];
    const lanePoints: TopologyPoint[] = [
      { id: '', x: 120, y: 170 },
      { id: '', x: 355, y: 88 },
      { id: '', x: 355, y: 252 },
      { id: '', x: 610, y: 68 },
      { id: '', x: 610, y: 170 },
      { id: '', x: 610, y: 272 },
      { id: '', x: 860, y: 104 },
      { id: '', x: 860, y: 236 }
    ];

    return new Map(
      nodes.map((node, index) => {
        const point = lanePoints[index] ?? {
          id: '',
          x: 860,
          y: 70 + ((index - lanePoints.length) % 4) * 72
        };
        return [node.id, { ...point, id: node.id }];
      })
    );
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail as string | { msg?: string }[] | undefined;
      if (typeof detail === 'string' && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        const message = detail.map((item) => item.msg).filter(Boolean).join(' · ');
        if (message) return message;
      }
      if (error.status === 0) {
        return 'DeployGuard API is unreachable at 127.0.0.1:8100. Start the backend and retry.';
      }
    }
    return fallback;
  }
}
