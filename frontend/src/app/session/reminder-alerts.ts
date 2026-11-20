import { DOCUMENT } from '@angular/common';
import { Injectable, InjectionToken, computed, effect, inject, signal } from '@angular/core';
import { AudioPlayer } from '../voice/audio-player';
import { CompanionSession } from './companion-session';

export type AlertPermission = NotificationPermission | 'unsupported';

export interface Notifier {
  permission(): AlertPermission;
  request(): Promise<AlertPermission>;
  show(title: string, body: string): void;
}

const browserNotifier: Notifier = {
  permission: () => (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission),
  request: () => Notification.requestPermission(),
  show: (title, body) => {
    new Notification(title, { body, icon: 'favicon.ico', tag: 'companion-reminder' });
  },
};

export const NOTIFIER = new InjectionToken<Notifier>('NOTIFIER', {
  providedIn: 'root',
  factory: () => browserNotifier,
});

@Injectable({ providedIn: 'root' })
export class ReminderAlerts {
  private readonly session = inject(CompanionSession);
  private readonly player = inject(AudioPlayer);
  private readonly notifier = inject(NOTIFIER);
  private readonly document = inject(DOCUMENT);
  private readonly dismissed = signal<number | null>(null);

  readonly permission = signal(this.notifier.permission());

  readonly current = computed(() => {
    const reminder = this.session.lastReminder();
    return reminder && reminder.id !== this.dismissed() ? reminder : null;
  });

  constructor() {
    let announced: number | null = null;
    effect(() => {
      const reminder = this.session.lastReminder();
      if (!reminder || reminder.id === announced) {
        return;
      }
      announced = reminder.id;
      void this.player.chime();
      if (this.permission() === 'granted' && !this.document.hasFocus()) {
        this.notifier.show('Companion', reminder.text);
      }
    });
  }

  dismiss(id: number): void {
    this.dismissed.set(id);
  }

  async enable(): Promise<void> {
    this.permission.set(await this.notifier.request());
  }
}
