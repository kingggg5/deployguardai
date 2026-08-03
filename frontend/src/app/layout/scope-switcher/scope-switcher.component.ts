import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
  signal
} from '@angular/core';

import { Language } from '../../core/i18n';
import { ScenarioSummary } from '../../core/models/deployguard.models';

const COPY = {
  th: {
    activeScope: 'ขอบเขตที่กำลังใช้งาน',
    close: 'ปิดตัวเลือก Repository',
    copyLink: 'คัดลอกลิงก์มุมมองนี้',
    repositorySearch: 'ค้นหา repository หรือสถานการณ์',
    repositorySearchLabel: 'ค้นหา Repository',
    selectRepository: 'เลือก Repository',
    synthetic: 'ข้อมูลสาธิต',
    connected: 'ข้อมูลเชื่อมต่อจริง',
    unscoped: 'ยังไม่เลือก Repository',
  },
  en: {
    activeScope: 'Active scope',
    close: 'Close repository selector',
    copyLink: 'Copy this view link',
    repositorySearch: 'Search repository or scenario',
    repositorySearchLabel: 'Search repositories',
    selectRepository: 'Select repository',
    synthetic: 'Synthetic data',
    connected: 'Connected data',
    unscoped: 'No repository selected',
  }
} as const;

@Component({
  selector: 'app-scope-switcher',
  standalone: true,
  templateUrl: './scope-switcher.component.html',
  styleUrl: './scope-switcher.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ScopeSwitcherComponent {
  readonly scenarios = input.required<ScenarioSummary[]>();
  readonly activeScenarioId = input.required<string>();
  readonly language = input.required<Language>();
  readonly scenarioSelected = output<ScenarioSummary>();
  readonly shareRequested = output<void>();

  readonly isOpen = signal(false);
  readonly query = signal('');

  readonly labels = computed(() => COPY[this.language()]);
  readonly activeScenario = computed(
    () =>
      this.scenarios().find(
        (scenario) => scenario.id === this.activeScenarioId()
      ) ?? null
  );
  readonly repositoryOwner = computed(
    () => this.activeScenario()?.repository.split('/')[0] ?? 'workspace'
  );
  readonly repositoryName = computed(() => {
    const repository = this.activeScenario()?.repository;
    if (!repository) return this.labels().selectRepository;
    return repository.split('/').slice(1).join('/') || repository;
  });
  readonly activeDataMode = computed(
    () => this.activeScenario()?.data_mode ?? 'unscoped'
  );
  readonly activeDataModeLabel = computed(() => {
    const mode = this.activeDataMode();
    if (mode === 'connected') return this.labels().connected;
    if (mode === 'synthetic') return this.labels().synthetic;
    return this.labels().unscoped;
  });
  readonly filteredScenarios = computed(() => {
    const query = this.query().trim().toLocaleLowerCase();
    if (!query) return this.scenarios();
    return this.scenarios().filter((scenario) =>
      `${scenario.repository} ${scenario.name} ${scenario.description}`
        .toLocaleLowerCase()
        .includes(query)
    );
  });

  toggle(): void {
    this.isOpen.update((value) => !value);
    if (!this.isOpen()) this.query.set('');
  }

  close(): void {
    this.isOpen.set(false);
    this.query.set('');
  }

  updateQuery(event: Event): void {
    const target = event.target;
    if (target instanceof HTMLInputElement) this.query.set(target.value);
  }

  selectScenario(scenario: ScenarioSummary): void {
    if (scenario.id !== this.activeScenarioId()) {
      this.scenarioSelected.emit(scenario);
    }
    this.close();
  }
}
