import { Injectable, inject, signal } from '@angular/core';
import { AUDIO_CONTEXT, loudness } from './audio-context';

@Injectable({ providedIn: 'root' })
export class AudioPlayer {
  private readonly createContext = inject(AUDIO_CONTEXT);
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private queueEnd = 0;
  private queue: Promise<void> = Promise.resolve();

  readonly playing = signal(false);
  readonly muted = signal(false);

  play(audio: ArrayBuffer): Promise<void> {
    this.queue = this.queue.then(() => this.schedule(audio)).catch(() => undefined);
    return this.queue;
  }

  stop(): void {
    for (const source of this.sources) {
      source.stop();
    }
    this.sources.clear();
    this.queueEnd = 0;
    this.playing.set(false);
  }

  level(): number {
    return this.analyser && this.playing() ? loudness(this.analyser) : 0;
  }

  private async schedule(audio: ArrayBuffer): Promise<void> {
    if (this.muted()) {
      return;
    }
    const { context, analyser } = this.ensureContext();
    const buffer = await context.decodeAudioData(audio);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    const startAt = Math.max(context.currentTime, this.queueEnd);
    source.start(startAt);
    this.queueEnd = startAt + buffer.duration;
    this.sources.add(source);
    this.playing.set(true);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) {
        this.playing.set(false);
      }
    };
  }

  private ensureContext(): { context: AudioContext; analyser: AnalyserNode } {
    if (!this.context || !this.analyser) {
      this.context = this.createContext();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.connect(this.context.destination);
    }
    if (this.context.state === 'suspended') {
      void this.context.resume();
    }
    return { context: this.context, analyser: this.analyser };
  }
}
