import { signal } from '@angular/core';
import { Observer, Subject, Subscription } from 'rxjs';
import { WebSocketSubject } from 'rxjs/webSocket';
import {
  VoiceDetector,
  VoiceDetectorEvents,
  VoiceDetectorFactory,
} from '../../voice/voice-detector';
import { SocketFactory } from '../companion-session';
import { Incoming, Outgoing } from '../protocol';

export class FakeSocket {
  readonly sent: Outgoing[] = [];
  readonly urls: string[] = [];
  private readonly incoming = new Subject<Incoming>();

  readonly factory: SocketFactory = (url) => {
    this.urls.push(url);
    // The fake implements only subscribe() and next(), the two methods the service uses.
    return this as unknown as WebSocketSubject<Incoming | Outgoing>;
  };

  subscribe(observer: Partial<Observer<Incoming>>): Subscription {
    return this.incoming.subscribe(observer);
  }

  next(event: Outgoing): void {
    this.sent.push(event);
  }

  emit(event: Incoming): void {
    this.incoming.next(event);
  }

  fail(): void {
    this.incoming.error(new Error('connection refused'));
  }
}

export class FakePlayer {
  readonly played: ArrayBuffer[] = [];
  stops = 0;
  readonly muted = signal(false);

  play(audio: ArrayBuffer): Promise<void> {
    this.played.push(audio);
    return Promise.resolve();
  }

  stop(): void {
    this.stops += 1;
  }

  chimes = 0;

  chime(): Promise<void> {
    this.chimes += 1;
    return Promise.resolve();
  }
}

export class FakeDetector implements VoiceDetector {
  events: VoiceDetectorEvents | null = null;
  listening = false;
  starts = 0;
  blocked = false;

  readonly factory: VoiceDetectorFactory = (events) => {
    if (this.blocked) {
      return Promise.reject(new Error('denied'));
    }
    this.events = events;
    return Promise.resolve(this);
  };

  start(): Promise<void> {
    this.listening = true;
    this.starts += 1;
    return Promise.resolve();
  }

  pause(): Promise<void> {
    this.listening = false;
    return Promise.resolve();
  }

  destroy(): Promise<void> {
    this.listening = false;
    return Promise.resolve();
  }
}
