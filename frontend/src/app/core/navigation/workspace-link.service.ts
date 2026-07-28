import { DOCUMENT } from '@angular/common';
import { Injectable, inject } from '@angular/core';

export type WorkspaceView =
  | 'investigation'
  | 'change_risk'
  | 'dora'
  | 'scenarios'
  | 'workspace';

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
      view === 'workspace'
    ) {
      return view;
    }
    return 'investigation';
  }

  readScenarioId(): string | null {
    return this.readQueryParam('scenario');
  }

  sync(
    view: WorkspaceView,
    scenarioId: string,
    mode: 'push' | 'replace'
  ): void {
    const window = this.document.defaultView;
    if (!window) return;
    const url = this.createUrl(view, scenarioId);
    if (mode === 'push' && window.location.href !== url) {
      window.history.pushState({}, '', url);
      return;
    }
    window.history.replaceState({}, '', url);
  }

  async copy(view: WorkspaceView, scenarioId: string): Promise<void> {
    const url = this.createUrl(view, scenarioId);
    if (globalThis.navigator?.clipboard?.writeText) {
      await globalThis.navigator.clipboard.writeText(url);
      return;
    }
    this.copyFallback(url);
  }

  private createUrl(view: WorkspaceView, scenarioId: string): string {
    const location = this.document.defaultView?.location;
    const url = new URL(location?.href ?? 'http://localhost/');
    url.searchParams.set('view', view);
    if (scenarioId) url.searchParams.set('scenario', scenarioId);
    return url.toString();
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
