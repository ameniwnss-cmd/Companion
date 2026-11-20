import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Memory, MemoryChanges, MemoryKind } from './memory';

export const BACKEND_UNREACHABLE = 'Could not reach the backend. Is it running?';

@Injectable()
export class MemoriesService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/memories`;

  private readonly _memories = signal<readonly Memory[]>([]);
  private readonly _error = signal<string | null>(null);
  private readonly _loading = signal(false);

  readonly memories = this._memories.asReadonly();
  readonly error = this._error.asReadonly();
  readonly loading = this._loading.asReadonly();
  readonly byKind = computed(() => {
    const groups = new Map<MemoryKind, Memory[]>();
    for (const memory of this._memories()) {
      groups.set(memory.kind, [...(groups.get(memory.kind) ?? []), memory]);
    }
    return groups;
  });

  async load(): Promise<void> {
    await this.run(async () => {
      this._memories.set(await firstValueFrom(this.http.get<Memory[]>(this.url)));
    });
  }

  async update(id: string, changes: MemoryChanges): Promise<void> {
    await this.run(async () => {
      const updated = await firstValueFrom(this.http.patch<Memory>(`${this.url}/${id}`, changes));
      this._memories.update((all) => all.map((m) => (m.id === id ? updated : m)));
    });
  }

  async remove(id: string): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.http.delete(`${this.url}/${id}`));
      this._memories.update((all) => all.filter((m) => m.id !== id));
    });
  }

  async forgetEverything(): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.http.delete(this.url));
      this._memories.set([]);
    });
  }

  private async run(request: () => Promise<void>): Promise<void> {
    this._loading.set(true);
    this._error.set(null);
    try {
      await request();
    } catch {
      this._error.set(BACKEND_UNREACHABLE);
    } finally {
      this._loading.set(false);
    }
  }
}
