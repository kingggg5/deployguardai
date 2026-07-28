import { HttpClient, provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig } from '@angular/core';
import {
  AbstractSecurityStorage,
  LogLevel,
  provideAuth,
  StsConfigHttpLoader,
  StsConfigLoader
} from 'angular-auth-oidc-client';
import { map } from 'rxjs';
import { oidcAuthInterceptor } from './core/auth/oidc-auth.interceptor';
import { MemorySecurityStorage } from './core/auth/memory-security-storage';
import { ProductCapabilities } from './core/models/workspace.models';

function oidcConfigLoader(http: HttpClient): StsConfigHttpLoader {
  const config = http
    .get<ProductCapabilities>('/api/v1/capabilities')
    .pipe(
      map((capabilities) => ({
        authority: capabilities.oidc_authority || globalThis.location.origin,
        clientId: capabilities.oidc_client_id || 'development-disabled',
        redirectUrl: `${globalThis.location.origin}/?view=workspace`,
        postLogoutRedirectUri: `${globalThis.location.origin}/?view=workspace`,
        scope: capabilities.oidc_scope || 'openid profile email',
        responseType: 'code',
        silentRenew: false,
        useRefreshToken: false,
        logLevel: LogLevel.Error
      }))
    );
  return new StsConfigHttpLoader(config);
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(withFetch(), withInterceptors([oidcAuthInterceptor])),
    provideAuth({
      loader: {
        provide: StsConfigLoader,
        useFactory: oidcConfigLoader,
        deps: [HttpClient]
      }
    }),
    { provide: AbstractSecurityStorage, useExisting: MemorySecurityStorage }
  ]
};
