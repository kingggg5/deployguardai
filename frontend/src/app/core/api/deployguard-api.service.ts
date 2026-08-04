import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import {
  AnalyzeChangeRequest,
  ChangeDetail,
  DatasetConsentRequest,
  DatasetConsentSummary,
  DatasetPurpose,
  DatasetReadiness,
  DoraMetrics,
  EvidenceSynthesisResponse,
  FeedbackRequest,
  HealthResponse,
  IncidentDetail,
  Overview,
  PostmortemSnapshotSummary,
  ScenarioSummary
} from '../models/deployguard.models';
import { DEPLOYGUARD_API_BASE } from '../config/deployguard-config';

@Injectable({ providedIn: 'root' })
export class DeployGuardApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = inject(DEPLOYGUARD_API_BASE);

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.apiBase}/health`);
  }

  getOverview(): Observable<Overview> {
    return this.http.get<Overview>(`${this.apiBase}/overview`);
  }

  getScenarios(): Observable<ScenarioSummary[]> {
    return this.http.get<ScenarioSummary[]>(`${this.apiBase}/scenarios`);
  }

  activateScenario(scenarioId: string): Observable<Overview> {
    return this.http.post<Overview>(
      `${this.apiBase}/scenarios/${encodeURIComponent(scenarioId)}/activate`,
      {}
    );
  }

  getChanges(): Observable<ChangeDetail[]> {
    return this.http.get<ChangeDetail[]>(`${this.apiBase}/changes`);
  }

  getChange(changeId: string): Observable<ChangeDetail> {
    return this.http.get<ChangeDetail>(
      `${this.apiBase}/changes/${encodeURIComponent(changeId)}`
    );
  }

  analyzeChange(request: AnalyzeChangeRequest): Observable<ChangeDetail> {
    return this.http.post<ChangeDetail>(`${this.apiBase}/changes/analyze`, request);
  }

  getIncidents(): Observable<IncidentDetail[]> {
    return this.http.get<IncidentDetail[]>(`${this.apiBase}/incidents`);
  }

  getIncident(incidentId: string): Observable<IncidentDetail> {
    return this.http.get<IncidentDetail>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}`
    );
  }

  synthesizeIncident(incidentId: string): Observable<EvidenceSynthesisResponse> {
    return this.http.post<EvidenceSynthesisResponse>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/synthesize`,
      {}
    );
  }

  submitFeedback(
    incidentId: string,
    request: FeedbackRequest
  ): Observable<IncidentDetail> {
    return this.http.post<IncidentDetail>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/feedback`,
      request
    );
  }

  getDoraMetrics(): Observable<DoraMetrics> {
    return this.http.get<DoraMetrics>(`${this.apiBase}/metrics/dora`);
  }

  exportPostMortem(incidentId: string): Observable<string> {
    return this.http.get(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/export-markdown`,
      { responseType: 'text' }
    );
  }

  getDatasetReadiness(
    incidentId: string,
    purpose: DatasetPurpose = 'evaluation'
  ): Observable<DatasetReadiness> {
    return this.http.get<DatasetReadiness>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/dataset-readiness`,
      { params: { purpose } }
    );
  }

  createPostmortemSnapshot(
    incidentId: string
  ): Observable<PostmortemSnapshotSummary> {
    return this.http.post<PostmortemSnapshotSummary>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/postmortem-snapshots`,
      {}
    );
  }

  recordDatasetConsent(
    incidentId: string,
    request: DatasetConsentRequest
  ): Observable<DatasetConsentSummary> {
    return this.http.post<DatasetConsentSummary>(
      `${this.apiBase}/incidents/${encodeURIComponent(incidentId)}/dataset-consent`,
      request
    );
  }
}
