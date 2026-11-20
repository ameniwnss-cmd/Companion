import { DestroyRef, Injectable, computed, effect, inject, signal } from '@angular/core';
import { AudioPlayer } from '../voice/audio-player';
import { VOICE_DETECTOR, VoiceDetector } from '../voice/voice-detector';
import { CompanionSession } from './companion-session';

export const HANDS_FREE_FAILED =
  "Hands-free mode couldn't start. Check that the microphone is allowed, then try again.";

@Injectable()
export class HandsFree {
  private readonly session = inject(CompanionSession);
  private readonly player = inject(AudioPlayer);
  private readonly createDetector = inject(VOICE_DETECTOR);
  private detector: VoiceDetector | null = null;
  private loudness = 0;

  readonly on = signal(false);
  readonly starting = signal(false);
  readonly hearing = signal(false);

  private readonly companionBusy = computed(() => {
    const state = this.session.state();
    return state === 'thinking' || state === 'speaking' || this.player.playing();
  });

  constructor() {
    effect(() => {
      const listen = this.on() && !this.companionBusy();
      const detector = this.detector;
      if (detector) {
        void (listen ? detector.start() : detector.pause());
      }
    });
    effect(() => {
      if (this.session.state() === 'closed') {
        void this.stop();
      }
    });
    inject(DestroyRef).onDestroy(() => void this.detector?.destroy());
  }

  readonly level = (): number => (this.hearing() ? this.loudness : 0);

  async toggle(): Promise<void> {
    await (this.on() ? this.stop() : this.start());
  }

  async start(): Promise<void> {
    if (this.on() || this.starting()) {
      return;
    }
    this.starting.set(true);
    try {
      this.detector ??= await this.createDetector({
        speechStarted: () => this.hearing.set(true),
        speechEnded: (recording) => this.send(recording),
        falseStart: () => this.hearing.set(false),
        level: (probability) => (this.loudness = probability),
      });
      this.on.set(true);
    } catch {
      this.session.reportProblem(HANDS_FREE_FAILED);
    } finally {
      this.starting.set(false);
    }
  }

  async stop(): Promise<void> {
    this.on.set(false);
    this.hearing.set(false);
    await this.detector?.pause();
  }

  private send(recording: Blob): void {
    this.hearing.set(false);
    if (!this.on() || !this.session.canSend()) {
      return;
    }
    void this.detector?.pause();
    this.session.sendRecording(recording);
  }
}
