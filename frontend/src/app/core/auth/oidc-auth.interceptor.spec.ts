import {
  HttpClient,
  provideHttpClient,
  withInterceptors
} from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { OidcSecurityService } from 'angular-auth-oidc-client';
import { of } from 'rxjs';
import {
  clearDevelopmentSessionToken,
  writeDevelopmentSessionToken
} from './development-session-storage';
import { oidcAuthInterceptor } from './oidc-auth.interceptor';

describe('oidcAuthInterceptor', () => {
  let http: HttpTestingController;

  afterEach(() => {
    clearDevelopmentSessionToken();
    http.verify();
  });

  function configure(oidcToken: string): void {
    TestBed.configureTestingModule({
      providers: [
        {
          provide: OidcSecurityService,
          useValue: { getAccessToken: vi.fn(() => of(oidcToken)) }
        },
        provideHttpClient(withInterceptors([oidcAuthInterceptor])),
        provideHttpClientTesting()
      ]
    });
    http = TestBed.inject(HttpTestingController);
  }

  it('uses the in-memory OIDC token when one is available', () => {
    writeDevelopmentSessionToken('development-token');
    configure('oidc-token');

    TestBed.inject(HttpClient).get('/api/v1/overview').subscribe();

    const request = http.expectOne('/api/v1/overview');
    expect(request.request.headers.get('Authorization')).toBe(
      'Bearer oidc-token'
    );
    request.flush({});
  });

  it('falls back to the development session for every API client', () => {
    writeDevelopmentSessionToken('development-token');
    configure('');

    TestBed.inject(HttpClient).get('/api/v1/overview').subscribe();

    const request = http.expectOne('/api/v1/overview');
    expect(request.request.headers.get('Authorization')).toBe(
      'Bearer development-token'
    );
    request.flush({});
  });
});
