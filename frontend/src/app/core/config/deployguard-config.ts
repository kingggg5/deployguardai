import { DOCUMENT } from '@angular/common';
import { inject, InjectionToken } from '@angular/core';

export interface DeployGuardRuntimeConfig {
  apiBaseUrl?: string;
}

declare global {
  interface Window {
    __DEPLOYGUARD_CONFIG__?: DeployGuardRuntimeConfig;
  }
}

export const DEFAULT_DEPLOYGUARD_API_BASE = '/api/v1';

export const DEPLOYGUARD_API_BASE = new InjectionToken<string>(
  'DEPLOYGUARD_API_BASE',
  {
    providedIn: 'root',
    factory: () => {
      const document = inject(DOCUMENT);
      const metaValue = document
        .querySelector<HTMLMetaElement>('meta[name="deployguard-api-base"]')
        ?.content.trim();
      const runtimeValue = globalThis.window?.__DEPLOYGUARD_CONFIG__?.apiBaseUrl?.trim();
      return normalizeApiBase(runtimeValue || metaValue || DEFAULT_DEPLOYGUARD_API_BASE);
    }
  }
);

function normalizeApiBase(value: string): string {
  return value.replace(/\/+$/, '');
}
