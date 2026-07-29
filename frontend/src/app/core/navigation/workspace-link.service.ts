import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

export type WorkspaceView =
  | 'investigation'
  | 'change_risk'
  | 'dora'
  | 'scenarios'
  | 'operations'
  | 'workspace';

export interface WorkspaceLinkTarget {
  changeId: string | null;
  workspaceId: string | null;
  repositoryId: string | null;
}

@Injectable({ providedIn: 'root' })
export class WorkspaceLinkService {
  private readonly document = inject(DOCUMENT);

  readView(): WorkspaceView {
    const view = this.readQueryParam('view');
    if (
      view === 'investigation' ||
      view === 'change_risk' ||
      view === 'dora' ||
      view === 'scenarios' ||
      view === 'operations' ||
      view === 'workspace'
    ) {
      return view;
    }
    return 'investigation';
  }

  readScenarioId(): string | null {
    return this.readQueryParam('scenario');
  }

  readTarget(): WorkspaceLinkTarget {
    return {
      changeId: this.readQueryParam('change'),
      workspaceId: this.readQueryParam('workspace'),
      repositoryId: this.readQueryParam('repository')
    };
  }

  sync(
    view: WorkspaceView,
    scenarioId: string,
    mode: 'push' | 'replace',
    target: WorkspaceLinkTarget | null | undefined = undefined
  ): void {
    const window = this.document.defaultView;
    if (!window) return;
    const url = this.createUrl(
      view,
      scenarioId,
      target === undefined ? this.readTarget() : target
    );
    if (mode === 'push' && window.location.href !== url) {
      window.history.pushState({}, '', url);
      return;
    }
    window.history.replaceState({}, '', url);
  }

  async copy(
    view: WorkspaceView,
    scenarioId: string,
    target: WorkspaceLinkTarget | null | undefined = undefined
  ): Promise<void> {
    const url = this.createUrl(
      view,
      scenarioId,
      target === undefined ? this.readTarget() : target
    );
    if (globalThis.navigator?.clipboard?.writeText) {
      await globalThis.navigator.clipboard.writeText(url);
      return;
    }
    this.copyFallback(url);
  }

  private createUrl(
    view: WorkspaceView,
    scenarioId: string,
    target: WorkspaceLinkTarget | null
  ): string {
    const location = this.document.defaultView?.location;
    const url = new URL(location?.href ?? 'http://localhost/');
    url.searchParams.set('view', view);
    this.writeQueryParam(url, 'scenario', scenarioId);
    this.writeQueryParam(url, 'change', target?.changeId ?? null);
    this.writeQueryParam(url, 'workspace', target?.workspaceId ?? null);
    this.writeQueryParam(url, 'repository', target?.repositoryId ?? null);
    return url.toString();
  }

  private writeQueryParam(
    url: URL,
    key: string,
    value: string | null
  ): void {
    if (value) {
      url.searchParams.set(key, value);
      return;
    }
    url.searchParams.delete(key);
  }

  private readQueryParam(key: string): string | null {
    const location = this.document.defaultView?.location;
    return location ? new URL(location.href).searchParams.get(key) : null;
  }

  private copyFallback(value: string): void {
    const textarea = this.document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    this.document.body.appendChild(textarea);
    textarea.select();
    const copied = this.document.execCommand('copy');
    textarea.remove();
    if (!copied) throw new Error('Copy command was rejected');
  }
}
