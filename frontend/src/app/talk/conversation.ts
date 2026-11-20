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
import { HandsFree } from '../session/hands-free';
import { ActionKind, PendingItem } from '../session/protocol';
import { PushToTalk } from '../session/push-to-talk';
import { Button } from '../ui/button';
import { Icon, IconName } from '../ui/icon';
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
const HANDS_FREE_HINTS: Partial<Record<OrbState, string>> = {
  idle: "Hands-free is on. Just talk, and pause when you're done.",
  speaking: "Talking. I'll listen again when I'm done.",
};

const KIND_LABELS: Record<ActionKind, string> = {
  task: 'New quest',
  reminder: 'New reminder',
  weekly_plan: 'New weekly plan',
};

const KIND_ICONS: Record<ActionKind, IconName> = {
  task: 'quests',
  reminder: 'bell',
  weekly_plan: 'calendar',
};

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

@Component({
  selector: 'app-conversation',
  imports: [Orb, Button, Icon, Panel],
  templateUrl: './conversation.html',
  styleUrl: './conversation.scss',
  providers: [PushToTalk, HandsFree],
  host: {
    '(window:keydown)': 'onKeyDown($event)',
    '(window:keyup)': 'onKeyUp($event)',
  },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Conversation {
  protected readonly session = inject(CompanionSession);
  protected readonly talk = inject(PushToTalk);
  protected readonly handsFree = inject(HandsFree);
  protected readonly player = inject(AudioPlayer);
  private readonly recorder = inject(Recorder);
  private readonly dismissedSaved = signal<number | null>(null);

  readonly plansChanged = output();

  protected readonly kindIcons = KIND_ICONS;

  protected readonly orbState = computed<OrbState>(() => {
    const state = this.session.state();
    if (state === 'closed') {
      return 'offline';
    }
    if (this.talk.recording() || this.handsFree.hearing()) {
      return 'listening';
    }
    if (this.player.playing() || state === 'speaking') {
      return 'speaking';
    }
    return state === 'thinking' ? 'thinking' : 'idle';
  });

  protected readonly hint = computed(() => {
    const state = this.orbState();
    return (this.handsFree.on() && HANDS_FREE_HINTS[state]) || HINTS[state];
  });

  protected readonly saved = computed(() => {
    const saved = this.session.lastSaved();
    return saved && saved.id !== this.dismissedSaved() ? saved : null;
  });

  protected readonly problem = computed(() => {
    const entries = this.session.entries();
    const last = entries.at(-1);
    return last?.from === 'system' ? last.text : null;
  });

  constructor() {
    let seen = 0;
    effect(() => {
      const version = this.session.plansVersion();
      if (version > seen) {
        seen = version;
        this.plansChanged.emit();
      }
    });
  }

  protected readonly level = (): number => {
    if (this.handsFree.hearing()) {
      return this.handsFree.level();
    }
    return this.talk.recording() ? this.recorder.level() : this.player.level();
  };

  protected cardTitle(items: readonly PendingItem[]): string {
    return items.length === 1 ? KIND_LABELS[items[0].kind] : `${items.length} new things`;
  }

  protected savedLabel(items: readonly PendingItem[]): string {
    return items.length === 1 ? 'Saved' : `Saved all ${items.length}`;
  }

  protected dismissSaved(id: number): void {
    this.dismissedSaved.set(id);
  }

  protected toggleMute(): void {
    this.player.muted.update((muted) => !muted);
    if (this.player.muted()) {
      this.player.stop();
    }
  }

  protected onKeyDown(event: KeyboardEvent): void {
    if (!this.pushToTalkKey(event) || event.repeat) {
      return;
    }
    event.preventDefault();
    void this.talk.start();
  }

  protected onKeyUp(event: KeyboardEvent): void {
    if (!this.pushToTalkKey(event)) {
      return;
    }
    event.preventDefault();
    void this.talk.stop();
  }

  private pushToTalkKey(event: KeyboardEvent): boolean {
    return event.code === 'Space' && !isTyping(event.target) && !this.handsFree.on();
  }
}
