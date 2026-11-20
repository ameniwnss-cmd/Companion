import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../environments/environment';
import { MemoriesPage } from './memories-page';
import { memory } from './memories.service.spec';

const URL = `${environment.apiUrl}/memories`;

describe('MemoriesPage', () => {
  let fixture: ComponentFixture<MemoriesPage>;
  let http: HttpTestingController;
  let page: HTMLElement;

  const buttons = (label: string) =>
    Array.from(page.querySelectorAll('button')).filter((b) => b.textContent?.trim() === label);

  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MemoriesPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(MemoriesPage);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  const byLabel = (label: string) =>
    Array.from(page.querySelectorAll<HTMLButtonElement>(`button[aria-label="${label}"]`));

  it('tags each memory with its kind and filters by kind', async () => {
    http
      .expectOne(URL)
      .flush([memory(), memory({ id: 'm2', kind: 'preference', content: 'Morning workouts' })]);
    await settle();

    const cards = () => Array.from(page.querySelectorAll('[data-testid="memory"]'));
    expect(cards()).toHaveLength(2);
    expect(cards()[0].textContent).toContain('A LITTLE DREAM');
    expect(cards()[1].textContent).toContain('A PIECE OF YOU');
    expect(page.textContent).toContain('2 little memories');

    const filters = Array.from(page.querySelectorAll('[role="group"] button')).map((b) =>
      b.textContent?.trim(),
    );
    expect(filters).toEqual(['Everything', 'Goals', 'Preferences']);

    buttons('Preferences')[0].click();
    await settle();
    expect(cards()).toHaveLength(1);
    expect(cards()[0].textContent).toContain('Morning workouts');
  });

  it('forgets a single memory', async () => {
    http.expectOne(URL).flush([memory()]);
    await settle();

    byLabel('Forget memory')[0].click();
    http.expectOne({ method: 'DELETE', url: `${URL}/m1` }).flush(null);
    await settle();

    expect(page.querySelectorAll('[data-testid="memory"]')).toHaveLength(0);
  });

  it('shows a friendly empty state', async () => {
    http.expectOne(URL).flush([]);
    await settle();

    expect(page.textContent).toContain('Nothing yet');
    expect(buttons('Forget everything')).toHaveLength(0);
  });

  it('edits a memory inline', async () => {
    http.expectOne(URL).flush([memory()]);
    await settle();

    byLabel('Edit memory')[0].click();
    await settle();
    const input = page.querySelector('textarea') as HTMLTextAreaElement;
    expect(input.value).toBe('Run a 5k by March');
    input.value = 'Run a 10k by June';
    input.dispatchEvent(new Event('input'));
    buttons('Save')[0].click();

    const request = http.expectOne({ method: 'PATCH', url: `${URL}/m1` });
    expect(request.request.body).toEqual({ content: 'Run a 10k by June' });
    request.flush(memory({ content: 'Run a 10k by June' }));
    await settle();

    expect(page.querySelector('textarea')).toBeNull();
    expect(page.textContent).toContain('Run a 10k by June');
  });

  it('asks before forgetting everything', async () => {
    http.expectOne(URL).flush([memory()]);
    await settle();
    const confirm = vi.spyOn(window, 'confirm');

    confirm.mockReturnValueOnce(false);
    buttons('Forget everything')[0].click();
    http.expectNone({ method: 'DELETE' });

    confirm.mockReturnValueOnce(true);
    buttons('Forget everything')[0].click();
    await fixture.whenStable();
    http.expectOne({ method: 'DELETE', url: URL }).flush(null);
    await settle();

    expect(page.querySelectorAll('[data-testid="memory"]')).toHaveLength(0);
  });
});
