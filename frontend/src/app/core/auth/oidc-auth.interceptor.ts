import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { OidcSecurityService } from 'angular-auth-oidc-client';
import { switchMap, take } from 'rxjs';
import { readDevelopmentSessionToken } from './development-session-storage';

export const oidcAuthInterceptor: HttpInterceptorFn = (request, next) => {
  if (
    request.headers.has('Authorization') ||
    request.url.endsWith('/capabilities')
  ) {
    return next(request);
  }
  return inject(OidcSecurityService)
    .getAccessToken()
    .pipe(
      take(1),
      switchMap((oidcToken) => {
        const requestUrl = new URL(request.url, globalThis.location?.origin);
        const developmentToken =
          requestUrl.origin === globalThis.location?.origin
            ? readDevelopmentSessionToken()
            : null;
        const token = oidcToken || developmentToken;
        return next(
          token
            ? request.clone({
                setHeaders: { Authorization: `Bearer ${token}` }
              })
            : request
        );
      })
    );
};
