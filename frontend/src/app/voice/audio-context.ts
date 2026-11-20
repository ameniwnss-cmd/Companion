import { InjectionToken } from '@angular/core';

export type AudioContextFactory = () => AudioContext;

export const AUDIO_CONTEXT = new InjectionToken<AudioContextFactory>('AUDIO_CONTEXT', {
  providedIn: 'root',
  factory: () => () => new AudioContext(),
});

export function loudness(analyser: AnalyserNode): number {
  const samples = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(samples);
  let sum = 0;
  for (const sample of samples) {
    const centred = (sample - 128) / 128;
    sum += centred * centred;
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * 3);
}
