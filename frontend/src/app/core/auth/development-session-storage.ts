const DEVELOPMENT_SESSION_TOKEN_KEY = 'deployguard-development-session';

export function readDevelopmentSessionToken(): string | null {
  try {
    return globalThis.localStorage?.getItem(DEVELOPMENT_SESSION_TOKEN_KEY) ?? null;
  } catch {
    return null;
  }
}

export function writeDevelopmentSessionToken(token: string): void {
  try {
    globalThis.localStorage?.setItem(DEVELOPMENT_SESSION_TOKEN_KEY, token);
  } catch {
    // Development sessions can continue in the current response when storage is blocked.
  }
}

export function clearDevelopmentSessionToken(): void {
  try {
    globalThis.localStorage?.removeItem(DEVELOPMENT_SESSION_TOKEN_KEY);
  } catch {
    // Storage is optional in development.
  }
}
