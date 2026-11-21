import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SOCKET_FACTORY } from '../session/companion-session';
import { HANDS_FREE_FAILED } from '../session/hands-free';
import { MICROPHONE_BLOCKED } from '../session/push-to-talk';
import { FakeDetector, FakePlayer, FakeSocket } from '../session/testing/fakes';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';
import { VOICE_DETECTOR } from '../voice/voice-detector';
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
  let detector: FakeDetector;
  let fixture: ComponentFixture<Conversation>;
  let page: HTMLElement;

  const orb = () => page.querySelector('app-orb') as HTMLElement;
  const hint = () => page.querySelector('[data-testid="hint"]')?.textContent?.trim();
  const talkButton = () => page.querySelector('.talk') as HTMLButtonElement;
  const handsFreeButton = () => page.querySelector('.hands-free') as HTMLButtonElement;

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
    detector = new FakeDetector();
    await TestBed.configureTestingModule({
      imports: [Conversation],
      providers: [
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: Recorder, useValue: recorder },
        { provide: AudioPlayer, useValue: player },
        { provide: VOICE_DETECTOR, useValue: detector.factory },
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
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'reminder', summary: 'call mom at 6' }],
    });
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

    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'task', summary: 'stretch' }],
    });
    await settle();
    expect(changes).toBe(0);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();
    expect(changes).toBe(1);

    socket.emit({ type: 'pending_action', id: 'a2', items: [{ kind: 'task', summary: 'nap' }] });
    socket.emit({ type: 'action_resolved', id: 'a2', status: 'cancelled' });
    await settle();
    expect(changes).toBe(1);

    socket.emit({ type: 'reminder_due', id: 'r1', title: 'water', text: 'Drink water.' });
    await settle();
    expect(changes).toBe(2);
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

  it('lists every item of a batch on one card', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [
        { kind: 'task', summary: 'a task: buy milk' },
        { kind: 'reminder', summary: 'a reminder to call mom, today at 6 PM' },
      ],
    });
    await settle();

    const card = page.querySelector('[data-testid="pending-action"]') as HTMLElement;
    expect(card.textContent).toContain('2 new things');
    expect(Array.from(card.querySelectorAll('li')).map((li) => li.textContent?.trim())).toEqual([
      'a task: buy milk',
      'a reminder to call mom, today at 6 PM',
    ]);
    expect(card.querySelector('button[data-variant="primary"]')?.textContent).toContain('Save all');
  });

  it('labels a finished quest as done and offers to tick it off', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'complete_task', summary: 'apply for jobs' }],
    });
    await settle();

    const card = page.querySelector('[data-testid="pending-action"]') as HTMLElement;
    expect(card.textContent).toContain('Quest done');
    expect(card.textContent).toContain('apply for jobs');
    const tick = card.querySelector('button[data-variant="primary"]') as HTMLButtonElement;
    expect(tick.textContent?.trim()).toBe('Tick off');
    tick.click();
    expect(socket.sent).toEqual([{ type: 'resolve_action', id: 'a1', confirm: true }]);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();
    const saved = page.querySelector('[data-testid="saved"]') as HTMLElement;
    expect(saved.textContent).toContain('Ticked off.');
  });

  it('ticks off several quests at once', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [
        { kind: 'complete_task', summary: 'buy milk' },
        { kind: 'complete_task', summary: 'stretch for today' },
      ],
    });
    await settle();

    const card = page.querySelector('[data-testid="pending-action"]') as HTMLElement;
    expect(card.textContent).toContain('2 quests done');
    expect(card.querySelector('button[data-variant="primary"]')?.textContent).toContain(
      'Tick off all',
    );
  });

  it('offers to undo what was just saved', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'task', summary: 'a task: buy milk' }],
    });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await settle();

    const saved = page.querySelector('[data-testid="saved"]') as HTMLElement;
    expect(saved.textContent).toContain('Saved');
    const undo = Array.from(saved.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Undo'),
    ) as HTMLButtonElement;
    undo.click();
    expect(socket.sent).toEqual([{ type: 'undo_action', id: 'a1' }]);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'undone' });
    await settle();
    expect(page.querySelector('[data-testid="saved"]')).toBeNull();
  });

  describe('hands-free', () => {
    async function turnOn(): Promise<void> {
      handsFreeButton().click();
      await settle();
    }

    it('listens without holding anything and sends what was said after a pause', async () => {
      await turnOn();

      expect(handsFreeButton().getAttribute('aria-pressed')).toBe('true');
      expect(detector.listening).toBe(true);
      expect(hint()).toContain('Hands-free is on');
      expect(talkButton().textContent).toContain('End hands-free');

      detector.events?.speechStarted();
      await settle();
      expect(orb().dataset['state']).toBe('listening');

      const speech = new Blob(['hello']);
      detector.events?.speechEnded(speech);
      await settle();
      expect(socket.sent).toEqual([speech]);
      expect(detector.listening).toBe(false);
    });

    it('stops listening while the companion thinks and talks, then listens again', async () => {
      await turnOn();

      socket.emit({ type: 'status', state: 'thinking' });
      await settle();
      expect(detector.listening).toBe(false);

      socket.emit({ type: 'status', state: 'idle' });
      player.playing.set(true);
      await settle();
      expect(detector.listening).toBe(false);

      player.playing.set(false);
      await settle();
      expect(detector.listening).toBe(true);
    });

    it('turns off with the end button and leaves the space bar alone while on', async () => {
      await turnOn();
      key('keydown');
      await settle();
      expect(recorder.recording()).toBe(false);

      talkButton().click();
      await settle();

      expect(detector.listening).toBe(false);
      expect(talkButton().textContent).toContain('Hold to talk');
    });

    it('explains when it cannot start', async () => {
      detector.blocked = true;

      await turnOn();

      expect(page.querySelector('[role="alert"]')?.textContent).toContain(HANDS_FREE_FAILED);
      expect(handsFreeButton().getAttribute('aria-pressed')).toBe('false');
    });

    it('switches off when the connection is lost', async () => {
      await turnOn();

      socket.fail();
      await settle();

      expect(detector.listening).toBe(false);
      expect(handsFreeButton().getAttribute('aria-pressed')).toBe('false');
    });
  });
});
