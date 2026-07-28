import { CommonModule, DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  HostListener,
  OnDestroy,
  OnInit,
  computed,
  inject,
  signal
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { DeployGuardApiService } from './core/api/deployguard-api.service';
import { Language, TRANSLATIONS } from './core/i18n';
import {
  AnalyzeChangeRequest,
  BlastRadiusEdge,
  BlastRadiusNode,
  ChangeDetail,
  DoraMetrics,
  FeedbackVerdict,
  IncidentEvidence,
  IncidentHypothesis,
  Overview,
  ScenarioSummary,
  TopologyPoint
} from './core/models/deployguard.models';
import {
  WorkspaceLinkService,
  WorkspaceView
} from './core/navigation/workspace-link.service';
import {
  CommandPaletteAction,
  CommandPaletteComponent
} from './layout/command-palette/command-palette.component';
import { ScopeSwitcherComponent } from './layout/scope-switcher/scope-switcher.component';
import { DoraDashboardComponent } from './features/dora/dora-dashboard.component';
import { ScenarioLabComponent } from './features/scenario-lab/scenario-lab.component';
import { WorkspaceSetupComponent } from './features/workspace-setup/workspace-setup.component';

type WorkspaceTab = WorkspaceView;

interface AnalysisDraft {
  title: string;
  repository: string;
  author: string;
  filesChanged: number;
  linesAdded: number;
  linesDeleted: number;
  changedServices: string[];
  flags: string;
  testCoveragePercent: number;
  rollbackReady: boolean;
  observabilityPercent: number;
  previousFailures: number;
}

const EMPTY_ANALYSIS_DRAFT: AnalysisDraft = {
  title: '',
  repository: '',
  author: '',
  filesChanged: 0,
  linesAdded: 0,
  linesDeleted: 0,
  changedServices: [],
  flags: '',
  testCoveragePercent: 0,
  rollbackReady: false,
  observabilityPercent: 0,
  previousFailures: 0
};

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    CommandPaletteComponent,
    ScopeSwitcherComponent,
    DoraDashboardComponent,
    ScenarioLabComponent,
    WorkspaceSetupComponent
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit, OnDestroy {
  private readonly api = inject(DeployGuardApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  private readonly workspaceLinks = inject(WorkspaceLinkService);
  private replayTimer: ReturnType<typeof setInterval> | null = null;

  readonly lang = signal<Language>(this.initialLanguage());
  readonly isDarkMode = signal(this.initialDarkMode());
  readonly activeTab = signal<WorkspaceTab>(this.workspaceLinks.readView());
  readonly isSidebarOpen = signal(false);
  readonly shareSuccess = signal('');
  readonly shareError = signal('');

  readonly doraMetrics = signal<DoraMetrics | null>(null);
  readonly scenarios = signal<ScenarioSummary[]>([]);
  readonly overview = signal<Overview | null>(null);
  readonly isLoading = signal(true);
  readonly isRefreshing = signal(false);
  readonly isDoraLoading = signal(false);
  readonly switchingScenarioId = signal<string | null>(null);
  readonly loadError = signal('');
  readonly doraError = signal('');

  readonly isEvidenceXray = signal(false);
  readonly selectedNodeId = signal<string | null>(null);
  readonly selectedHypothesisId = signal<string | null>(null);
  readonly feedbackNote = signal('');
  readonly feedbackError = signal('');
  readonly feedbackSuccess = signal('');
  readonly isSubmittingFeedback = signal(false);

  readonly replayIndex = signal(-1);
  readonly isReplaying = signal(false);

  readonly isExporting = signal(false);
  readonly exportError = signal('');
  readonly exportSuccess = signal('');

  readonly isAnalysisFormOpen = signal(false);
  readonly analysisDraft = signal<AnalysisDraft>({ ...EMPTY_ANALYSIS_DRAFT });
  readonly analysisResult = signal<ChangeDetail | null>(null);
  readonly isAnalyzing = signal(false);
  readonly analysisError = signal('');
  readonly analysisSuccess = signal('');

  readonly activeChange = computed(() => this.overview()?.active_change ?? null);
  readonly activeIncident = computed(() => this.overview()?.active_incident ?? null);
  readonly activeScenarioId = computed(() => this.overview()?.active_scenario_id ?? '');
  readonly displayedRiskChange = computed(
    () => this.analysisResult() ?? this.activeChange()
  );
  readonly lastUpdated = computed(() => this.overview()?.generated_at ?? null);

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
      const ids = new Set([
        ...hypothesis.evidence_ids,
        ...hypothesis.counter_evidence_ids
      ]);
      return evidence.filter((item) => ids.has(item.id));
    }

    const node = this.selectedNode();
    if (node) {
      const ids = new Set(node.evidence_ids);
      const explicitlyLinked = evidence.filter((item) => ids.has(item.id));
      if (explicitlyLinked.length) return explicitlyLinked;

      const serviceEvidence = evidence.filter((item) => item.service_id === node.id);
      if (serviceEvidence.length) return serviceEvidence;
    }

    return evidence.slice(0, 6);
  });

  readonly feedbackForSelectedHypothesis = computed(() => {
    const hypothesisId = this.selectedHypothesisId();
    return (this.activeIncident()?.feedback ?? []).filter(
      (feedback) => feedback.hypothesis_id === hypothesisId
    );
  });

  readonly availableAnalysisNodes = computed(
    () => this.activeChange()?.blast_radius.nodes ?? []
  );

  readonly canAnalyze = computed(() => {
    const draft = this.analysisDraft();
    return Boolean(
      draft.title.trim() &&
        draft.repository.trim() &&
        draft.author.trim() &&
        draft.changedServices.length
    );
  });

  t(key: string): string {
    return TRANSLATIONS[this.lang()][key] ?? TRANSLATIONS.en[key] ?? key;
  }

  ngOnInit(): void {
    this.applyPreferences();
    this.refreshDashboard();
  }

  ngOnDestroy(): void {
    this.pauseReplay();
  }

  setActiveTab(tab: WorkspaceTab): void {
    this.activeTab.set(tab);
    this.isSidebarOpen.set(false);
    this.shareSuccess.set('');
    this.shareError.set('');
    this.workspaceLinks.sync(tab, this.activeScenarioId(), 'push');
    this.document.title = `${this.t(`tab_${tab === 'change_risk' ? 'change_risk' : tab}`)} · DeployGuard AI`;
  }

  handlePaletteAction(action: CommandPaletteAction): void {
    if (action.type === 'navigate') {
      this.setActiveTab(action.view);
      return;
    }
    if (action.type === 'scenario') {
      this.activateScenario(action.scenario);
      return;
    }
    if (action.type === 'share') {
      void this.copyCurrentView();
      return;
    }
    this.toggleEvidenceXray();
  }

  @HostListener('window:popstate')
  restoreViewFromUrl(): void {
    this.activeTab.set(this.workspaceLinks.readView());
    const scenarioId = this.workspaceLinks.readScenarioId();
    const scenario = this.scenarios().find((item) => item.id === scenarioId);
    if (scenario && scenario.id !== this.activeScenarioId()) {
      this.activateScenario(scenario, false);
    }
  }

  toggleSidebar(): void {
    this.isSidebarOpen.update((value) => !value);
  }

  toggleTheme(): void {
    const next = !this.isDarkMode();
    this.isDarkMode.set(next);
    this.applyTheme(next);
    this.writePreference('deployguard-theme', next ? 'dark' : 'light');
  }

  setLang(language: Language): void {
    this.lang.set(language);
    this.document.documentElement.lang = language;
    this.writePreference('deployguard-language', language);
  }

  refreshDashboard(silent = false): void {
    if (this.isRefreshing()) return;
    if (silent) {
      this.isRefreshing.set(true);
    } else {
      this.isLoading.set(true);
    }
    this.loadError.set('');
    this.exportError.set('');

    forkJoin({
      scenarios: this.api.getScenarios(),
      overview: this.api.getOverview()
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          this.isLoading.set(false);
          this.isRefreshing.set(false);
        })
      )
      .subscribe({
        next: ({ scenarios, overview }) => {
          this.scenarios.set(scenarios);
          this.applyOverview(overview);
          const requestedScenarioId = this.workspaceLinks.readScenarioId();
          const requestedScenario = scenarios.find(
            (scenario) => scenario.id === requestedScenarioId
          );
          if (
            requestedScenario &&
            requestedScenario.id !== overview.active_scenario_id
          ) {
            this.activateScenario(requestedScenario, false);
          } else {
            this.workspaceLinks.sync(
              this.activeTab(),
              overview.active_scenario_id,
              'replace'
            );
          }
        },
        error: (error: unknown) => {
          this.loadError.set(
            this.errorMessage(error, this.t('error_dashboard_load'))
          );
        }
      });

    this.loadDoraMetrics();
  }

  loadDoraMetrics(): void {
    this.isDoraLoading.set(true);
    this.doraError.set('');
    this.api
      .getDoraMetrics()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.isDoraLoading.set(false))
      )
      .subscribe({
        next: (metrics) => this.doraMetrics.set(metrics),
        error: (error: unknown) => {
          this.doraError.set(
            this.errorMessage(error, this.t('error_dora_load'))
          );
        }
      });
  }

  activateScenario(scenario: ScenarioSummary, updateUrl = true): void {
    if (this.switchingScenarioId() || scenario.id === this.activeScenarioId()) return;
    this.switchingScenarioId.set(scenario.id);
    this.loadError.set('');
    this.feedbackSuccess.set('');
    this.analysisResult.set(null);

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
          if (updateUrl) {
            this.workspaceLinks.sync(
              this.activeTab(),
              overview.active_scenario_id,
              'push'
            );
          }
          this.loadDoraMetrics();
        },
        error: (error: unknown) => {
          this.loadError.set(
            this.errorMessage(error, this.t('error_scenario_activate'))
          );
        }
      });
  }

  async copyCurrentView(): Promise<void> {
    this.shareSuccess.set('');
    this.shareError.set('');
    try {
      await this.workspaceLinks.copy(this.activeTab(), this.activeScenarioId());
      this.shareSuccess.set(this.t('view_link_copied'));
    } catch {
      this.shareError.set(this.t('error_copy_link'));
    }
  }

  selectNode(node: BlastRadiusNode | string): void {
    const id = typeof node === 'string' ? node : node.id;
    this.selectedNodeId.set(id);
    this.selectedHypothesisId.set(null);
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
      this.feedbackError.set(this.t('error_feedback_note'));
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
          this.overview.update((current) =>
            current ? { ...current, active_incident: updatedIncident } : current
          );
          this.feedbackNote.set('');
          this.feedbackSuccess.set(
            this.t('feedback_recorded').replace('{rank}', String(hypothesis.rank))
          );
        },
        error: (error: unknown) => {
          this.feedbackError.set(
            this.errorMessage(error, this.t('error_feedback_submit'))
          );
        }
      });
  }

  startReplay(): void {
    const eventCount = this.activeIncident()?.timeline.length ?? 0;
    if (!eventCount || this.isReplaying()) return;
    this.clearReplayTimer();

    if (globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      this.replayIndex.set(eventCount - 1);
      return;
    }

    if (this.replayIndex() < 0 || this.replayIndex() >= eventCount - 1) {
      this.replayIndex.set(0);
    }
    this.isReplaying.set(true);
    this.replayTimer = setInterval(() => {
      const next = this.replayIndex() + 1;
      if (next >= eventCount) {
        this.replayIndex.set(eventCount - 1);
        this.pauseReplay();
        return;
      }
      this.replayIndex.set(next);
    }, 720);
  }

  pauseReplay(): void {
    this.clearReplayTimer();
    this.isReplaying.set(false);
  }

  resetReplay(): void {
    this.pauseReplay();
    this.replayIndex.set(-1);
  }

  scrubReplay(index: number): void {
    this.pauseReplay();
    this.replayIndex.set(index);
  }

  exportPostMortem(): void {
    const incident = this.activeIncident();
    if (!incident || this.isExporting()) return;

    this.isExporting.set(true);
    this.exportError.set('');
    this.exportSuccess.set('');
    this.api
      .exportPostMortem(incident.id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.isExporting.set(false))
      )
      .subscribe({
        next: (markdown) => {
          this.downloadText(
            markdown,
            `${this.safeFileName(incident.id)}-post-mortem.md`
          );
          this.exportSuccess.set(this.t('export_ready'));
        },
        error: (error: unknown) => {
          this.exportError.set(
            this.errorMessage(error, this.t('error_export'))
          );
        }
      });
  }

  toggleAnalysisForm(): void {
    this.isAnalysisFormOpen.update((value) => !value);
    this.analysisError.set('');
    this.analysisSuccess.set('');
  }

  updateAnalysisDraft(patch: Partial<AnalysisDraft>): void {
    this.analysisDraft.update((current) => ({ ...current, ...patch }));
  }

  toggleAnalysisService(serviceId: string, checked: boolean): void {
    this.analysisDraft.update((current) => {
      const services = new Set(current.changedServices);
      if (checked) services.add(serviceId);
      else services.delete(serviceId);
      return { ...current, changedServices: [...services] };
    });
  }

  submitChangeAnalysis(): void {
    if (this.isAnalyzing()) return;
    if (!this.canAnalyze()) {
      this.analysisError.set(this.t('error_analysis_required'));
      return;
    }

    const draft = this.analysisDraft();
    const payload: AnalyzeChangeRequest = {
      title: draft.title.trim(),
      repository: draft.repository.trim(),
      author: draft.author.trim(),
      files_changed: this.nonNegativeInteger(draft.filesChanged),
      lines_added: this.nonNegativeInteger(draft.linesAdded),
      lines_deleted: this.nonNegativeInteger(draft.linesDeleted),
      changed_services: draft.changedServices,
      flags: [
        ...new Set(
          draft.flags
            .split(',')
            .map((flag) => flag.trim())
            .filter(Boolean)
        )
      ],
      test_coverage: this.percentage(draft.testCoveragePercent),
      rollback_ready: draft.rollbackReady,
      observability_score: this.percentage(draft.observabilityPercent),
      previous_failures: this.nonNegativeInteger(draft.previousFailures)
    };

    this.isAnalyzing.set(true);
    this.analysisError.set('');
    this.analysisSuccess.set('');
    this.api
      .analyzeChange(payload)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.isAnalyzing.set(false))
      )
      .subscribe({
        next: (change) => {
          this.analysisResult.set(change);
          this.analysisSuccess.set(this.t('analysis_complete'));
          this.isAnalysisFormOpen.set(false);
        },
        error: (error: unknown) => {
          this.analysisError.set(
            this.errorMessage(error, this.t('error_analysis_submit'))
          );
        }
      });
  }

  clearAnalysisResult(): void {
    this.analysisResult.set(null);
    this.analysisSuccess.set('');
  }

  nodePoint(nodeId: string): TopologyPoint {
    return this.topologyPoints().get(nodeId) ?? { id: nodeId, x: 470, y: 190 };
  }

  nodeEvidenceCount(node: BlastRadiusNode): number {
    return node.evidence_ids.length;
  }

  isEdgeRevealed(edge: BlastRadiusEdge, index: number): boolean {
    if (!edge.active) return false;
    if (this.replayIndex() < 0) return true;
    const eventCount = Math.max(1, this.activeIncident()?.timeline.length ?? 1);
    const progress = (this.replayIndex() + 1) / eventCount;
    const activeEdges = this.activeChange()?.blast_radius.edges.filter(
      (item) => item.active
    ).length ?? 0;
    return index < Math.ceil(progress * activeEdges);
  }

  evidenceRelation(evidence: IncidentEvidence): 'supports' | 'contradicts' | 'context' {
    const hypothesis = this.selectedHypothesis();
    if (!hypothesis) return 'context';
    if (hypothesis.counter_evidence_ids.includes(evidence.id)) return 'contradicts';
    if (hypothesis.evidence_ids.includes(evidence.id)) return 'supports';
    return 'context';
  }

  feedbackLabel(verdict: string): string {
    return this.t(`verdict_${verdict}`);
  }

  readableStatus(value: string | null | undefined): string {
    return value ? value.replaceAll('_', ' ') : this.t('not_available');
  }

  private applyOverview(overview: Overview): void {
    this.resetReplay();
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
    this.exportSuccess.set('');
  }

  private buildTopologyPoints(): Map<string, TopologyPoint> {
    const nodes = this.activeChange()?.blast_radius.nodes ?? [];
    if (!nodes.length) return new Map();

    const layers = new Map<number, BlastRadiusNode[]>();
    for (const node of nodes) {
      const hop = Number.isFinite(node.hop_distance)
        ? Math.max(0, node.hop_distance)
        : 0;
      layers.set(hop, [...(layers.get(hop) ?? []), node]);
    }

    const orderedLayers = [...layers.entries()].sort(([a], [b]) => a - b);
    const minX = 110;
    const maxX = 830;
    const minY = 68;
    const maxY = 312;
    const xStep =
      orderedLayers.length > 1
        ? (maxX - minX) / (orderedLayers.length - 1)
        : 0;

    const points = new Map<string, TopologyPoint>();
    orderedLayers.forEach(([, layerNodes], layerIndex) => {
      const x =
        orderedLayers.length === 1 ? (minX + maxX) / 2 : minX + layerIndex * xStep;
      const yStep = (maxY - minY) / Math.max(1, layerNodes.length - 1);
      layerNodes
        .slice()
        .sort((a, b) => a.label.localeCompare(b.label))
        .forEach((node, nodeIndex) => {
          const y =
            layerNodes.length === 1
              ? (minY + maxY) / 2
              : minY + nodeIndex * yStep;
          points.set(node.id, { id: node.id, x, y });
        });
    });
    return points;
  }

  private loadPreference(key: string): string | null {
    try {
      return globalThis.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  private writePreference(key: string, value: string): void {
    try {
      globalThis.localStorage?.setItem(key, value);
    } catch {
      // Preferences are optional when storage is blocked.
    }
  }

  private initialLanguage(): Language {
    const stored = this.loadPreference('deployguard-language');
    if (stored === 'th' || stored === 'en') return stored;
    return globalThis.navigator?.language?.toLowerCase().startsWith('th') ? 'th' : 'en';
  }

  private initialDarkMode(): boolean {
    const stored = this.loadPreference('deployguard-theme');
    if (stored === 'dark') return true;
    if (stored === 'light') return false;
    return Boolean(globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches);
  }

  private applyPreferences(): void {
    this.applyTheme(this.isDarkMode());
    this.document.documentElement.lang = this.lang();
  }

  private applyTheme(isDark: boolean): void {
    this.document.body.classList.toggle('dark-theme', isDark);
    this.document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';
  }

  private clearReplayTimer(): void {
    if (this.replayTimer) {
      clearInterval(this.replayTimer);
      this.replayTimer = null;
    }
  }

  private nonNegativeInteger(value: number): number {
    return Math.max(0, Math.round(Number(value) || 0));
  }

  private percentage(value: number): number {
    return Math.min(1, Math.max(0, Number(value) || 0) / 100);
  }

  private safeFileName(value: string): string {
    return value.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  }

  private downloadText(content: string, fileName: string): void {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const objectUrl = globalThis.URL.createObjectURL(blob);
    const anchor = this.document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = fileName;
    anchor.style.display = 'none';
    this.document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    globalThis.URL.revokeObjectURL(objectUrl);
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail as string | { msg?: string }[] | undefined;
      if (typeof detail === 'string' && detail.trim()) return detail;
      if (Array.isArray(detail)) {
        const message = detail.map((item) => item.msg).filter(Boolean).join(' · ');
        if (message) return message;
      }
      if (error.status === 0) return this.t('error_api_unreachable');
    }
    return fallback;
  }
}
