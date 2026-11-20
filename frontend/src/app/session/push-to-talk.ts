import { Injectable, inject } from '@angular/core';
import { AudioPlayer } from '../voice/audio-player';
import { Recorder } from '../voice/recorder';
import { CompanionSession } from './companion-session';

export const MICROPHONE_BLOCKED =
  'Microphone access was blocked. Allow it in the browser to talk to your companion.';

@Injectable()
export class PushToTalk {
  private readonly session = inject(CompanionSession);
  private readonly recorder = inject(Recorder);
  private readonly player = inject(AudioPlayer);

  readonly recording = this.recorder.recording;

  async start(): Promise<void> {
    if (!this.session.canSend() || this.recorder.recording()) {
      return;
    }
    this.player.stop();
    try {
      await this.recorder.start();
    } catch {
      this.session.reportProblem(MICROPHONE_BLOCKED);
    }
  }

  async stop(): Promise<void> {
    const recording = await this.recorder.stop();
    if (recording) {
      this.session.sendRecording(recording);
    }
  }
}
