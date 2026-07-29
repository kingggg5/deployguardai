import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { DEPLOYGUARD_API_BASE } from '../config/deployguard-config';
import { IncidentTimelineEvent } from '../models/deployguard.models';
import {
  IncidentLifecycle,
  IncidentLifecycleUpdateRequest,
  IncidentNoteRequest,
  OperationalEvent,
  OperationalEventCreateRequest,
  OperationalEventFilters,
  OperatorNotification,
  RiskPolicy,
  RiskPolicyUpdateRequest,
  ServiceCreateRequest,
  ServiceRecord,
  ServiceUpdateRequest
} from '../models/operations.models';
import { WorkspaceApiService } from './workspace-api.service';

@Injectable({ providedIn: 'root' })
export class OperationsApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBase = inject(DEPLOYGUARD_API_BASE);
  private readonly workspaceApi = inject(WorkspaceApiService);

  services(workspaceId: string): Observable<ServiceRecord[]> {
    return this.http.get<ServiceRecord[]>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/services`,
      { headers: this.headers() }
    );
  }

  createService(
    workspaceId: string,
    request: ServiceCreateRequest
  ): Observable<ServiceRecord> {
    return this.http.post<ServiceRecord>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/services`,
      request,
      { headers: this.headers() }
    );
  }

  service(serviceId: string): Observable<ServiceRecord> {
    return this.http.get<ServiceRecord>(
      `${this.apiBase}/services/${this.encode(serviceId)}`,
      { headers: this.headers() }
    );
  }

  updateService(
    serviceId: string,
    request: ServiceUpdateRequest
  ): Observable<ServiceRecord> {
    return this.http.patch<ServiceRecord>(
      `${this.apiBase}/services/${this.encode(serviceId)}`,
      request,
      { headers: this.headers() }
    );
  }

  riskPolicy(workspaceId: string): Observable<RiskPolicy> {
    return this.http.get<RiskPolicy>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/risk-policy`,
      { headers: this.headers() }
    );
  }

  updateRiskPolicy(
    workspaceId: string,
    request: RiskPolicyUpdateRequest
  ): Observable<RiskPolicy> {
    return this.http.put<RiskPolicy>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/risk-policy`,
      request,
      { headers: this.headers() }
    );
  }

  events(
    workspaceId: string,
    filters: OperationalEventFilters = {}
  ): Observable<OperationalEvent[]> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return this.http.get<OperationalEvent[]>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/events`,
      { headers: this.headers(), params }
    );
  }

  createEvent(
    workspaceId: string,
    request: OperationalEventCreateRequest
  ): Observable<OperationalEvent> {
    return this.http.post<OperationalEvent>(
      `${this.apiBase}/workspaces/${this.encode(workspaceId)}/events`,
      request,
      { headers: this.headers() }
    );
  }

  updateIncidentLifecycle(
    incidentId: string,
    request: IncidentLifecycleUpdateRequest
  ): Observable<IncidentLifecycle> {
    return this.http.patch<IncidentLifecycle>(
      `${this.apiBase}/incidents/${this.encode(incidentId)}/lifecycle`,
      request,
      { headers: this.headers() }
    );
  }

  addIncidentNote(
    incidentId: string,
    request: IncidentNoteRequest
  ): Observable<IncidentTimelineEvent> {
    return this.http.post<IncidentTimelineEvent>(
      `${this.apiBase}/incidents/${this.encode(incidentId)}/notes`,
      request,
      { headers: this.headers() }
    );
  }

  notifications(
    workspaceId?: string,
    unreadOnly = false,
    limit = 100
  ): Observable<OperatorNotification[]> {
    let params = new HttpParams()
      .set('unread_only', String(unreadOnly))
      .set('limit', String(limit));
    if (workspaceId) params = params.set('workspace_id', workspaceId);
    return this.http.get<OperatorNotification[]>(
      `${this.apiBase}/notifications`,
      { headers: this.headers(), params }
    );
  }

  markNotificationRead(notificationId: string): Observable<OperatorNotification> {
    return this.http.patch<OperatorNotification>(
      `${this.apiBase}/notifications/${this.encode(notificationId)}/read`,
      {},
      { headers: this.headers() }
    );
  }

  private encode(value: string): string {
    return encodeURIComponent(value);
  }

  private headers(): HttpHeaders {
    const token = this.workspaceApi.token();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }
}
