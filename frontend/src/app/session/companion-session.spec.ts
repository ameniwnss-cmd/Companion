import { TestBed } from '@angular/core/testing';
import { CompanionSession, SOCKET_FACTORY, sessionUrl } from './companion-session';
import { AudioPlayer } from '../voice/audio-player';
import { FakePlayer, FakeSocket } from './testing/fakes';

describe('CompanionSession', () => {
  let socket: FakeSocket;
  let chat: CompanionSession;
  let player: FakePlayer;

  beforeEach(() => {
    socket = new FakeSocket();
    player = new FakePlayer();
    TestBed.configureTestingModule({
      providers: [
        CompanionSession,
        { provide: SOCKET_FACTORY, useValue: socket.factory },
        { provide: AudioPlayer, useValue: player },
      ],
    });
    chat = TestBed.inject(CompanionSession);
  });

  it('connects to the configured dev channel', () => {
    expect(socket.urls).toHaveLength(1);
    expect(chat.state()).toBe('connecting');
    expect(chat.canSend()).toBe(true);
  });

  it('sends trimmed messages and shows them in the log', () => {
    chat.send('  I went to the gym!  ');

    expect(socket.sent).toEqual([{ type: 'user_message', text: 'I went to the gym!' }]);
    expect(chat.entries()).toEqual([
      { id: 0, from: 'user', text: 'I went to the gym!', spoken: false },
    ]);
  });

  it('ignores blank messages', () => {
    chat.send('   ');

    expect(socket.sent).toEqual([]);
    expect(chat.entries()).toEqual([]);
  });

  it('blocks sending while the companion is thinking', () => {
    socket.emit({ type: 'status', state: 'thinking' });
    chat.send('hello?');

    expect(chat.canSend()).toBe(false);
    expect(socket.sent).toEqual([]);
  });

  it('adds companion replies with their safety mode', () => {
    socket.emit({
      type: 'assistant_message',
      text: 'Breathe with me.',
      mode: 'crisis',
      teasing_allowed: false,
    });
    socket.emit({ type: 'status', state: 'idle' });

    expect(chat.entries()).toEqual([
      { id: 0, from: 'companion', text: 'Breathe with me.', mode: 'crisis', teasingAllowed: false },
    ]);
    expect(chat.state()).toBe('idle');
  });

  it('shows server errors in the log', () => {
    socket.emit({ type: 'error', detail: 'The companion is unavailable right now' });

    expect(chat.entries()).toEqual([
      { id: 0, from: 'system', text: 'The companion is unavailable right now' },
    ]);
  });

  it('explains how to fix a lost connection and stops sending', () => {
    socket.fail();
    chat.send('anyone there?');

    expect(chat.state()).toBe('closed');
    expect(chat.canSend()).toBe(false);
    expect(chat.entries()[0]).toMatchObject({
      from: 'system',
      text: expect.stringContaining('Is the backend running?'),
    });
    expect(socket.sent).toEqual([]);
  });

  it('shows a proposed action as a pending card, then updates it when resolved', () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'reminder', summary: 'call mom at 6' }],
    });

    expect(chat.entries()).toEqual([
      {
        id: 0,
        from: 'action',
        actionId: 'a1',
        items: [{ kind: 'reminder', summary: 'call mom at 6' }],
        status: 'pending',
      },
    ]);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });

    expect(chat.entries()[0]).toMatchObject({ actionId: 'a1', status: 'confirmed' });
  });

  it('only updates the card that was resolved', () => {
    socket.emit({ type: 'pending_action', id: 'a1', items: [{ kind: 'task', summary: 'first' }] });
    socket.emit({ type: 'pending_action', id: 'a2', items: [{ kind: 'task', summary: 'second' }] });

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'cancelled' });

    expect(chat.entries().map((e) => (e.from === 'action' ? e.status : null))).toEqual([
      'cancelled',
      'pending',
    ]);
  });

  it('sends a resolve event when a card button is used', () => {
    chat.resolve('a1', false);

    expect(socket.sent).toEqual([{ type: 'resolve_action', id: 'a1', confirm: false }]);
  });

  it('sends an undo event for a saved action', () => {
    chat.undo('a1');

    expect(socket.sent).toEqual([{ type: 'undo_action', id: 'a1' }]);
  });

  it('remembers the last saved action until it is undone', () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'task', summary: 'buy milk' }],
    });
    expect(chat.lastSaved()).toBeNull();

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    expect(chat.lastSaved()).toMatchObject({ actionId: 'a1' });

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'undone' });
    expect(chat.lastSaved()).toBeNull();
  });

  it('counts every change to the saved plans', () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'task', summary: 'buy milk' }],
    });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'cancelled' });
    expect(chat.plansVersion()).toBe(0);

    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'undone' });
    socket.emit({ type: 'reminder_due', id: 'r1', title: 'water', text: 'Drink water.' });

    expect(chat.plansVersion()).toBe(3);
  });

  it('refreshes the plans when a quest is ticked off or unticked', () => {
    socket.emit({
      type: 'pending_action',
      id: 'a1',
      items: [{ kind: 'complete_task', summary: 'buy milk' }],
    });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'confirmed' });
    socket.emit({ type: 'action_resolved', id: 'a1', status: 'undone' });

    expect(chat.plansVersion()).toBe(2);
  });

  it('does not resolve while the companion is thinking', () => {
    socket.emit({ type: 'status', state: 'thinking' });

    chat.resolve('a1', true);

    expect(socket.sent).toEqual([]);
  });

  it('shows due reminders', () => {
    socket.emit({
      type: 'reminder_due',
      id: 'r1',
      title: 'call mom',
      text: 'Hey, reminder: call mom.',
    });

    expect(chat.entries()).toEqual([{ id: 0, from: 'reminder', text: 'Hey, reminder: call mom.' }]);
  });

  it('tells the backend the user time zone', () => {
    expect(socket.urls[0]).toMatch(/\?tz=.+&speak=true$/);
    expect(sessionUrl('ws://x/dev/ws', 'America/New_York')).toBe(
      'ws://x/dev/ws?tz=America%2FNew_York&speak=true',
    );
  });

  it('captions what the user said out loud', () => {
    socket.emit({ type: 'user_transcript', text: 'remind me to stretch' });

    expect(chat.entries()).toEqual([
      { id: 0, from: 'user', text: 'remind me to stretch', spoken: true },
    ]);
  });

  it('plays the companion voice as it arrives', () => {
    const first = new ArrayBuffer(4);
    const second = new ArrayBuffer(8);

    socket.emit({ type: 'audio', data: first });
    socket.emit({ type: 'audio', data: second });

    expect(player.played).toEqual([first, second]);
  });

  it('sends a recording and interrupts the companion', () => {
    const recording = new Blob(['audio']);

    chat.sendRecording(recording);

    expect(socket.sent).toEqual([recording]);
    expect(player.stops).toBe(1);
  });

  it('does not send recordings while the companion is speaking', () => {
    socket.emit({ type: 'status', state: 'speaking' });

    chat.sendRecording(new Blob(['audio']));

    expect(socket.sent).toEqual([]);
  });
});
