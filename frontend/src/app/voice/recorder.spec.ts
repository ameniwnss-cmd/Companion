import { TestBed } from '@angular/core/testing';
import { AUDIO_CONTEXT } from './audio-context';
import { MEDIA, MIN_RECORDING_BYTES, MediaApi, Recorder } from './recorder';

class FakeMediaRecorder {
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = 'inactive';

  constructor(
    readonly mimeType: string,
    private readonly chunks: Blob[],
  ) {}

  start(): void {
    this.state = 'recording';
  }

  stop(): void {
    this.state = 'inactive';
    for (const data of this.chunks) {
      this.ondataavailable?.({ data });
    }
    this.onstop?.();
  }
}

describe('Recorder', () => {
  let stoppedTracks: number;
  let chunks: Blob[];
  let constraints: MediaStreamConstraints | undefined;
  let blocked: boolean;
  let recorder: Recorder;

  beforeEach(() => {
    stoppedTracks = 0;
    chunks = [new Blob([new Uint8Array(MIN_RECORDING_BYTES)])];
    blocked = false;
    const media: MediaApi = {
      getUserMedia: (c) => {
        constraints = c;
        if (blocked) {
          return Promise.reject(new DOMException('denied', 'NotAllowedError'));
        }
        const track = { stop: () => (stoppedTracks += 1) };
        return Promise.resolve({ getTracks: () => [track] } as unknown as MediaStream);
      },
      createRecorder: (_stream, mimeType) =>
        new FakeMediaRecorder(mimeType ?? '', chunks) as unknown as MediaRecorder,
      supportedMimeType: () => 'audio/webm;codecs=opus',
    };
    const context = {
      createAnalyser: () => ({
        fftSize: 0,
        getByteTimeDomainData: (samples: Uint8Array) => samples.fill(200),
      }),
      createMediaStreamSource: () => ({ connect: () => undefined, disconnect: () => undefined }),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: MEDIA, useValue: media },
        { provide: AUDIO_CONTEXT, useValue: () => context as unknown as AudioContext },
      ],
    });
    recorder = TestBed.inject(Recorder);
  });

  it('records with echo cancellation and returns the audio as one blob', async () => {
    await recorder.start();
    expect(recorder.recording()).toBe(true);
    expect(constraints).toEqual({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });

    const recording = await recorder.stop();

    expect(recording?.type).toBe('audio/webm;codecs=opus');
    expect(recording?.size).toBe(MIN_RECORDING_BYTES);
    expect(recorder.recording()).toBe(false);
    expect(stoppedTracks).toBe(1);
  });

  it('ignores an accidental tap that captured almost nothing', async () => {
    chunks = [new Blob(['x'])];
    await recorder.start();

    expect(await recorder.stop()).toBeNull();
  });

  it('stopping without recording does nothing', async () => {
    expect(await recorder.stop()).toBeNull();
  });

  it('reports a blocked microphone to the caller', async () => {
    blocked = true;

    await expect(recorder.start()).rejects.toThrow('denied');
    expect(recorder.recording()).toBe(false);
  });

  it('reports the microphone loudness only while recording', async () => {
    expect(recorder.level()).toBe(0);

    await recorder.start();
    expect(recorder.level()).toBeGreaterThan(0.5);

    await recorder.stop();
    expect(recorder.level()).toBe(0);
  });
});
