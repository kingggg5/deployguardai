import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DeployGuardApiService, DEPLOYGUARD_API_BASE } from './deployguard-api.service';
import { makeOverview, scenarioFixtures } from '../../test-fixtures';

describe('DeployGuardApiService', () => {
  let service: DeployGuardApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        DeployGuardApiService,
        provideHttpClient(),
        provideHttpClientTesting()
      ]
    });
    service = TestBed.inject(DeployGuardApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads the bare scenarios array from the fixed local API base', () => {
    let response = scenarioFixtures.slice(0, 0);
    service.getScenarios().subscribe((value) => (response = value));

    const request = http.expectOne(`${DEPLOYGUARD_API_BASE}/scenarios`);
    expect(request.request.method).toBe('GET');
    request.flush(scenarioFixtures);
    expect(response).toEqual(scenarioFixtures);
  });

  it('activates an encoded scenario with an empty object body', () => {
    service.activateScenario('queue/backlog').subscribe();

    const request = http.expectOne(
      `${DEPLOYGUARD_API_BASE}/scenarios/queue%2Fbacklog/activate`
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
      `${DEPLOYGUARD_API_BASE}/incidents/inc%2Fcheckout/feedback`
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush(makeOverview().active_incident);
  });
});
