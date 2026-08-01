import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked
} from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators
} from '@angular/forms';
import { finalize, forkJoin, switchMap } from 'rxjs';
import { OperationsApiService } from '../../core/api/operations-api.service';
import { WorkspaceApiService } from '../../core/api/workspace-api.service';
import { Language } from '../../core/i18n';
import {
  IncidentDetail,
  IncidentTimelineEvent
} from '../../core/models/deployguard.models';
import {
  EventIngestionStatus,
  EventSeverity,
  DeploymentRecord,
  DeploymentStatus,
  IncidentLifecycle,
  IncidentLifecycleStatus,
  IncidentSeverity,
  OperationalEvent,
  OperationalEventFilters,
  OperatorNotification,
  RiskPolicy,
  ServiceCreateRequest,
  ServiceLifecycle,
  ServiceRecord,
  ServiceTier
} from '../../core/models/operations.models';
import {
  ProductCapabilities,
  MembershipSummary,
  RepositorySummary,
  UserContext,
  WorkspaceSummary
} from '../../core/models/workspace.models';

type OperationsSection = 'catalog' | 'events' | 'deployments' | 'policy' | 'incident';

function thresholdOrderValidator(
  control: AbstractControl
): ValidationErrors | null {
  const warn = Number(control.get('warnThreshold')?.value);
  const block = Number(control.get('blockThreshold')?.value);
  return Number.isFinite(warn) && Number.isFinite(block) && warn >= block
    ? { thresholdOrder: true }
    : null;
}

