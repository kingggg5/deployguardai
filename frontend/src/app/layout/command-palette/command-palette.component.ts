import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  computed,
  input,
  output,
  signal,
  viewChild
} from '@angular/core';

import { Language } from '../../core/i18n';
import { ScenarioSummary } from '../../core/models/deployguard.models';
import { WorkspaceView } from '../../core/navigation/workspace-link.service';

export type CommandPaletteAction =
  | { type: 'navigate'; view: WorkspaceView }
  | { type: 'scenario'; scenario: ScenarioSummary }
  | { type: 'share' }
  | { type: 'xray' };

interface PaletteItem {
  id: string;
  label: string;
  meta: string;
  keywords: string;
  action: CommandPaletteAction;
}

const COPY = {
  th: {
    close: 'ปิด Command palette',
    commands: 'คำสั่ง',
    copyLink: 'คัดลอกลิงก์มุมมองนี้',
    dora: 'เปิดตัวชี้วัด DORA',
    empty: 'ไม่พบคำสั่งที่ตรงกัน',
    investigation: 'เปิดการสืบสวน',
    open: 'เปิด Command palette',
    operations: 'เปิดศูนย์ปฏิบัติการ',
    placeholder: 'ค้นหาหน้า Repository หรือคำสั่ง…',
    repositories: 'Repository',
    risk: 'เปิดการประเมิน Change risk',
    scenarioLab: 'เปิด Scenario Lab',
    search: 'ค้นหาคำสั่ง',
    shareMeta: 'Deep link · ไม่เปลี่ยนสิทธิ์เข้าถึง',
    shortcut: 'Ctrl K',
    title: 'Command center',
    xray: 'สลับ Evidence X-ray'
  },
  en: {
    close: 'Close command palette',
    commands: 'Commands',
    copyLink: 'Copy this view link',
    dora: 'Open DORA metrics',
    empty: 'No matching command',
    investigation: 'Open investigation',
    open: 'Open command palette',
    operations: 'Open operations center',
    placeholder: 'Search pages, repositories, or commands…',
    repositories: 'Repositories',
    risk: 'Open change risk',
    scenarioLab: 'Open Scenario Lab',
    search: 'Search commands',
    shareMeta: 'Deep link · does not change access',
    shortcut: 'Ctrl K',
    title: 'Command center',
    xray: 'Toggle Evidence X-ray'
  }
} as const;

@Component({
  selector: 'app-command-palette',
  standalone: true,
  templateUrl: './command-palette.component.html',
  styleUrl: './command-palette.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class CommandPaletteComponent {
  readonly scenarios = input.required<ScenarioSummary[]>();
  readonly language = input.required<Language>();
  readonly actionSelected = output<CommandPaletteAction>();

  private readonly searchInput =
    viewChild<ElementRef<HTMLInputElement>>('searchInput');

  readonly isOpen = signal(false);
  readonly query = signal('');
  readonly labels = computed(() => COPY[this.language()]);
  readonly items = computed<PaletteItem[]>(() => {
    const labels = this.labels();
    const commands: PaletteItem[] = [
      {
        id: 'investigation',
        label: labels.investigation,
        meta: labels.commands,
        keywords: 'incident evidence rca root cause',
        action: { type: 'navigate', view: 'investigation' }
      },
      {
        id: 'risk',
        label: labels.risk,
        meta: labels.commands,
        keywords: 'change pull request pre deploy',
        action: { type: 'navigate', view: 'change_risk' }
      },
      {
        id: 'dora',
        label: labels.dora,
        meta: labels.commands,
        keywords: 'metrics deployment frequency lead time mttr',
        action: { type: 'navigate', view: 'dora' }
      },
      {
        id: 'scenarios',
        label: labels.scenarioLab,
        meta: labels.commands,
        keywords: 'synthetic demo lab',
        action: { type: 'navigate', view: 'scenarios' }
      },
      {
        id: 'operations',
        label: labels.operations,
        meta: labels.commands,
        keywords: 'operations service catalog risk policy events incident notifications',
        action: { type: 'navigate', view: 'operations' }
      },
      {
        id: 'workspace',
        label:
          this.language() === 'th'
            ? 'ตั้งค่า Workspace และทีม'
            : 'Set up workspace and team',
        meta: labels.commands,
        keywords: 'workspace repository team invite members access',
        action: { type: 'navigate', view: 'workspace' }
      },
      {
        id: 'share',
        label: labels.copyLink,
        meta: labels.shareMeta,
        keywords: 'share copy url deep link',
        action: { type: 'share' }
      },
      {
        id: 'xray',
        label: labels.xray,
        meta: labels.commands,
        keywords: 'evidence annotations topology',
        action: { type: 'xray' }
      }
    ];
    const repositories = this.scenarios().map<PaletteItem>((scenario) => ({
      id: `scenario-${scenario.id}`,
      label: scenario.repository,
      meta: `${labels.repositories} · ${scenario.name}`,
      keywords: `${scenario.repository} ${scenario.name} ${scenario.description}`,
      action: { type: 'scenario', scenario }
    }));
    return [...commands, ...repositories];
  });
  readonly filteredItems = computed(() => {
    const query = this.query().trim().toLocaleLowerCase();
    if (!query) return this.items();
    return this.items().filter((item) =>
      `${item.label} ${item.meta} ${item.keywords}`
        .toLocaleLowerCase()
        .includes(query)
    );
  });

  @HostListener('document:keydown', ['$event'])
  onDocumentKeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.isOpen() ? this.close() : this.open();
      return;
    }
    if (event.key === 'Escape' && this.isOpen()) this.close();
  }

  open(): void {
    this.isOpen.set(true);
    setTimeout(() => this.searchInput()?.nativeElement.focus());
  }

  close(): void {
    this.isOpen.set(false);
    this.query.set('');
  }

  updateQuery(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) this.query.set(target.value);
  }

  select(item: PaletteItem): void {
    this.actionSelected.emit(item.action);
    this.close();
  }
}
