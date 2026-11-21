import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DevChat } from './dev-chat';
import { SOCKET_FACTORY } from '../session/companion-session';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';
import { MICROPHONE_BLOCKED } from '../session/push-to-talk';
import { FakePlayer, FakeSocket } from '../session/testing/fakes';

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
    this.recording.set(false);
    return Promise.resolve(this.result);
  }
}

describe('DevChat', () => {
  let socket: FakeSocket;
  let fixture: ComponentFixture<DevChat>;
  let page: HTMLElement;
  let recorder: FakeRecorder;

  const input = () => page.querySelector('input') as HTMLInputElement;
  const sendButton = () => page.querySelector('button[type="submit"]') as HTMLButtonElement;

  async function type(text: string): Promise<void> {
    input().value = text;
    input().dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  beforeEach(async () => {
    socket = new FakeSocket();
    await TestBed.configureTestingModule({
      imports: [DevChat],
      providers: [
        provideRouter([]),
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: AudioPlayer, useValue: new FakePlayer() },
        { provide: Recorder, useFactory: () => (recorder = new FakeRecorder()) },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DevChat);
    page = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });

  it('starts empty, with sending disabled until something is typed', async () => {
    expect(page.textContent).toContain('Say something to your companion.');
    expect(sendButton().disabled).toBe(true);

    await type('hey');

    expect(sendButton().disabled).toBe(false);
  });

  it('sends the draft on submit and clears the input', async () => {
    await type('I skipped the gym again');

    sendButton().click();
    await fixture.whenStable();

    expect(socket.sent).toEqual([{ type: 'user_message', text: 'I skipped the gym again' }]);
    expect(input().value).toBe('');
    expect(page.querySelector('.entry.user')?.textContent).toContain('I skipped the gym again');
  });

  it('shows a thinking indicator, then the reply with its mode badges', async () => {
    socket.emit({ type: 'status', state: 'thinking' });
    await fixture.whenStable();
    expect(page.querySelector('.thinking')).not.toBeNull();

    socket.emit({
      type: 'assistant_message',
      text: "Okay, no teasing. What's one small step?",
      mode: 'supportive',
      teasing_allowed: false,
    });
    socket.emit({ type: 'status', state: 'idle' });
    await fixture.whenStable();

    expect(page.querySelector('.thinking')).toBeNull();
    const reply = page.querySelector('.entry.companion') as HTMLElement;
    expect(reply.textContent).toContain("What's one small step?");
    expect(reply.querySelector('.badge.supportive')?.textContent?.trim()).toBe('supportive');
    expect(reply.textContent).toContain('teasing off');
  });

  it('disables the input when the connection is lost', async () => {
    socket.fail();
    await fixture.whenStable();

    expect(input().disabled).toBe(true);
    expect(page.querySelector('[data-testid="state"]')?.textContent).toContain('closed');
  });

  it('lets the user save or cancel a proposed action from its card', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'reminder', summary: 'call mom at 6' }],
    });
    await fixture.whenStable();

    const card = page.querySelector('[data-testid="action-card"]') as HTMLElement;
    expect(card.textContent).toContain('Reminder');
    expect(card.textContent).toContain('call mom at 6');

    const [save] = Array.from(card.querySelectorAll('button'));
    save.click();
    expect(socket.sent).toEqual([{ type: 'resolve_action', id: 'a1', confirm: true }]);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    await fixture.whenStable();

    expect(card.querySelectorAll('button')).toHaveLength(0);
    expect(card.textContent).toContain('confirmed');
  });

  it('labels a finished quest with a tick-off button', async () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'complete_task', summary: 'buy milk' }],
    });
    await fixture.whenStable();

    const card = page.querySelector('[data-testid="action-card"]') as HTMLElement;
    expect(card.textContent).toContain('Quest done');
    expect(card.querySelector('button')?.textContent?.trim()).toBe('Tick off');
  });

  const talkButton = () => page.querySelector('.talk') as HTMLButtonElement;

  it('records while the talk button is held and sends the recording on release', async () => {
    talkButton().dispatchEvent(new Event('pointerdown'));
    await fixture.whenStable();
    expect(talkButton().textContent).toContain('Listening');

    talkButton().dispatchEvent(new Event('pointerup'));
    await fixture.whenStable();

    expect(socket.sent).toEqual([recorder.result]);
    expect(talkButton().textContent).toContain('Hold to talk');
  });

  it('explains a blocked microphone', async () => {
    recorder.blocked = true;

    talkButton().dispatchEvent(new Event('pointerdown'));
    await fixture.whenStable();

    expect(page.textContent).toContain(MICROPHONE_BLOCKED);
  });

  it('shows spoken messages in the conversation', async () => {
    socket.emit({ type: 'user_transcript', text: 'I did my reading' });
    await fixture.whenStable();

    expect(page.querySelector('.entry.user')?.textContent).toContain('I did my reading');
  });
});
