import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SOCKET_FACTORY } from '../session/companion-session';
import { AlertPermission, NOTIFIER, Notifier, ReminderAlerts } from '../session/reminder-alerts';
import { FakePlayer, FakeSocket } from '../session/testing/fakes';
import { AudioPlayer } from '../voice/audio-player';
import { ReminderToast } from './reminder-toast';

class FakeNotifier implements Notifier {
  granted: AlertPermission = 'default';
  readonly shown: string[] = [];
  asked = 0;

  permission(): AlertPermission {
    return this.granted;
  }

  request(): Promise<AlertPermission> {
    this.asked += 1;
    this.granted = 'granted';
    return Promise.resolve(this.granted);
  }

  show(_title: string, body: string): void {
    this.shown.push(body);
  }
}

describe('ReminderToast', () => {
  let socket: FakeSocket;
  let player: FakePlayer;
  let notifier: FakeNotifier;
  let fixture: ComponentFixture<ReminderToast>;
  let page: HTMLElement;

  const toast = () => page.querySelector('[data-testid="reminder-alert"]');

  async function remind(id: string, title: string): Promise<void> {
    socket.emit({ type: 'reminder_due', id, title, text: `Hey, reminder: ${title}.` });
    await fixture.whenStable();
  }

  function setUp(granted: AlertPermission): void {
    socket = new FakeSocket();
    player = new FakePlayer();
    notifier = new FakeNotifier();
    notifier.granted = granted;
    TestBed.configureTestingModule({
      imports: [ReminderToast],
      providers: [
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: AudioPlayer, useValue: player },
        { provide: NOTIFIER, useValue: notifier },
      ],
    });
    fixture = TestBed.createComponent(ReminderToast);
    page = fixture.nativeElement as HTMLElement;
  }

  afterEach(() => vi.restoreAllMocks());

  it('shows a due reminder with a chime until it is dismissed', async () => {
    setUp('default');

    await remind('r1', 'stretch');

    expect(toast()?.textContent).toContain('Hey, reminder: stretch.');
    expect(player.chimes).toBe(1);

    (toast()?.querySelector('button') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(toast()).toBeNull();
  });

  it('chimes once for each new reminder', async () => {
    setUp('default');

    await remind('r1', 'stretch');
    await fixture.whenStable();
    await remind('r2', 'water');

    expect(player.chimes).toBe(2);
    expect(toast()?.textContent).toContain('water');
  });

  it('pops up a system notification only when allowed and the app is in the background', async () => {
    setUp('granted');
    const focus = vi.spyOn(document, 'hasFocus');

    focus.mockReturnValue(true);
    await remind('r1', 'stretch');
    expect(notifier.shown).toEqual([]);

    focus.mockReturnValue(false);
    await remind('r2', 'water');
    expect(notifier.shown).toEqual(['Hey, reminder: water.']);
  });

  it('asks for permission when the user turns pop-up alerts on', async () => {
    setUp('default');
    const alerts = TestBed.inject(ReminderAlerts);

    await alerts.enable();

    expect(notifier.asked).toBe(1);
    expect(alerts.permission()).toBe('granted');
  });
});
