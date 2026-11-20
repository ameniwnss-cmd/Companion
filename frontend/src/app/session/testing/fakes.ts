import { signal } from '@angular/core';
import { Observer, Subject, Subscription } from 'rxjs';
import { WebSocketSubject } from 'rxjs/webSocket';
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
}
