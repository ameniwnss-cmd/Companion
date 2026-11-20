import { TestBed } from '@angular/core/testing';
import { AUDIO_CONTEXT } from './audio-context';
import { AudioPlayer } from './audio-player';

class FakeSource {
  buffer: { duration: number } | null = null;
  onended: (() => void) | null = null;
  startedAt: number | null = null;
  stopped = false;

  connect(): void {
    return undefined;
  }

  start(when: number): void {
    this.startedAt = when;
  }

  stop(): void {
    this.stopped = true;
  }

  finish(): void {
    this.onended?.();
  }
}

class FakeAudioContext {
  currentTime = 10;
  state = 'running';
  destination = {};
  readonly sources: FakeSource[] = [];

  createAnalyser() {
    return {
      fftSize: 0,
      connect: () => undefined,
      getByteTimeDomainData: (samples: Uint8Array) => samples.fill(255),
    };
  }

  readonly tones: { frequency: number; startedAt: number | null }[] = [];

  createOscillator() {
    const tone = { frequency: { value: 0 }, startedAt: null as number | null };
    this.tones.push({
      get frequency() {
        return tone.frequency.value;
      },
      get startedAt() {
        return tone.startedAt;
      },
    });
    return {
      frequency: tone.frequency,
      connect: (node: unknown) => node,
      start: (when: number) => (tone.startedAt = when),
      stop: () => undefined,
    };
  }

  createGain() {
    return {
      gain: { setValueAtTime: () => undefined, exponentialRampToValueAtTime: () => undefined },
      connect: () => undefined,
    };
  }

  createBufferSource(): FakeSource {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }

  decodeAudioData(audio: ArrayBuffer): Promise<{ duration: number }> {
    return Promise.resolve({ duration: audio.byteLength });
  }

  resume(): Promise<void> {
    return Promise.resolve();
  }
}

describe('AudioPlayer', () => {
  let context: FakeAudioContext;
  let player: AudioPlayer;

  beforeEach(() => {
    context = new FakeAudioContext();
    TestBed.configureTestingModule({
      providers: [{ provide: AUDIO_CONTEXT, useValue: () => context as unknown as AudioContext }],
    });
    player = TestBed.inject(AudioPlayer);
  });

  it('plays sentences back to back without gaps or overlap', async () => {
    void player.play(new ArrayBuffer(2));
    await player.play(new ArrayBuffer(3));

    expect(context.sources.map((s) => s.startedAt)).toEqual([10, 12]);
    expect(player.playing()).toBe(true);
  });

  it('is no longer playing once every sentence has ended', async () => {
    await player.play(new ArrayBuffer(2));
    await player.play(new ArrayBuffer(2));

    context.sources[0].finish();
    expect(player.playing()).toBe(true);
    context.sources[1].finish();
    expect(player.playing()).toBe(false);
  });

  it('reports a loudness level only while playing', async () => {
    expect(player.level()).toBe(0);

    await player.play(new ArrayBuffer(2));

    expect(player.level()).toBeGreaterThan(0.5);
  });

  it('can be interrupted, and starts fresh afterwards', async () => {
    await player.play(new ArrayBuffer(5));

    player.stop();
    expect(context.sources[0].stopped).toBe(true);
    expect(player.playing()).toBe(false);

    await player.play(new ArrayBuffer(1));
    expect(context.sources[1].startedAt).toBe(10);
  });

  it('stays silent when muted', async () => {
    player.muted.set(true);

    await player.play(new ArrayBuffer(2));

    expect(context.sources).toEqual([]);
  });

  it('chimes after the speech already queued, then plays what comes next', async () => {
    void player.play(new ArrayBuffer(2));
    await player.chime();
    await player.play(new ArrayBuffer(1));

    expect(context.tones.map((tone) => tone.startedAt)).toEqual([12, 12.18]);
    expect(context.sources[1].startedAt).toBeCloseTo(12.9);
  });

  it('chimes even when the companion is muted', async () => {
    player.muted.set(true);

    await player.chime();

    expect(context.tones).toHaveLength(2);
  });
});
