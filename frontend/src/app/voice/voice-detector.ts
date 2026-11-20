import { InjectionToken } from '@angular/core';

export interface VoiceDetector {
  start(): Promise<void>;
  pause(): Promise<void>;
  destroy(): Promise<void>;
}

export interface VoiceDetectorEvents {
  speechStarted(): void;
  speechEnded(recording: Blob): void;
  falseStart(): void;
  level(probability: number): void;
}

export type VoiceDetectorFactory = (events: VoiceDetectorEvents) => Promise<VoiceDetector>;

const SILENCE_BEFORE_REPLY_MS = 800;
const SHORTEST_SPEECH_MS = 300;
const PCM = 1;
const SAMPLE_RATE = 16_000;
const MONO = 1;
const BITS = 16;

export async function createSileroDetector(events: VoiceDetectorEvents): Promise<VoiceDetector> {
  const { MicVAD, utils } = await import('@ricky0123/vad-web');
  const assets = new URL('vad/', document.baseURI).href;
  const vad = await MicVAD.new({
    model: 'v5',
    baseAssetPath: assets,
    onnxWASMBasePath: assets,
    startOnLoad: false,
    redemptionMs: SILENCE_BEFORE_REPLY_MS,
    minSpeechMs: SHORTEST_SPEECH_MS,
    onSpeechStart: () => events.speechStarted(),
    onVADMisfire: () => events.falseStart(),
    onSpeechEnd: (audio) => {
      const wav = utils.encodeWAV(audio, PCM, SAMPLE_RATE, MONO, BITS);
      events.speechEnded(new Blob([wav], { type: 'audio/wav' }));
    },
    onFrameProcessed: (probabilities) => events.level(probabilities.isSpeech),
  });
  return {
    start: () => vad.start(),
    pause: () => vad.pause(),
    destroy: () => vad.destroy(),
  };
}

export const VOICE_DETECTOR = new InjectionToken<VoiceDetectorFactory>('VOICE_DETECTOR', {
  providedIn: 'root',
  factory: () => createSileroDetector,
});
