import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import {
  AnalyzeChangeRequest,
  ChangeDetail,
  DoraMetrics,
  FeedbackRequest,
  HealthResponse,
  IncidentDetail,
  Overview,
  ScenarioSummary
} from '../models/deployguard.models';

export const DEPLOYGUARD_API_BASE = 'http://127.0.0.1:8100/api/v1';

@Injectable({ providedIn: 'root' })
export class DeployGuardApiService {
  private readonly http = inject(HttpClient);

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${DEPLOYGUARD_API_BASE}/health`);
  }

  getOverview(): Observable<Overview> {
    return this.http.get<Overview>(`${DEPLOYGUARD_API_BASE}/overview`);
  }

  getScenarios(): Observable<ScenarioSummary[]> {
    return this.http.get<ScenarioSummary[]>(`${DEPLOYGUARD_API_BASE}/scenarios`);
  }

  activateScenario(scenarioId: string): Observable<Overview> {
    return this.http.post<Overview>(
      `${DEPLOYGUARD_API_BASE}/scenarios/${encodeURIComponent(scenarioId)}/activate`,
      {}
    );
  }

  getChanges(): Observable<ChangeDetail[]> {
    return this.http.get<ChangeDetail[]>(`${DEPLOYGUARD_API_BASE}/changes`);
  }

  getChange(changeId: string): Observable<ChangeDetail> {
    return this.http.get<ChangeDetail>(
      `${DEPLOYGUARD_API_BASE}/changes/${encodeURIComponent(changeId)}`
    );
  }

  analyzeChange(request: AnalyzeChangeRequest): Observable<ChangeDetail> {
    return this.http.post<ChangeDetail>(`${DEPLOYGUARD_API_BASE}/changes/analyze`, request);
  }

  getIncidents(): Observable<IncidentDetail[]> {
    return this.http.get<IncidentDetail[]>(`${DEPLOYGUARD_API_BASE}/incidents`);
  }

  getIncident(incidentId: string): Observable<IncidentDetail> {
    return this.http.get<IncidentDetail>(
      `${DEPLOYGUARD_API_BASE}/incidents/${encodeURIComponent(incidentId)}`
    );
  }

  submitFeedback(
    incidentId: string,
    request: FeedbackRequest
  ): Observable<IncidentDetail> {
    return this.http.post<IncidentDetail>(
      `${DEPLOYGUARD_API_BASE}/incidents/${encodeURIComponent(incidentId)}/feedback`,
      request
    );
  }

  getDoraMetrics(): Observable<DoraMetrics> {
    return this.http.get<DoraMetrics>(`${DEPLOYGUARD_API_BASE}/metrics/dora`);
  }

  exportPostMortem(incidentId: string): Observable<string> {
    return this.http.get(
      `${DEPLOYGUARD_API_BASE}/incidents/${encodeURIComponent(incidentId)}/export-markdown`,
      { responseType: 'text' }
    );
  }
}
