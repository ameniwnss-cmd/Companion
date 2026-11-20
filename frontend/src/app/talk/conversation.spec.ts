import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SOCKET_FACTORY } from '../session/companion-session';
import { MICROPHONE_BLOCKED } from '../session/push-to-talk';
import { FakePlayer, FakeSocket } from '../session/testing/fakes';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';
import { Conversation } from './conversation';

class FakeRecorder {
  readonly recording = signal(false);
  blocked = false;
  result: Blob | null = new Blob(['speech']);

  start(): Promise<void> {
    if (this.blocked) {
      return Promise.reject(new Error('denied'));
    }
    this.recording.set(true);
    return Promise.resolve();
  }

  stop(): Promise<Blob | null> {
    const wasRecording = this.recording();
    this.recording.set(false);
    return Promise.resolve(wasRecording ? this.result : null);
  }

  level(): number {
    return 0.5;
  }
}

class PlayingPlayer extends FakePlayer {
  readonly playing = signal(false);

  level(): number {
    return 0.3;
  }
}

describe('Conversation', () => {
  let socket: FakeSocket;
  let recorder: FakeRecorder;
  let player: PlayingPlayer;
  let fixture: ComponentFixture<Conversation>;
  let page: HTMLElement;

  const orb = () => page.querySelector('app-orb') as HTMLElement;
  const hint = () => page.querySelector('[data-testid="hint"]')?.textContent?.trim();
  const talkButton = () => page.querySelector('.talk') as HTMLButtonElement;

  async function settle(): Promise<void> {
    await fixture.whenStable();
  }

  function key(type: 'keydown' | 'keyup', init: KeyboardEventInit = {}): KeyboardEvent {
    const event = new KeyboardEvent(type, { code: 'Space', cancelable: true, ...init });
    window.dispatchEvent(event);
    return event;
  }

  beforeEach(async () => {
    socket = new FakeSocket();
    recorder = new FakeRecorder();
    player = new PlayingPlayer();
    await TestBed.configureTestingModule({
      imports: [Conversation],
      providers: [
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: Recorder, useValue: recorder },
        { provide: AudioPlayer, useValue: player },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(Conversation);
    page = fixture.nativeElement as HTMLElement;
    await settle();
  });

  it('starts idle with a hint on how to talk', () => {
    expect(orb().dataset['state']).toBe('idle');
    expect(hint()).toContain('Hold the button, or the space bar');
  });

  it('follows the conversation through listening, thinking and speaking', async () => {
    talkButton().dispatchEvent(new Event('pointerdown'));
    await settle();
    expect(orb().dataset['state']).toBe('listening');

    talkButton().dispatchEvent(new Event('pointerup'));
    await settle();
    expect(socket.sent).toEqual([recorder.result]);

    socket.emit({ type: 'status', state: 'thinking' });
    await settle();
    expect(orb().dataset['state']).toBe('thinking');

    socket.emit({ type: 'status', state: 'idle' });
    player.playing.set(true);
    await settle();
    expect(orb().dataset['state']).toBe('speaking');

    player.playing.set(false);
    await settle();
    expect(orb().dataset['state']).toBe('idle');
  });

  it('shows live captions for both sides', async () => {
    socket.emit({ type: 'user_transcript', text: 'I went running' });
    socket.emit({
      type: 'assistant_message',
      text: 'Look at you go!',
      mode: 'normal',
      teasing_allowed: true,
    });
    await settle();

    expect(page.querySelector('[data-testid="caption-you"]')?.textContent).toContain(
      'I went running',
    );
    expect(page.querySelector('[data-testid="caption-companion"]')?.textContent).toContain(
      'Look at you go!',
    );
  });

  it('holds the space bar to talk, but not while typing in a field', async () => {
    const down = key('keydown');
    await settle();
    expect(down.defaultPrevented).toBe(true);
    expect(recorder.recording()).toBe(true);

    key('keyup');
    await settle();
    expect(socket.sent).toHaveLength(1);

    const field = document.createElement('input');
    document.body.appendChild(field);
    field.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', bubbles: true }));
    await settle();
    expect(recorder.recording()).toBe(false);
    field.remove();
  });

  it('ignores held-key repeats', async () => {
    key('keydown');
    await settle();
    key('keyup');
    await settle();
    key('keydown', { repeat: true });
    await settle();

    expect(recorder.recording()).toBe(false);
  });

  it('offers a confirmation card for proposed actions', async () => {
    socket.emit({ type: 'pending_action', id: 'a1', kind: 'reminder', summary: 'call mom at 6' });
    await settle();

    const card = page.querySelector('[data-testid="pending-action"]') as HTMLElement;
    expect(card.textContent).toContain('New reminder');
    expect(card.textContent).toContain('call mom at 6');

    (card.querySelector('button[data-variant="primary"]') as HTMLButtonElement).click();
    expect(socket.sent).toEqual([{ type: 'resolve_action', id: 'a1', confirm: true }]);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();
    expect(page.querySelector('[data-testid="pending-action"]')).toBeNull();
  });

  it('tells the page when plans change so it can refresh them', async () => {
    let changes = 0;
    fixture.componentInstance.plansChanged.subscribe(() => (changes += 1));

    socket.emit({ type: 'pending_action', id: 'a1', kind: 'task', summary: 'stretch' });
    await settle();
    expect(changes).toBe(0);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();
    expect(changes).toBe(1);

    socket.emit({ type: 'pending_action', id: 'a2', kind: 'task', summary: 'nap' });
    socket.emit({ type: 'action_resolved', id: 'a2', status: 'cancelled' });
    await settle();
    expect(changes).toBe(1);

    socket.emit({ type: 'reminder_due', id: 'r1', title: 'water', text: 'Drink water.' });
    await settle();
    expect(changes).toBe(2);
  });

  it('shows a due reminder until it is dismissed', async () => {
    socket.emit({
      type: 'reminder_due',
      id: 'r1',
      title: 'stretch',
      text: 'Hey, reminder: stretch.',
    });
    await settle();
    const toast = page.querySelector('[data-testid="reminder"]') as HTMLElement;
    expect(toast.textContent).toContain('Hey, reminder: stretch.');

    (toast.querySelector('button') as HTMLButtonElement).click();
    await settle();
    expect(page.querySelector('[data-testid="reminder"]')).toBeNull();
  });

  it('explains a blocked microphone', async () => {
    recorder.blocked = true;

    talkButton().dispatchEvent(new Event('pointerdown'));
    await settle();

    expect(page.querySelector('[role="alert"]')?.textContent).toContain(MICROPHONE_BLOCKED);
  });

  it('goes offline and disables talking when the connection is lost', async () => {
    socket.fail();
    await settle();

    expect(orb().dataset['state']).toBe('offline');
    expect(talkButton().disabled).toBe(true);
    expect(hint()).toContain("Can't reach your companion");
  });
});
