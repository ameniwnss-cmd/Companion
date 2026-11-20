import { Injectable, inject, signal } from '@angular/core';
import { AUDIO_CONTEXT, loudness } from './audio-context';

const CHIME_NOTES = [880, 1318.5];
const NOTE_GAP = 0.18;
const NOTE_LENGTH = 0.5;
const CHIME_LENGTH = 0.9;
const CHIME_VOLUME = 0.25;
const SILENT = 0.0001;

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

  chime(): Promise<void> {
    this.queue = this.queue.then(() => this.scheduleChime()).catch(() => undefined);
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

  private scheduleChime(): void {
    const { context } = this.ensureContext();
    const startAt = Math.max(context.currentTime, this.queueEnd);
    CHIME_NOTES.forEach((frequency, index) => {
      const at = startAt + index * NOTE_GAP;
      const tone = context.createOscillator();
      const volume = context.createGain();
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(SILENT, at);
      volume.gain.exponentialRampToValueAtTime(CHIME_VOLUME, at + 0.02);
      volume.gain.exponentialRampToValueAtTime(SILENT, at + NOTE_LENGTH);
      tone.connect(volume).connect(context.destination);
      tone.start(at);
      tone.stop(at + NOTE_LENGTH);
    });
    this.queueEnd = startAt + CHIME_LENGTH;
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
