import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  output,
  signal,
} from '@angular/core';
import { Orb, OrbState } from '../orb/orb';
import { CompanionSession } from '../session/companion-session';
import { ActionKind } from '../session/protocol';
import { PushToTalk } from '../session/push-to-talk';
import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { Panel } from '../ui/panel';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';

const HINTS: Record<OrbState, string> = {
  idle: 'Hold the button, or the space bar, and talk',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Talking. Hold to interrupt.',
  offline: "Can't reach your companion. Is the backend running?",
};

const KIND_LABELS: Record<ActionKind, string> = {
  task: 'New quest',
  reminder: 'New reminder',
  workout_plan: 'New training plan',
};

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

@Component({
  selector: 'app-conversation',
  imports: [Orb, Button, Icon, Panel],
  templateUrl: './conversation.html',
  styleUrl: './conversation.scss',
  providers: [CompanionSession, PushToTalk],
  host: {
    '(window:keydown)': 'onKeyDown($event)',
    '(window:keyup)': 'onKeyUp($event)',
  },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Conversation {
  protected readonly session = inject(CompanionSession);
  protected readonly talk = inject(PushToTalk);
  protected readonly player = inject(AudioPlayer);
  private readonly recorder = inject(Recorder);
  private readonly dismissedReminder = signal<number | null>(null);

  readonly plansChanged = output();

  protected readonly kindLabels = KIND_LABELS;

  protected readonly orbState = computed<OrbState>(() => {
    const state = this.session.state();
    if (state === 'closed') {
      return 'offline';
    }
    if (this.talk.recording()) {
      return 'listening';
    }
    if (this.player.playing() || state === 'speaking') {
      return 'speaking';
    }
    return state === 'thinking' ? 'thinking' : 'idle';
  });

  protected readonly hint = computed(() => HINTS[this.orbState()]);

  protected readonly reminder = computed(() => {
    const reminder = this.session.lastReminder();
    return reminder && reminder.id !== this.dismissedReminder() ? reminder : null;
  });

  protected readonly problem = computed(() => {
    const entries = this.session.entries();
    const last = entries.at(-1);
    return last?.from === 'system' ? last.text : null;
  });

  private readonly planEvents = computed(
    () =>
      this.session
        .entries()
        .filter(
          (entry) =>
            (entry.from === 'action' && entry.status === 'confirmed') || entry.from === 'reminder',
        ).length,
  );

  constructor() {
    let seen = 0;
    effect(() => {
      const count = this.planEvents();
      if (count > seen) {
        seen = count;
        this.plansChanged.emit();
      }
    });
  }

  protected readonly level = (): number =>
    this.talk.recording() ? this.recorder.level() : this.player.level();

  protected dismissReminder(id: number): void {
    this.dismissedReminder.set(id);
  }

  protected toggleMute(): void {
    this.player.muted.update((muted) => !muted);
    if (this.player.muted()) {
      this.player.stop();
    }
  }

  protected onKeyDown(event: KeyboardEvent): void {
    if (event.code !== 'Space' || event.repeat || isTyping(event.target)) {
      return;
    }
    event.preventDefault();
    void this.talk.start();
  }

  protected onKeyUp(event: KeyboardEvent): void {
    if (event.code !== 'Space' || isTyping(event.target)) {
      return;
    }
    event.preventDefault();
    void this.talk.stop();
  }
}
