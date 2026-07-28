import { Injectable } from '@angular/core';
import { AbstractSecurityStorage } from 'angular-auth-oidc-client';

@Injectable({ providedIn: 'root' })
export class MemorySecurityStorage implements AbstractSecurityStorage {
  private readonly values = new Map<string, string>();

  read(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  write(key: string, value: string): void {
    this.values.set(key, value);
  }

  remove(key: string): void {
    this.values.delete(key);
  }

  clear(): void {
    this.values.clear();
  }
}