@Component({
  selector: 'app-operations-center',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './operations-center.component.html',
  styleUrl: './operations-center.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class OperationsCenterComponent implements OnInit {
  private readonly api = inject(OperationsApiService);
  private readonly workspaceApi = inject(WorkspaceApiService);
  private readonly fb = inject(FormBuilder);

  readonly language = input<Language>('en');
  readonly incident = input<IncidentDetail | null>(null);
  readonly workspaceSetupRequested = output<void>();
  readonly contextChanged = output<UserContext>();

  readonly capabilities = signal<ProductCapabilities | null>(null);
  readonly workspaces = signal<WorkspaceSummary[]>([]);
  readonly activeWorkspace = signal<WorkspaceSummary | null>(null);
  readonly repositories = signal<RepositorySummary[]>([]);
  readonly members = signal<MembershipSummary[]>([]);
  readonly services = signal<ServiceRecord[]>([]);
  readonly selectedService = signal<ServiceRecord | null>(null);
  readonly riskPolicy = signal<RiskPolicy | null>(null);
  readonly events = signal<OperationalEvent[]>([]);
  readonly deployments = signal<DeploymentRecord[]>([]);
  readonly notifications = signal<OperatorNotification[]>([]);
  readonly lifecycle = signal<IncidentLifecycle | null>(null);
  readonly pendingTimeline = signal<IncidentTimelineEvent[]>([]);

  readonly activeSection = signal<OperationsSection>('catalog');
  readonly isLoading = signal(true);
  readonly busyAction = signal('');
  readonly error = signal('');
  readonly notice = signal('');
  readonly showServiceForm = signal(false);
  readonly showEventForm = signal(false);
  readonly unreadOnly = signal(false);
  readonly deploymentStatus = signal<DeploymentStatus | 'all'>('all');
  readonly visibleDeployments = computed(() => {
    const status = this.deploymentStatus();
    return status === 'all'
      ? this.deployments()
      : this.deployments().filter((deployment) => deployment.status === status);
  });

  readonly canManage = computed(() => {
    const role = this.activeWorkspace()?.role;
    return role === 'owner' || role === 'admin';
  });
  readonly canRespond = computed(() => {
    const role = this.activeWorkspace()?.role;
    return role === 'owner' || role === 'admin' || role === 'responder';
  });
  readonly catalogCoverage = computed(() => {
    const services = this.services();
    if (!services.length) return 0;
    const documented = services.filter(
      (service) => service.owner_team && service.runbook_url
    ).length;
    return Math.round((documented / services.length) * 100);
  });
  readonly unreadCount = computed(
    () => this.notifications().filter((item) => !item.read_at).length
  );
  readonly visibleNotifications = computed(() =>
    this.unreadOnly()
      ? this.notifications().filter((item) => !item.read_at)
      : this.notifications()
  );
  readonly eventSources = computed(() =>
    [...new Set(this.events().map((event) => event.source))].sort()
  );
  readonly incidentTimeline = computed(() => {
    const incident = this.incident();
    if (!incident) return [];
    const lifecycle = this.lifecycle();
    const authoritative =
      lifecycle?.incident_id === incident.id
        ? lifecycle.timeline
        : incident.timeline;
    const seen = new Set<string>();
    return [...authoritative, ...this.pendingTimeline()].filter((entry) => {
      if (seen.has(entry.id)) return false;
      seen.add(entry.id);
      return true;
    });
  });
  readonly incidentStatus = computed(() => {
    const incident = this.incident();
    const lifecycle = this.lifecycle();
    return lifecycle && lifecycle.incident_id === incident?.id
      ? lifecycle.status
      : incident?.status ?? null;
  });
  readonly isIncidentTerminal = computed(
    () => this.incidentStatus() === 'resolved'
  );

  readonly serviceForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120)]],
    slug: [
      '',
      [
        Validators.required,
        Validators.maxLength(120),
        Validators.pattern(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
      ]
    ],
    description: ['', [Validators.maxLength(500)]],
    tier: ['tier_2' as ServiceTier, [Validators.required]],
    lifecycle: ['active' as ServiceLifecycle, [Validators.required]],
    ownerTeam: ['', [Validators.required, Validators.maxLength(120)]],
    repositoryId: [''],
    dependencies: this.fb.nonNullable.control<string[]>([]),
    runbookUrl: ['', [Validators.pattern(/^https?:\/\/\S+$/)]],
    tags: ['']
  });

  readonly serviceEditForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120)]],
    description: ['', [Validators.maxLength(500)]],
    tier: ['tier_2' as ServiceTier, [Validators.required]],
    lifecycle: ['active' as ServiceLifecycle, [Validators.required]],
    ownerTeam: ['', [Validators.required, Validators.maxLength(120)]],
    repositoryId: [''],
    dependencies: this.fb.nonNullable.control<string[]>([]),
    runbookUrl: ['', [Validators.pattern(/^https?:\/\/\S+$/)]],
    tags: ['']
  });

  readonly policyForm = this.fb.nonNullable.group(
    {
      enabled: [true],
      warnThreshold: [
        55,
        [Validators.required, Validators.min(0), Validators.max(100)]
      ],
      blockThreshold: [
        80,
        [Validators.required, Validators.min(0), Validators.max(100)]
      ],
      requireTests: [true],
      requireRollback: [true],
      maxBlastRadius: [
        8,
        [Validators.required, Validators.min(1), Validators.max(10000)]
      ]
    },
    { validators: [thresholdOrderValidator] }
  );

  readonly eventFilterForm = this.fb.nonNullable.group({
    source: [''],
    eventType: [''],
    severity: [''],
    ingestionStatus: [''],
    repositoryId: [''],
    serviceId: [''],
    occurredAfter: [''],
    occurredBefore: ['']
  });

  readonly eventForm = this.fb.nonNullable.group({
    eventType: ['', [Validators.required, Validators.maxLength(120)]],
    severity: ['info' as EventSeverity, [Validators.required]],
    occurredAt: [this.localDateTime(), [Validators.required]],
    repositoryId: [''],
    serviceId: [''],
    summary: ['', [Validators.required, Validators.maxLength(500)]]
  });

  readonly lifecycleForm = this.fb.nonNullable.group({
    status: ['open' as IncidentLifecycleStatus, [Validators.required]],
    severity: ['sev3' as IncidentSeverity, [Validators.required]],
    assigneeUserId: ['']
  });

  readonly noteForm = this.fb.nonNullable.group({
    note: ['', [Validators.required, Validators.maxLength(2000)]]
  });

  private incidentKey: string | null = null;
  private incidentSnapshot: IncidentDetail | null = null;
  private workspaceRequestId = 0;

  constructor() {
    effect(() => {
      const incident = this.incident();
      untracked(() => {
        this.reconcileIncident(incident);
      });
    });
  }

  ngOnInit(): void {
    this.loadAccessContext();
  }

  copy(en: string, th: string): string {
    return this.language() === 'th' ? th : en;
  }

  setSection(section: OperationsSection): void {
    this.activeSection.set(section);
    this.error.set('');
    this.notice.set('');
  }

  selectWorkspaceId(workspaceId: string): void {
    const workspace = this.workspaces().find((item) => item.id === workspaceId);
    if (workspace) this.selectWorkspace(workspace);
  }

  refresh(): void {
    const workspace = this.activeWorkspace();
    if (workspace) this.loadWorkspaceContext(workspace);
    else this.loadAccessContext();
  }

  toggleUnreadOnly(): void {
    this.unreadOnly.update((value) => !value);
  }

  setDeploymentStatus(status: DeploymentStatus | 'all'): void {
    this.deploymentStatus.set(status);
  }

  selectService(service: ServiceRecord): void {
    this.selectedService.set(service);
    this.serviceEditForm.reset({
      name: service.name,
      description: service.description,
      tier: service.tier,
      lifecycle: service.lifecycle,
      ownerTeam: service.owner_team,
      repositoryId: service.repository_id ?? '',
      dependencies: service.dependencies,
      runbookUrl: service.runbook_url ?? '',
      tags: service.tags.join(', ')
    });
  }

  createService(): void {
    const workspace = this.activeWorkspace();
    if (
      !workspace ||
      !this.canManage() ||
      this.serviceForm.invalid ||
      this.isBusy()
    ) {
      this.serviceForm.markAllAsTouched();
      return;
    }
    this.begin('create-service');
    this.api
      .createService(workspace.id, this.serviceRequest(this.serviceForm.getRawValue()))
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (service) => {
          this.services.update((items) => [...items, service]);
          this.selectService(service);
          this.serviceForm.reset({
            name: '',
            slug: '',
            description: '',
            tier: 'tier_2',
            lifecycle: 'active',
            ownerTeam: '',
            repositoryId: '',
            dependencies: [],
            runbookUrl: '',
            tags: ''
          });
          this.showServiceForm.set(false);
          this.notice.set('Service registered in this workspace.');
        },
        error: (error) => this.fail(error, 'The service could not be registered.')
      });
  }

  saveService(): void {
    const service = this.selectedService();
    if (
      !service ||
      !this.canManage() ||
      this.serviceEditForm.invalid ||
      this.isBusy()
    ) {
      this.serviceEditForm.markAllAsTouched();
      return;
    }
    const value = this.serviceEditForm.getRawValue();
    this.begin('save-service');
    this.api
      .updateService(service.id, {
        name: value.name.trim(),
        description: value.description.trim(),
        tier: value.tier,
        lifecycle: value.lifecycle,
        owner_team: value.ownerTeam.trim(),
        repository_id: value.repositoryId || null,
        dependencies: value.dependencies,
        runbook_url: value.runbookUrl.trim() || null,
        tags: this.csv(value.tags)
      })
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (updated) => {
          this.services.update((items) =>
            items.map((item) => (item.id === updated.id ? updated : item))
          );
          this.selectService(updated);
          this.notice.set('Service ownership and operating metadata saved.');
        },
        error: (error) => this.fail(error, 'The service could not be updated.')
      });
  }

  savePolicy(): void {
    const workspace = this.activeWorkspace();
    const current = this.riskPolicy();
    if (
      !workspace ||
      !current ||
      !this.canManage() ||
      this.policyForm.invalid ||
      this.isBusy()
    ) {
      this.policyForm.markAllAsTouched();
      return;
    }
    const value = this.policyForm.getRawValue();
    this.begin('save-policy');
    this.api
      .updateRiskPolicy(workspace.id, {
        enabled: value.enabled,
        warn_threshold: value.warnThreshold,
        block_threshold: value.blockThreshold,
        require_tests: value.requireTests,
        require_rollback: value.requireRollback,
        max_blast_radius: value.maxBlastRadius,
        version: current.version + 1
      })
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (policy) => {
          this.riskPolicy.set(policy);
          this.patchPolicy(policy);
          this.notice.set(`Risk policy v${policy.version} is now active.`);
        },
        error: (error) => this.fail(error, 'The risk policy could not be saved.')
      });
  }

  applyEventFilters(): void {
    const workspace = this.activeWorkspace();
    if (!workspace || this.isBusy()) return;
    const value = this.eventFilterForm.getRawValue();
    const filters: OperationalEventFilters = {
      source: value.source.trim() || undefined,
      event_type: value.eventType.trim() || undefined,
      severity: (value.severity as EventSeverity) || undefined,
      ingestion_status:
        (value.ingestionStatus as EventIngestionStatus) || undefined,
      repository_id: value.repositoryId || undefined,
      service_id: value.serviceId || undefined,
      occurred_after: value.occurredAfter
        ? new Date(value.occurredAfter).toISOString()
        : undefined,
      occurred_before: value.occurredBefore
        ? new Date(value.occurredBefore).toISOString()
        : undefined,
      limit: 100
    };
    this.begin('filter-events');
    this.api
      .events(workspace.id, filters)
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (events) => this.events.set(events),
        error: (error) => this.fail(error, 'The event ledger could not be filtered.')
      });
  }

  clearEventFilters(): void {
    this.eventFilterForm.reset({
      source: '',
      eventType: '',
      severity: '',
      ingestionStatus: '',
      repositoryId: '',
      serviceId: '',
      occurredAfter: '',
      occurredBefore: ''
    });
    this.applyEventFilters();
  }

  createEvent(): void {
    const workspace = this.activeWorkspace();
    if (
      !workspace ||
      !this.canRespond() ||
      this.eventForm.invalid ||
      this.isBusy()
    ) {
      this.eventForm.markAllAsTouched();
      return;
    }
    const value = this.eventForm.getRawValue();
    this.begin('create-event');
    this.api
      .createEvent(workspace.id, {
        provider_event_id: this.operatorEventId(),
        repository_id: value.repositoryId || null,
        service_id: value.serviceId || null,
        incident_id: this.incident()?.id ?? null,
        source: 'manual',
        event_type: value.eventType.trim(),
        occurred_at: new Date(value.occurredAt).toISOString(),
        severity: value.severity,
        summary: value.summary.trim(),
        attributes: {},
        provenance: {
          origin: 'operator_entry',
          surface: 'operations_center'
        }
      })
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (event) => {
          this.events.update((items) => [event, ...items]);
          this.eventForm.reset({
            eventType: '',
            severity: 'info',
            occurredAt: this.localDateTime(),
            repositoryId: '',
            serviceId: '',
            summary: ''
          });
          this.showEventForm.set(false);
          this.notice.set('Event accepted into the workspace ledger.');
        },
        error: (error) =>
          this.fail(
            error,
            'The event was not accepted. Check its provider ID and try again.'
          )
      });
  }

  updateLifecycle(): void {
    const incident = this.incident();
    if (
      !incident ||
      !this.canRespond() ||
      this.isIncidentTerminal() ||
      this.lifecycleForm.invalid ||
      this.isBusy()
    ) {
      return;
    }
    this.begin('update-lifecycle');
    const value = this.lifecycleForm.getRawValue();
    this.api
      .updateIncidentLifecycle(incident.id, {
        status: value.status,
        severity: value.severity,
        assignee_user_id: value.assigneeUserId || undefined
      })
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (lifecycle) => {
          if (this.incident()?.id !== lifecycle.incident_id) return;
          this.lifecycle.set(lifecycle);
          this.pendingTimeline.set([]);
          this.notice.set(
            `Incident status changed to ${this.humanize(lifecycle.status)}.`
          );
          this.reloadNotifications();
        },
        error: (error) =>
          this.fail(error, 'The incident lifecycle could not be updated.')
      });
  }

  addNote(): void {
    const incident = this.incident();
    if (
      !incident ||
      !this.canRespond() ||
      this.noteForm.invalid ||
      this.isBusy()
    ) {
      this.noteForm.markAllAsTouched();
      return;
    }
    const note = this.noteForm.getRawValue().note.trim();
    this.begin('add-note');
    this.api
      .addIncidentNote(incident.id, { note })
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (entry) => {
          if (this.incident()?.id !== incident.id) return;
          this.pendingTimeline.update((items) =>
            items.some((item) => item.id === entry.id)
              ? items
              : [...items, entry]
          );
          this.noteForm.reset({ note: '' });
          this.notice.set('Incident note appended to the audit timeline.');
          this.reloadNotifications();
        },
        error: (error) => this.fail(error, 'The incident note could not be added.')
      });
  }

  markRead(notification: OperatorNotification): void {
    if (notification.read_at || this.isBusy()) return;
    this.begin(`notification-${notification.id}`);
    this.api
      .markNotificationRead(notification.id)
      .pipe(finalize(() => this.busyAction.set('')))
      .subscribe({
        next: (updated) =>
          this.notifications.update((items) =>
            items.map((item) => (item.id === updated.id ? updated : item))
          ),
        error: (error) =>
          this.fail(error, 'The notification could not be marked as read.')
      });
  }

  openNotification(notification: OperatorNotification): void {
    if (notification.resource_type === 'incident') {
      this.setSection('incident');
    }
    if (!notification.read_at) this.markRead(notification);
  }

  humanize(value: string): string {
    return value.replaceAll('_', ' ');
  }

  isBusy(action?: string): boolean {
    return action ? this.busyAction() === action : Boolean(this.busyAction());
  }

  private loadAccessContext(): void {
    this.isLoading.set(true);
    this.error.set('');
    forkJoin({
      capabilities: this.workspaceApi.capabilities(),
      workspaces: this.workspaceApi.workspaces(),
      context: this.workspaceApi.currentContext()
    })
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: ({ capabilities, workspaces, context }) => {
          this.capabilities.set(capabilities);
          this.workspaces.set(workspaces);
          const active =
            workspaces.find(
              (workspace) => workspace.id === context.workspace_id
            ) ??
            workspaces[0] ??
            null;
          this.activeWorkspace.set(active);
          if (active) this.loadWorkspaceContext(active);
        },
        error: (error) =>
          this.fail(
            error,
            'Operations Center needs an authenticated workspace session.'
          )
      });
  }

  private selectWorkspace(workspace: WorkspaceSummary): void {
    this.workspaceRequestId += 1;
    this.isLoading.set(true);
    this.error.set('');
    this.workspaceApi
      .repositories(workspace.id)
      .pipe(
        switchMap((repositories) => {
          const repository =
            repositories.find((item) => item.selected) ?? repositories[0] ?? null;
          return this.workspaceApi.selectContext(
            workspace.id,
            repository?.id ?? null
          );
        })
      )
      .subscribe({
        next: (context) => {
          this.activeWorkspace.set(workspace);
          this.selectedService.set(null);
          this.contextChanged.emit(context);
          this.loadWorkspaceContext(workspace);
        },
        error: (error) =>
          this.fail(error, 'The workspace context could not be selected.')
      });
  }

  private loadWorkspaceContext(workspace: WorkspaceSummary): void {
    const requestId = ++this.workspaceRequestId;
    this.isLoading.set(true);
    this.error.set('');
    this.notice.set('');
    forkJoin({
      services: this.api.services(workspace.id),
      policy: this.api.riskPolicy(workspace.id),
      events: this.api.events(workspace.id, { limit: 100 }),
      deployments: this.api.deployments(workspace.id, { limit: 100 }),
      notifications: this.api.notifications(workspace.id, false, 100),
      repositories: this.workspaceApi.repositories(workspace.id),
      members: this.workspaceApi.members(workspace.id)
    })
      .pipe(
        finalize(() => {
          if (requestId === this.workspaceRequestId) {
            this.isLoading.set(false);
          }
        })
      )
      .subscribe({
        next: (context) => {
          if (requestId !== this.workspaceRequestId) return;
          this.services.set(context.services);
          this.riskPolicy.set(context.policy);
          this.events.set(context.events);
          this.deployments.set(context.deployments);
          this.notifications.set(context.notifications);
          this.repositories.set(context.repositories);
          this.members.set(context.members);
          this.patchPolicy(context.policy);
          const selected =
            context.services.find(
              (service) => service.id === this.selectedService()?.id
            ) ?? context.services[0];
          if (selected) this.selectService(selected);
          else this.selectedService.set(null);
        },
        error: (error) =>
          this.fail(
            error,
            'Workspace operations data could not be loaded. Retry the connection.'
          )
      });
  }

  private reloadNotifications(): void {
    const workspace = this.activeWorkspace();
    if (!workspace) return;
    this.api.notifications(workspace.id, false, 100).subscribe({
      next: (notifications) => this.notifications.set(notifications)
    });
  }

  private patchPolicy(policy: RiskPolicy): void {
    this.policyForm.reset({
      enabled: policy.enabled,
      warnThreshold: policy.warn_threshold,
      blockThreshold: policy.block_threshold,
      requireTests: policy.require_tests,
      requireRollback: policy.require_rollback,
      maxBlastRadius: policy.max_blast_radius
    });
  }

  private serviceRequest(
    value: typeof this.serviceForm.value & {
      name: string;
      slug: string;
      description: string;
      tier: ServiceTier;
      lifecycle: ServiceLifecycle;
      ownerTeam: string;
      repositoryId: string;
      dependencies: string[];
      runbookUrl: string;
      tags: string;
    }
  ): ServiceCreateRequest {
    return {
      name: value.name.trim(),
      slug: value.slug.trim(),
      description: value.description.trim(),
      tier: value.tier,
      lifecycle: value.lifecycle,
      owner_team: value.ownerTeam.trim(),
      repository_id: value.repositoryId || null,
      dependencies: value.dependencies,
      runbook_url: value.runbookUrl.trim() || null,
      tags: this.csv(value.tags)
    };
  }

  private csv(value: string): string[] {
    return [
      ...new Set(
        value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
      )
    ];
  }

  private begin(action: string): void {
    this.busyAction.set(action);
    this.error.set('');
    this.notice.set('');
  }

  private fail(error: unknown, fallback: string): void {
    this.isLoading.set(false);
    this.busyAction.set('');
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail;
      if (typeof detail === 'string') {
        this.error.set(detail);
        return;
      }
    }
    this.error.set(fallback);
  }

  private normalizeIncidentStatus(value: string): IncidentLifecycleStatus {
    const normalized = value.toLowerCase().replaceAll('-', '_');
    return normalized === 'acknowledged' ||
      normalized === 'investigating' ||
      normalized === 'mitigated' ||
      normalized === 'resolved'
      ? normalized
      : 'open';
  }

  private normalizeIncidentSeverity(value: string): IncidentSeverity {
    const normalized = value.toLowerCase().replaceAll('-', '');
    return normalized === 'sev1' ||
      normalized === 'sev2' ||
      normalized === 'sev3' ||
      normalized === 'sev4'
      ? normalized
      : 'sev3';
  }

  private localDateTime(): string {
    const date = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
    return date.toISOString().slice(0, 16);
  }

  private operatorEventId(): string {
    const id = globalThis.crypto?.randomUUID?.();
    return `operator-${id ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
  }

  private reconcileIncident(incident: IncidentDetail | null): void {
    const nextKey = incident?.id ?? null;
    if (nextKey !== this.incidentKey) {
      this.incidentKey = nextKey;
      this.incidentSnapshot = incident;
      this.lifecycle.set(null);
      this.pendingTimeline.set([]);
    } else if (incident !== this.incidentSnapshot) {
      this.incidentSnapshot = incident;
      this.lifecycle.set(null);
      const authoritativeIds = new Set(
        incident?.timeline.map((entry) => entry.id) ?? []
      );
      this.pendingTimeline.update((entries) =>
        entries.filter((entry) => !authoritativeIds.has(entry.id))
      );
    }

    if (!incident) return;
    this.lifecycleForm.patchValue({
      status: this.normalizeIncidentStatus(incident.status),
      severity: this.normalizeIncidentSeverity(incident.severity),
      assigneeUserId: incident.assignee_user_id ?? ''
    });
  }
}
