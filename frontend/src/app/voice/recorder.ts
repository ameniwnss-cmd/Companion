import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { AUDIO_CONTEXT, loudness } from './audio-context';

export interface MediaApi {
  getUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream>;
  createRecorder(stream: MediaStream, mimeType: string | undefined): MediaRecorder;
  supportedMimeType(): string | undefined;
}

const PREFERRED_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm'];

export const MEDIA = new InjectionToken<MediaApi>('MEDIA', {
  providedIn: 'root',
  factory: () => ({
    getUserMedia: (constraints) => navigator.mediaDevices.getUserMedia(constraints),
    createRecorder: (stream, mimeType) => new MediaRecorder(stream, mimeType ? { mimeType } : {}),
    supportedMimeType: () => PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)),
  }),
});

export const MIN_RECORDING_BYTES = 1_000;

@Injectable({ providedIn: 'root' })
export class Recorder {
  private readonly media = inject(MEDIA);
  private readonly createContext = inject(AUDIO_CONTEXT);
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];

  readonly recording = signal(false);

  async start(): Promise<void> {
    if (this.recorder) {
      return;
    }
    this.stream = await this.media.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.chunks = [];
    this.recorder = this.media.createRecorder(this.stream, this.media.supportedMimeType());
    this.recorder.ondataavailable = (event) => this.chunks.push(event.data);
    this.recorder.start();
    this.listen(this.stream);
    this.recording.set(true);
  }

  level(): number {
    return this.analyser && this.recording() ? loudness(this.analyser) : 0;
  }

  stop(): Promise<Blob | null> {
    const recorder = this.recorder;
    if (!recorder) {
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      recorder.onstop = () => {
        this.source?.disconnect();
        this.source = null;
        this.stream?.getTracks().forEach((track) => track.stop());
        this.recorder = null;
        this.stream = null;
        this.recording.set(false);
        const recording = new Blob(this.chunks, { type: recorder.mimeType });
        resolve(recording.size >= MIN_RECORDING_BYTES ? recording : null);
      };
      recorder.stop();
    });
  }

  private listen(stream: MediaStream): void {
    this.context ??= this.createContext();
    if (!this.analyser) {
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 512;
    }
    this.source = this.context.createMediaStreamSource(stream);
    this.source.connect(this.analyser);
  }
}
