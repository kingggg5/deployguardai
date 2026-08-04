import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DeployGuardApiService } from './deployguard-api.service';
import { DEPLOYGUARD_API_BASE } from '../config/deployguard-config';
import { makeOverview, scenarioFixtures } from '../../test-fixtures';

describe('DeployGuardApiService', () => {
  let service: DeployGuardApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        DeployGuardApiService,
        { provide: DEPLOYGUARD_API_BASE, useValue: '/test-api/v1' },
        provideHttpClient(),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(DeployGuardApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads the bare scenarios array from the injected API base', () => {
    let response = scenarioFixtures.slice(0, 0);
    service.getScenarios().subscribe((value) => (response = value));

    const request = http.expectOne('/test-api/v1/scenarios');
    expect(request.request.method).toBe('GET');
    request.flush(scenarioFixtures);
    expect(response).toEqual(scenarioFixtures);
  });

  it('activates an encoded scenario with an empty object body', () => {
    service.activateScenario('queue/backlog').subscribe();

    const request = http.expectOne(
      '/test-api/v1/scenarios/queue%2Fbacklog/activate'
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush(makeOverview('queue-backlog'));
  });

  it('submits a typed human verdict and receives the updated incident', () => {
    const payload = {
      hypothesis_id: 'hyp-db',
      verdict: 'confirmed' as const,
      note: 'The lock holder matches the changed transaction.'
    };
    service.submitFeedback('inc/checkout', payload).subscribe();

    const request = http.expectOne(
      '/test-api/v1/incidents/inc%2Fcheckout/feedback'
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush(makeOverview().active_incident!);
  });

  it('requests an evidence synthesis with an encoded incident id', () => {
    service.synthesizeIncident('inc/checkout').subscribe();

    const request = http.expectOne(
      '/test-api/v1/incidents/inc%2Fcheckout/synthesize'
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush({});
  });

  it('fetches an immutable change by encoded id', () => {
    service.getChange('change/checkout').subscribe();

    const request = http.expectOne(
      '/test-api/v1/changes/change%2Fcheckout'
    );
    expect(request.request.method).toBe('GET');
    request.flush(makeOverview().active_change);
  });
});
