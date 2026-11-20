import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../environments/environment';
import { PlansPage } from './plans-page';
import { PLANS_UNREACHABLE, Reminder, Task, WeeklyPlan } from './plans.service';

const API = environment.apiUrl;

const TASK: Task = {
  id: 't1',
  title: 'Finish essay',
  due_at: '2037-11-20T09:00:00Z',
  repeat_days: null,
  time_of_day: null,
  done: false,
  created_at: '2037-11-18T09:00:00Z',
};
const REMINDER: Reminder = {
  id: 'r1',
  title: 'call mom',
  remind_at: '2037-11-19T18:00:00Z',
  repeat_days: null,
  delivered: false,
};
const PLAN: WeeklyPlan = {
  id: 'w1',
  name: 'Get strong',
  sessions: [
    { day: 'monday', activity: 'upper body', minutes: 45 },
    { day: 'tuesday', activity: 'portfolio', minutes: null },
  ],
  created_at: '2037-11-18T09:00:00Z',
};

describe('PlansPage', () => {
  let fixture: ComponentFixture<PlansPage>;
  let http: HttpTestingController;
  let page: HTMLElement;

  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  async function load(tasks: Task[], reminders: Reminder[], plans: WeeklyPlan[]): Promise<void> {
    http.expectOne(`${API}/tasks`).flush(tasks);
    http.expectOne(`${API}/reminders`).flush(reminders);
    http.expectOne(`${API}/weekly-plans`).flush(plans);
    await settle();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlansPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PlansPage);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('shows tasks, reminders and weekly plans', async () => {
    await load([TASK], [REMINDER], [PLAN]);

    expect(page.querySelector('[data-testid="task"]')?.textContent).toContain('Finish essay');
    expect(page.querySelector('[data-testid="reminder"]')?.textContent).toContain('call mom');
    const plan = (page.querySelector('[data-testid="weekly-plan"]')?.textContent ?? '').replace(
      /\s+/g,
      ' ',
    );
    expect(plan).toContain('Get strong');
    expect(plan).toContain('Monday');
    expect(plan).toContain('upper body · 45 min');
  });

  it('suggests asking the companion when nothing is planned', async () => {
    await load([], [], []);

    expect(page.textContent).toContain('Nothing planned yet');
  });

  it('ticks a task off', async () => {
    await load([TASK], [], []);

    (page.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
    const request = http.expectOne({ method: 'PATCH', url: `${API}/tasks/t1` });
    expect(request.request.body).toEqual({ done: true });
    request.flush({ ...TASK, done: true });
    await settle();

    expect(page.querySelector('[data-testid="task"]')?.classList).toContain('done');
  });

  it('filters quests by progress', async () => {
    await load([TASK, { ...TASK, id: 't2', title: 'Water plants', done: true }], [], []);
    const titles = () =>
      Array.from(page.querySelectorAll('[data-testid="task"]')).map((t) => t.textContent?.trim());
    const filter = (label: string) =>
      Array.from(page.querySelectorAll('button')).find((b) => b.textContent?.trim() === label);

    expect(page.textContent).toContain('1 of 2 quests complete');
    expect(titles()).toHaveLength(2);

    filter('Completed')?.click();
    await settle();
    expect(titles()).toEqual([expect.stringContaining('Water plants')]);
    expect(filter('Completed')?.getAttribute('aria-pressed')).toBe('true');

    filter('In progress')?.click();
    await settle();
    expect(titles()).toEqual([expect.stringContaining('Finish essay')]);
  });

  it('deletes items', async () => {
    await load([TASK], [REMINDER], [PLAN]);

    (page.querySelector('[aria-label="Delete reminder call mom"]') as HTMLButtonElement).click();
    http.expectOne({ method: 'DELETE', url: `${API}/reminders/r1` }).flush(null);
    (
      page.querySelector('[aria-label="Delete weekly plan Get strong"]') as HTMLButtonElement
    ).click();
    http.expectOne({ method: 'DELETE', url: `${API}/weekly-plans/w1` }).flush(null);
    await settle();

    expect(page.querySelector('[data-testid="reminder"]')).toBeNull();
    expect(page.querySelector('[data-testid="weekly-plan"]')).toBeNull();
    expect(page.querySelector('[data-testid="task"]')).not.toBeNull();
  });

  it('explains when the backend cannot be reached', async () => {
    http.expectOne(`${API}/tasks`).flush('down', { status: 503, statusText: 'Unavailable' });
    http.expectOne(`${API}/reminders`).flush([]);
    http.expectOne(`${API}/weekly-plans`).flush([]);
    await settle();

    expect(page.querySelector('[role="alert"]')?.textContent).toContain(PLANS_UNREACHABLE);
  });

  it('shows a plan day without minutes as just the activity', async () => {
    await load([], [], [PLAN]);

    const plan = page.querySelector('[data-testid="weekly-plan"]')?.textContent ?? '';
    expect(plan.replace(/\s+/g, ' ')).toContain('Tuesday portfolio');
    expect(plan).not.toContain('portfolio ·');
  });

  it('labels repeating tasks and reminders with their days', async () => {
    const routine: Task = {
      ...TASK,
      due_at: null,
      repeat_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
      time_of_day: '09:00:00',
    };
    const daily: Reminder = {
      ...REMINDER,
      repeat_days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
    };

    await load([routine], [daily], []);

    expect(page.querySelector('[data-testid="task"]')?.textContent).toMatch(
      /Every weekday\s*·\s*9:00 AM/,
    );
    expect(page.querySelector('[data-testid="reminder"]')?.textContent).toContain('Every day');
  });
});
