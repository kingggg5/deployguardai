import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  input,
  signal
} from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators
} from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { OidcSecurityService } from 'angular-auth-oidc-client';
import { WorkspaceApiService } from '../../core/api/workspace-api.service';
import { Language } from '../../core/i18n';
import {
  AuditEventSummary,
  ConnectedChangeSummary,
  GitHubConnectionSummary,
  GitHubRepositoryCandidate,
  InvitationCreated,
  InvitationSummary,
  MembershipSummary,
  ProductCapabilities,
  RepositorySummary,
  UserSummary,
  WorkspaceSummary
} from '../../core/models/workspace.models';

@Component({
  selector: 'app-workspace-setup',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './workspace-setup.component.html',
  styleUrl: './workspace-setup.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class WorkspaceSetupComponent implements OnInit {
  private readonly api = inject(WorkspaceApiService);
  private readonly fb = inject(FormBuilder);
  private readonly oidc = inject(OidcSecurityService);

  readonly language = input<Language>('en');
  readonly user = signal<UserSummary | null>(null);
  readonly capabilities = signal<ProductCapabilities | null>(null);
  readonly githubConnection = signal<GitHubConnectionSummary | null>(null);
  readonly githubCandidates = signal<GitHubRepositoryCandidate[]>([]);
  readonly workspaces = signal<WorkspaceSummary[]>([]);
  readonly activeWorkspace = signal<WorkspaceSummary | null>(null);
  readonly repositories = signal<RepositorySummary[]>([]);
  readonly members = signal<MembershipSummary[]>([]);
  readonly invitations = signal<InvitationSummary[]>([]);
  readonly auditEvents = signal<AuditEventSummary[]>([]);
  readonly connectedChanges = signal<ConnectedChangeSummary[]>([]);
  readonly latestInvite = signal<InvitationCreated | null>(null);
  readonly isBusy = signal(false);
  readonly error = signal('');
  readonly notice = signal('');

  readonly canManage = computed(() => {
    const role = this.activeWorkspace()?.role;
    return role === 'owner' || role === 'admin';
  });
  readonly activationStep = computed(() => {
    if (!this.user()) return 1;
    if (!this.activeWorkspace()) return 2;
    if (!this.repositories().length) return 3;
    return 4;
  });

  readonly identityForm = this.fb.nonNullable.group({
    email: ['', [Validators.email]],
    displayName: ['']
  });
  readonly workspaceForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120)]],
    slug: [
      '',
      [
        Validators.required,
        Validators.pattern(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
      ]
    ]
  });
  readonly repositoryForm = this.fb.nonNullable.group({
    fullName: [
      '',
      [Validators.required, Validators.pattern(/^[^/\s]+\/[^/\s]+$/)]
    ],
    defaultBranch: ['main', [Validators.required]],
    visibility: ['private']
  });
  readonly invitationForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['viewer']
  });
  readonly acceptForm = this.fb.nonNullable.group({
    token: ['', [Validators.required]]
  });

  ngOnInit(): void {
    this.api.capabilities().subscribe({
      next: (capabilities) => {
        this.capabilities.set(capabilities);
        if (capabilities.auth_provider === 'oidc') {
          this.oidc.checkAuth().subscribe({
            next: ({ isAuthenticated }) => {
              if (!isAuthenticated) return;
              this.api.me().subscribe({
                next: (user) => {
                  this.user.set(user);
                  this.loadWorkspaces();
                },
                error: (error) => this.fail(error)
              });
            },
            error: (error) => this.fail(error)
          });
        } else if (this.api.token()) {
          this.loadWorkspaces();
        }
      },
      error: (error) => this.fail(error)
    });
  }

  signIn(): void {
    if (this.identityForm.invalid || this.isBusy()) return;
    this.begin();
    const { email, displayName } = this.identityForm.getRawValue();
    this.api
      .developmentSession(email || undefined, displayName || undefined)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (session) => {
          this.api.storeToken(session.access_token);
          this.user.set(session.user);
          this.workspaces.set(session.workspaces);
          if (session.workspaces[0]) this.selectWorkspace(session.workspaces[0]);
          this.notice.set(
            this.language() === 'th'
              ? 'เข้าสู่ระบบด้วย Development identity แล้ว'
              : 'Signed in with the development identity provider.'
          );
        },
        error: (error) => this.fail(error)
      });
  }

  signOut(): void {
    if (this.capabilities()?.auth_provider === 'oidc') {
      this.oidc.logoff().subscribe();
    }
    this.api.clearToken();
    this.user.set(null);
    this.workspaces.set([]);
    this.activeWorkspace.set(null);
    this.repositories.set([]);
    this.members.set([]);
    this.invitations.set([]);
    this.auditEvents.set([]);
    this.latestInvite.set(null);
    this.notice.set('');
    this.error.set('');
  }

  signInOidc(): void {
    if (this.capabilities()?.auth_provider !== 'oidc') return;
    this.begin();
    this.oidc
      .authorizeWithPopUp()
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: ({ isAuthenticated }) => {
          if (!isAuthenticated) {
            this.error.set('The identity provider did not complete sign-in.');
            return;
          }
          this.api.me().subscribe({
            next: (user) => {
              this.user.set(user);
              this.loadWorkspaces();
            },
            error: (error) => this.fail(error)
          });
        },
        error: (error) => this.fail(error)
      });
  }

  createWorkspace(): void {
    if (this.workspaceForm.invalid || this.isBusy()) return;
    this.begin();
    const payload = this.workspaceForm.getRawValue();
    this.api
      .createWorkspace(payload.name.trim(), payload.slug.trim())
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (workspace) => {
          this.workspaces.update((items) => [...items, workspace]);
          this.workspaceForm.reset({ name: '', slug: '' });
          this.selectWorkspace(workspace);
          this.notice.set(
            this.language() === 'th'
              ? 'สร้าง workspace และกำหนดคุณเป็น Owner แล้ว'
              : 'Workspace created. You are its owner.'
          );
        },
        error: (error) => this.fail(error)
      });
  }

  selectWorkspace(workspace: WorkspaceSummary): void {
    this.activeWorkspace.set(workspace);
    this.latestInvite.set(null);
    this.loadWorkspaceContext(workspace);
  }

  connectRepository(): void {
    const workspace = this.activeWorkspace();
    if (!workspace || this.repositoryForm.invalid || this.isBusy()) return;
    this.begin();
    const payload = this.repositoryForm.getRawValue();
    this.api
      .connectDevelopmentRepository(
        workspace.id,
        payload.fullName.trim(),
        payload.defaultBranch.trim(),
        payload.visibility
      )
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (repository) => {
          this.repositories.update((items) => [...items, repository]);
          this.repositoryForm.reset({
            fullName: '',
            defaultBranch: 'main',
            visibility: 'private'
          });
          this.notice.set(
            this.language() === 'th'
              ? 'เชื่อม repository จาก Development fixture แล้ว'
              : 'Development fixture repository connected.'
          );
          this.refreshAudit();
        },
        error: (error) => this.fail(error)
      });
  }

  installGitHub(): void {
    const workspace = this.activeWorkspace();
    if (!workspace || this.isBusy()) return;
    this.begin();
    this.api
      .startGitHubInstall(workspace.id)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: ({ install_url }) => globalThis.location.assign(install_url),
        error: (error) => this.fail(error)
      });
  }

  toggleGitHubRepository(candidate: GitHubRepositoryCandidate): void {
    this.githubCandidates.update((items) =>
      items.map((item) =>
        item.provider_repository_id === candidate.provider_repository_id
          ? { ...item, selected: !item.selected }
          : item
      )
    );
  }

  syncGitHubRepositories(): void {
    const workspace = this.activeWorkspace();
    const repositoryIds = this.githubCandidates()
      .filter((item) => item.selected && !item.archived)
      .map((item) => item.provider_repository_id);
    if (!workspace || !repositoryIds.length || this.isBusy()) return;
    this.begin();
    this.api
      .syncGitHubRepositories(workspace.id, repositoryIds)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: ({ imported }) => {
          this.notice.set(`${imported} GitHub repositories synchronized.`);
          this.loadWorkspaceContext(workspace);
        },
        error: (error) => this.fail(error)
      });
  }

  inviteMember(): void {
    const workspace = this.activeWorkspace();
    if (!workspace || this.invitationForm.invalid || this.isBusy()) return;
    this.begin();
    const payload = this.invitationForm.getRawValue();
    const role =
      payload.role === 'admin' || payload.role === 'responder'
        ? payload.role
        : 'viewer';
    this.api
      .invite(workspace.id, payload.email.trim(), role)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (invitation) => {
          this.latestInvite.set(invitation);
          this.invitations.update((items) => [invitation, ...items]);
          this.invitationForm.reset({ email: '', role: 'viewer' });
          this.notice.set(
            invitation.delivery_status === 'sent'
              ? 'Invitation email sent.'
              : invitation.delivery_status === 'development_outbox'
                ? 'Invite created in the development outbox — no email was sent.'
                : 'Invitation was saved, but delivery is not available.'
          );
          this.refreshAudit();
        },
        error: (error) => this.fail(error)
      });
  }

  acceptInvitation(): void {
    if (this.acceptForm.invalid || this.isBusy()) return;
    this.begin();
    this.api
      .acceptInvitation(this.acceptForm.getRawValue().token.trim())
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (workspace) => {
          this.acceptForm.reset();
          this.notice.set(
            this.language() === 'th'
              ? `เข้าร่วม ${workspace.name} แล้ว`
              : `Joined ${workspace.name}.`
          );
          this.loadWorkspaces(workspace.id);
        },
        error: (error) => this.fail(error)
      });
  }

  revokeInvitation(invitation: InvitationSummary): void {
    const workspace = this.activeWorkspace();
    if (!workspace || this.isBusy()) return;
    this.begin();
    this.api
      .revokeInvitation(workspace.id, invitation.id)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (updated) => {
          this.invitations.update((items) =>
            items.map((item) => (item.id === updated.id ? updated : item))
          );
          if (this.latestInvite()?.id === updated.id) this.latestInvite.set(null);
          this.notice.set(
            this.language() === 'th'
              ? 'ยกเลิกคำเชิญแล้ว'
              : 'Invitation revoked.'
          );
          this.refreshAudit();
        },
        error: (error) => this.fail(error)
      });
  }

  async copyInvite(): Promise<void> {
    const invitation = this.latestInvite();
    if (!invitation?.claim_token) return;
    await globalThis.navigator?.clipboard?.writeText(invitation.claim_token);
    this.notice.set(
      this.language() === 'th'
        ? 'คัดลอก one-time invite token แล้ว'
        : 'One-time invite token copied.'
    );
  }

  private loadWorkspaces(selectId?: string): void {
    this.begin();
    this.api
      .workspaces()
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (workspaces) => {
          this.workspaces.set(workspaces);
          const target =
            workspaces.find((item) => item.id === selectId) ?? workspaces[0];
          if (target) this.selectWorkspace(target);
        },
        error: (error) => {
          this.api.clearToken();
          this.fail(error);
        }
      });
  }

  private loadWorkspaceContext(workspace: WorkspaceSummary): void {
    this.begin();
    this.loadGitHubContext(workspace);
    const context = {
      repositories: this.api.repositories(workspace.id),
      members: this.api.members(workspace.id)
    };
    if (workspace.role === 'owner' || workspace.role === 'admin') {
      forkJoin({
        ...context,
        invitations: this.api.invitations(workspace.id),
        auditEvents: this.api.auditEvents(workspace.id)
      })
        .pipe(finalize(() => this.isBusy.set(false)))
        .subscribe({
          next: (data) => {
            this.repositories.set(data.repositories);
            this.loadConnectedChanges(workspace, data.repositories);
            this.members.set(data.members);
            this.invitations.set(data.invitations);
            this.auditEvents.set(data.auditEvents);
          },
          error: (error) => this.fail(error)
        });
      return;
    }
    forkJoin(context)
      .pipe(finalize(() => this.isBusy.set(false)))
      .subscribe({
        next: (data) => {
          this.repositories.set(data.repositories);
          this.loadConnectedChanges(workspace, data.repositories);
          this.members.set(data.members);
          this.invitations.set([]);
          this.auditEvents.set([]);
        },
        error: (error) => this.fail(error)
      });
  }

  private loadGitHubContext(workspace: WorkspaceSummary): void {
    if (!this.capabilities()?.github_app) {
      this.githubConnection.set(null);
      this.githubCandidates.set([]);
      return;
    }
    this.api.githubStatus(workspace.id).subscribe({
      next: (connection) => {
        this.githubConnection.set(connection);
        if (connection.connection_state !== 'connected') {
          this.githubCandidates.set([]);
          return;
        }
        this.api.githubRepositories(workspace.id).subscribe({
          next: (repositories) => this.githubCandidates.set(repositories),
          error: (error) => this.fail(error)
        });
      },
      error: (error: HttpErrorResponse) => {
        if (error.status === 404) {
          this.githubConnection.set(null);
          this.githubCandidates.set([]);
          return;
        }
        this.fail(error);
      }
    });
  }

  private loadConnectedChanges(
    workspace: WorkspaceSummary,
    repositories: RepositorySummary[]
  ): void {
    const connected = repositories.filter(
      (repository) => repository.data_mode === 'connected'
    );
    if (!connected.length) {
      this.connectedChanges.set([]);
      return;
    }
    forkJoin(
      connected.map((repository) =>
        this.api.connectedChanges(workspace.id, repository.id)
      )
    ).subscribe({
      next: (groups) =>
        this.connectedChanges.set(
          groups.flat().sort((a, b) => b.created_at.localeCompare(a.created_at))
        ),
      error: (error) => this.fail(error)
    });
  }

  private refreshAudit(): void {
    const workspace = this.activeWorkspace();
    if (!workspace || !this.canManage()) return;
    this.api.auditEvents(workspace.id).subscribe({
      next: (events) => this.auditEvents.set(events)
    });
  }

  private begin(): void {
    this.isBusy.set(true);
    this.error.set('');
    this.notice.set('');
  }

  private fail(error: unknown): void {
    this.isBusy.set(false);
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail;
      if (typeof detail === 'string') {
        this.error.set(detail);
        return;
      }
    }
    this.error.set(
      this.language() === 'th'
        ? 'ดำเนินการไม่สำเร็จ โปรดลองอีกครั้ง'
        : 'The action could not be completed. Try again.'
    );
  }
}
