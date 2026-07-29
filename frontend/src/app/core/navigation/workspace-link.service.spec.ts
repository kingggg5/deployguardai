import { TestBed } from '@angular/core/testing';
import { WorkspaceLinkService } from './workspace-link.service';

describe('WorkspaceLinkService', () => {
  let service: WorkspaceLinkService;

  beforeEach(() => {
    window.history.replaceState({}, '', '/?view=operations&scenario=checkout');
    TestBed.configureTestingModule({});
    service = TestBed.inject(WorkspaceLinkService);
  });

  it('restores the Operations Center from the query-param view contract', () => {
    expect(service.readView()).toBe('operations');
    expect(service.readScenarioId()).toBe('checkout');
  });

  it('keeps the operations view when replacing scenario scope', () => {
    service.sync('operations', 'payments', 'replace');

    expect(window.location.search).toContain('view=operations');
    expect(window.location.search).toContain('scenario=payments');
  });

  it('parses and preserves an immutable change tenant target', () => {
    window.history.replaceState(
      {},
      '',
      '/?view=change_risk&change=change-42&workspace=workspace-1&repository=repo-7'
    );

    expect(service.readTarget()).toEqual({
      changeId: 'change-42',
      workspaceId: 'workspace-1',
      repositoryId: 'repo-7'
    });

    service.sync('investigation', 'checkout', 'replace');
    expect(window.location.search).toContain('change=change-42');
    expect(window.location.search).toContain('workspace=workspace-1');
    expect(window.location.search).toContain('repository=repo-7');
  });

  it('builds an encoded change link and can explicitly clear stale scope', () => {
    service.sync('change_risk', 'checkout', 'replace', {
      changeId: 'change/42',
      workspaceId: 'workspace one',
      repositoryId: 'repo/7'
    });
    const target = new URL(window.location.href);
    expect(target.searchParams.get('change')).toBe('change/42');
    expect(target.searchParams.get('workspace')).toBe('workspace one');
    expect(target.searchParams.get('repository')).toBe('repo/7');

    service.sync('scenarios', 'checkout', 'replace', null);
    expect(window.location.search).not.toContain('change=');
    expect(window.location.search).not.toContain('workspace=');
    expect(window.location.search).not.toContain('repository=');
  });
});
