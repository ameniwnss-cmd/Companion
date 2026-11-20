import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../environments/environment';
import { Reminder, Task } from '../plans/plans.service';
import { SOCKET_FACTORY } from '../session/companion-session';
import { FakePlayer, FakeSocket } from '../session/testing/fakes';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';
import { Room } from './room';

const API = environment.apiUrl;

class QuietPlayer extends FakePlayer {
  readonly playing = signal(false);
  level(): number {
    return 0;
  }
}

class IdleRecorder {
  readonly recording = signal(false);
  level(): number {
    return 0;
  }
}

function today(hour: number): string {
  const date = new Date();
  date.setHours(hour, 0, 0, 0);
  return date.toISOString();
}

const OPEN: Task = { id: 't1', title: 'Stretch', due_at: null, done: false, created_at: today(8) };
const DONE: Task = { ...OPEN, id: 't2', title: 'Breakfast', done: true };
const LATER: Task = { ...OPEN, id: 't3', title: 'Tax return', due_at: '2099-01-01T09:00:00Z' };
const REMINDER: Reminder = { id: 'r1', title: 'Call mom', remind_at: today(23), delivered: false };

describe('Room', () => {
  let socket: FakeSocket;
  let fixture: ComponentFixture<Room>;
  let http: HttpTestingController;
  let page: HTMLElement;

  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
  }

  async function load(tasks: Task[], reminders: Reminder[]): Promise<void> {
    http.expectOne(`${API}/tasks`).flush(tasks);
    http.expectOne(`${API}/reminders`).flush(reminders);
    http.expectOne(`${API}/workout-plans`).flush([]);
    await settle();
  }

  beforeEach(async () => {
    socket = new FakeSocket();
    await TestBed.configureTestingModule({
      imports: [Room],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: Recorder, useValue: new IdleRecorder() },
        { provide: AudioPlayer, useValue: new QuietPlayer() },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Room);
    page = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it("shows today's open quests and reminders next to the companion", async () => {
    await load([OPEN, DONE, LATER], [REMINDER]);

    const quests = Array.from(page.querySelectorAll('[data-testid="today-task"]'));
    expect(quests.map((q) => q.textContent?.trim())).toEqual(['Stretch']);
    expect(page.querySelector('[data-testid="today-reminder"]')?.textContent).toContain('Call mom');
    expect(page.querySelector('app-orb')).not.toBeNull();
  });

  it('completes a quest from the room', async () => {
    await load([OPEN], []);

    (page.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
    const request = http.expectOne({ method: 'PATCH', url: `${API}/tasks/t1` });
    expect(request.request.body).toEqual({ done: true });
    request.flush({ ...OPEN, done: true });
    await settle();

    expect(page.querySelector('[data-testid="today-task"]')).toBeNull();
    expect(page.textContent).toContain('All clear');
  });

  it('refreshes the lists after the user confirms a new plan', async () => {
    await load([], []);

    socket.emit({ type: 'pending_action', id: 'a1', kind: 'task', summary: 'Stretch' });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();
    await load([OPEN], []);

    expect(page.querySelector('[data-testid="today-task"]')?.textContent).toContain('Stretch');
  });
});
