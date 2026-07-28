import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { OidcSecurityService } from 'angular-auth-oidc-client';
import { switchMap, take } from 'rxjs';

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
      switchMap((token) =>
        next(
          token
            ? request.clone({
                setHeaders: { Authorization: `Bearer ${token}` }
              })
            : request
        )
      )
    );
};
