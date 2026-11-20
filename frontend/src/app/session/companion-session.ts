import { DestroyRef, Injectable, InjectionToken, computed, inject, signal } from '@angular/core';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { environment } from '../../environments/environment';
import { AudioPlayer } from '../voice/audio-player';
import {
  ActionKind,
  ActionStatus,
  Incoming,
  Mode,
  Outgoing,
  ServerEvent,
  StatusEvent,
} from './protocol';

export type ChatEntry =
  | { id: number; from: 'user'; text: string; spoken: boolean }
  | { id: number; from: 'companion'; text: string; mode: Mode; teasingAllowed: boolean }
  | {
      id: number;
      from: 'action';
      actionId: string;
      kind: ActionKind;
      summary: string;
      status: ActionStatus;
    }
  | { id: number; from: 'reminder'; text: string }
  | { id: number; from: 'system'; text: string };

type NewEntry = ChatEntry extends infer E ? (E extends ChatEntry ? Omit<E, 'id'> : never) : never;

export type ConnectionState = 'connecting' | 'closed' | StatusEvent['state'];

export type SocketFactory = (url: string) => WebSocketSubject<Incoming | Outgoing>;

export const SOCKET_FACTORY = new InjectionToken<SocketFactory>('SOCKET_FACTORY', {
  providedIn: 'root',
  factory: () => (url) =>
    webSocket<Incoming | Outgoing>({
      url,
      binaryType: 'arraybuffer',
      serializer: (value) => (value instanceof Blob ? value : JSON.stringify(value)),
      deserializer: (event: MessageEvent<string | ArrayBuffer>) =>
        typeof event.data === 'string'
          ? (JSON.parse(event.data) as ServerEvent)
          : { type: 'audio', data: event.data },
    }),
});

export const COMPANION_URL = new InjectionToken<string>('COMPANION_URL', {
  providedIn: 'root',
  factory: () => environment.companionUrl,
});

export function sessionUrl(base: string, timeZone: string): string {
  return `${base}?tz=${encodeURIComponent(timeZone)}&speak=true`;
}

@Injectable()
export class CompanionSession {
  private readonly socket = inject(SOCKET_FACTORY)(
    sessionUrl(inject(COMPANION_URL), Intl.DateTimeFormat().resolvedOptions().timeZone),
  );
  private readonly player = inject(AudioPlayer);
  private nextId = 0;

  private readonly _entries = signal<readonly ChatEntry[]>([]);
  private readonly _state = signal<ConnectionState>('connecting');

  readonly entries = this._entries.asReadonly();
  readonly state = this._state.asReadonly();
  readonly canSend = computed(() => this._state() === 'idle' || this._state() === 'connecting');
  readonly lastHeard = computed(() => this.latest('user'));
  readonly lastSaid = computed(() => this.latest('companion'));
  readonly pendingAction = computed(() => {
    const action = this.latest('action');
    return action?.status === 'pending' ? action : null;
  });
  readonly lastReminder = computed(() => this.latest('reminder'));
  readonly lastProblem = computed(() => this.latest('system'));

  constructor() {
    const subscription = this.socket.subscribe({
      next: (event) => this.handle(event as Incoming),
      error: () => this.close('Connection lost. Is the backend running?'),
      complete: () => this.close('Connection closed.'),
    });
    inject(DestroyRef).onDestroy(() => {
      subscription.unsubscribe();
      this.player.stop();
    });
  }

  send(text: string): void {
    const trimmed = text.trim();
    if (!trimmed || !this.canSend()) {
      return;
    }
    this.player.stop();
    this.add({ from: 'user', text: trimmed, spoken: false });
    this.socket.next({ type: 'user_message', text: trimmed });
  }

  sendRecording(recording: Blob): void {
    if (!this.canSend()) {
      return;
    }
    this.player.stop();
    this.socket.next(recording);
  }

  resolve(actionId: string, confirm: boolean): void {
    if (!this.canSend()) {
      return;
    }
    this.socket.next({ type: 'resolve_action', id: actionId, confirm });
  }

  reportProblem(text: string): void {
    this.add({ from: 'system', text });
  }

  private handle(event: Incoming): void {
    switch (event.type) {
      case 'audio':
        void this.player.play(event.data);
        break;
      case 'status':
        this._state.set(event.state);
        break;
      case 'user_transcript':
        this.add({ from: 'user', text: event.text, spoken: true });
        break;
      case 'assistant_message':
        this.add({
          from: 'companion',
          text: event.text,
          mode: event.mode,
          teasingAllowed: event.teasing_allowed,
        });
        break;
      case 'pending_action':
        this.add({
          from: 'action',
          actionId: event.id,
          kind: event.kind,
          summary: event.summary,
          status: 'pending',
        });
        break;
      case 'action_resolved':
        this._entries.update((entries) =>
          entries.map((entry) =>
            entry.from === 'action' && entry.actionId === event.id
              ? { ...entry, status: event.status }
              : entry,
          ),
        );
        break;
      case 'reminder_due':
        this.add({ from: 'reminder', text: event.text });
        break;
      case 'error':
        this.add({ from: 'system', text: event.detail });
        break;
    }
  }

  private latest<K extends ChatEntry['from']>(from: K): Extract<ChatEntry, { from: K }> | null {
    const entries = this._entries();
    for (let i = entries.length - 1; i >= 0; i--) {
      const entry = entries[i];
      if (entry.from === from) {
        return entry as Extract<ChatEntry, { from: K }>;
      }
    }
    return null;
  }

  private close(reason: string): void {
    this._state.set('closed');
    this.add({ from: 'system', text: reason });
  }

  private add(entry: NewEntry): void {
    const withId: ChatEntry = { ...entry, id: this.nextId++ };
    this._entries.update((entries) => [...entries, withId]);
  }
}
