import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DEPLOYGUARD_API_BASE } from '../config/deployguard-config';
import { OperationsApiService } from './operations-api.service';

describe('OperationsApiService', () => {
  let service: OperationsApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        OperationsApiService,
        { provide: DEPLOYGUARD_API_BASE, useValue: '/test-api/v1' },
        provideHttpClient(),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(OperationsApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('uses tenant-scoped service endpoints', () => {
    const payload = {
      name: 'Checkout API',
      slug: 'checkout-api',
      description: 'Customer checkout orchestration',
      tier: 'tier_1' as const,
      lifecycle: 'active' as const,
      owner_team: 'Commerce Platform',
      repository_id: null,
      dependencies: ['payments-api'],
      runbook_url: 'https://runbooks.example/checkout',
      tags: ['checkout']
    };

    service.createService('workspace/one', payload).subscribe();
    const create = http.expectOne(
      '/test-api/v1/workspaces/workspace%2Fone/services'
    );
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual(payload);
    create.flush({});

    service.updateService('service/one', { owner_team: 'SRE' }).subscribe();
    const update = http.expectOne('/test-api/v1/services/service%2Fone');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ owner_team: 'SRE' });
    update.flush({});
  });

  it('serializes event filters and publishes a complete policy version', () => {
    service
      .events('workspace-1', {
        source: 'github',
        severity: 'warning',
        ingestion_status: 'correlated',
        limit: 50
      })
      .subscribe();
    const events = http.expectOne(
      (request) =>
        request.url === '/test-api/v1/workspaces/workspace-1/events' &&
        request.params.get('source') === 'github' &&
        request.params.get('severity') === 'warning' &&
        request.params.get('ingestion_status') === 'correlated' &&
        request.params.get('limit') === '50'
    );
    expect(events.request.method).toBe('GET');
    events.flush([]);

    const policy = {
      enabled: true,
      warn_threshold: 55,
      block_threshold: 80,
      require_tests: true,
      require_rollback: true,
      max_blast_radius: 8,
      version: 2
    };
    service.updateRiskPolicy('workspace-1', policy).subscribe();
    const update = http.expectOne(
      '/test-api/v1/workspaces/workspace-1/risk-policy'
    );
    expect(update.request.method).toBe('PUT');
    expect(update.request.body).toEqual(policy);
    update.flush({});
  });

  it('uses encoded incident lifecycle and note endpoints', () => {
    service
      .updateIncidentLifecycle('incident/checkout', {
        status: 'investigating',
        severity: 'sev2'
      })
      .subscribe();
    const lifecycle = http.expectOne(
      '/test-api/v1/incidents/incident%2Fcheckout/lifecycle'
    );
    expect(lifecycle.request.method).toBe('PATCH');
    expect(lifecycle.request.body).toEqual({
      status: 'investigating',
      severity: 'sev2'
    });
    lifecycle.flush({});

    service
      .addIncidentNote('incident/checkout', { note: 'Rollback validated.' })
      .subscribe();
    const note = http.expectOne(
      '/test-api/v1/incidents/incident%2Fcheckout/notes'
    );
    expect(note.request.method).toBe('POST');
    expect(note.request.body).toEqual({ note: 'Rollback validated.' });
    note.flush({});
  });

  it('loads a filtered inbox and marks one notification read', () => {
    service.notifications('workspace-1', true, 25).subscribe();
    const inbox = http.expectOne(
      (request) =>
        request.url === '/test-api/v1/notifications' &&
        request.params.get('workspace_id') === 'workspace-1' &&
        request.params.get('unread_only') === 'true' &&
        request.params.get('limit') === '25'
    );
    expect(inbox.request.method).toBe('GET');
    inbox.flush([]);

    service.markNotificationRead('notice/1').subscribe();
    const read = http.expectOne(
      '/test-api/v1/notifications/notice%2F1/read'
    );
    expect(read.request.method).toBe('PATCH');
    expect(read.request.body).toEqual({});
    read.flush({});
  });
});
