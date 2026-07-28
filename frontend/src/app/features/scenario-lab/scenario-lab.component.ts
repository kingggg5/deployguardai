import {
  ChangeDetectionStrategy,
  Component,
  input,
  output
} from '@angular/core';

import { Language, TRANSLATIONS } from '../../core/i18n';
import { ScenarioSummary } from '../../core/models/deployguard.models';

@Component({
  selector: 'app-scenario-lab',
  standalone: true,
  templateUrl: './scenario-lab.component.html',
  styleUrl: './scenario-lab.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class ScenarioLabComponent {
  readonly scenarios = input.required<ScenarioSummary[]>();
  readonly activeScenarioId = input.required<string>();
  readonly switchingScenarioId = input.required<string | null>();
  readonly language = input.required<Language>();
  readonly scenarioSelected = output<ScenarioSummary>();

  t(key: string): string {
    return (
      TRANSLATIONS[this.language()][key] ??
      TRANSLATIONS.en[key] ??
      key
    );
  }
}
