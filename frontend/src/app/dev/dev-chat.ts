import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CompanionSession } from '../session/companion-session';
import { ActionKind } from '../session/protocol';
import { PushToTalk } from '../session/push-to-talk';
import { AudioPlayer } from '../voice/audio-player';

@Component({
  selector: 'app-dev-chat',
  imports: [RouterLink],
  templateUrl: './dev-chat.html',
  styleUrl: './dev-chat.scss',
  providers: [PushToTalk],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DevChat {
  protected readonly chat = inject(CompanionSession);
  protected readonly talk = inject(PushToTalk);
  protected readonly player = inject(AudioPlayer);
  protected readonly draft = signal('');
  protected readonly kindLabels: Record<ActionKind, string> = {
    task: 'Task',
    reminder: 'Reminder',
    weekly_plan: 'Weekly plan',
  };

  protected send(): void {
    this.chat.send(this.draft());
    this.draft.set('');
  }

  protected toggleMute(): void {
    this.player.muted.update((muted) => !muted);
    if (this.player.muted()) {
      this.player.stop();
    }
  }
}
