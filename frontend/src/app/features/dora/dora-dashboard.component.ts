import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  input,
  output
} from '@angular/core';

import { Language, TRANSLATIONS } from '../../core/i18n';
import {
  DataMode,
  DoraMetrics
} from '../../core/models/deployguard.models';

@Component({
  selector: 'app-dora-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dora-dashboard.component.html',
  styleUrl: './dora-dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class DoraDashboardComponent {
  readonly metrics = input.required<DoraMetrics | null>();
  readonly isLoading = input.required<boolean>();
  readonly error = input.required<string>();
  readonly dataMode = input.required<DataMode>();
  readonly language = input.required<Language>();
  readonly retryRequested = output<void>();

  t(key: string): string {
    return (
      TRANSLATIONS[this.language()][key] ??
      TRANSLATIONS.en[key] ??
      key
    );
  }
}
