import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../environments/environment';
import { BACKEND_UNREACHABLE, MemoriesService } from './memories.service';
import { Memory } from './memory';

const URL = `${environment.apiUrl}/memories`;

export function memory(overrides: Partial<Memory> = {}): Memory {
  return {
    id: 'm1',
    kind: 'goal',
    content: 'Run a 5k by March',
    created_at: '2037-11-18T10:00:00Z',
    updated_at: '2037-11-18T10:00:00Z',
    expires_at: null,
    ...overrides,
  };
}

describe('MemoriesService', () => {
  let store: MemoriesService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [MemoriesService, provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(MemoriesService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function load(memories: Memory[]): Promise<void> {
    const done = store.load();
    http.expectOne({ method: 'GET', url: URL }).flush(memories);
    await done;
  }

  it('loads memories and groups them by kind', async () => {
    await load([memory(), memory({ id: 'm2', kind: 'habit', content: 'Reads at night' })]);

    expect(store.memories()).toHaveLength(2);
    expect(
      store
        .byKind()
        .get('goal')
        ?.map((m) => m.id),
    ).toEqual(['m1']);
    expect(
      store
        .byKind()
        .get('habit')
        ?.map((m) => m.id),
    ).toEqual(['m2']);
    expect(store.byKind().has('preference')).toBe(false);
  });

  it('updates a memory in place', async () => {
    await load([memory()]);

    const done = store.update('m1', { content: 'Run a 10k' });
    const request = http.expectOne({ method: 'PATCH', url: `${URL}/m1` });
    expect(request.request.body).toEqual({ content: 'Run a 10k' });
    request.flush(memory({ content: 'Run a 10k' }));
    await done;

    expect(store.memories()[0].content).toBe('Run a 10k');
  });

  it('removes one memory, then forgets everything', async () => {
    await load([memory(), memory({ id: 'm2' })]);

    const removed = store.remove('m1');
    http.expectOne({ method: 'DELETE', url: `${URL}/m1` }).flush(null);
    await removed;
    expect(store.memories().map((m) => m.id)).toEqual(['m2']);

    const forgotten = store.forgetEverything();
    http.expectOne({ method: 'DELETE', url: URL }).flush(null);
    await forgotten;
    expect(store.memories()).toEqual([]);
  });

  it('explains how to fix a failed request and keeps the data', async () => {
    await load([memory()]);

    const done = store.remove('m1');
    http.expectOne(`${URL}/m1`).flush('down', { status: 503, statusText: 'Unavailable' });
    await done;

    expect(store.error()).toBe(BACKEND_UNREACHABLE);
    expect(store.memories()).toHaveLength(1);
    expect(store.loading()).toBe(false);
  });
});
