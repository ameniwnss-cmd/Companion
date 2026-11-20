import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  inject,
  input,
} from '@angular/core';

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'offline';

const SMOOTHING = 0.25;
const RUNES = ['✦', '◆', '✧', '◆', '✦', '✧'];

@Component({
  selector: 'app-orb',
  template: `
    <span class="ring"></span>
    <span class="ring"></span>
    <span class="ring"></span>
    <span class="orbit">
      @for (rune of runes; track $index) {
        <span class="rune" [style.--i]="$index">{{ rune }}</span>
      }
    </span>
    <span class="body">
      <span class="core">
        <span class="current one"></span>
        <span class="current two"></span>
        <span class="current three"></span>
      </span>
      <span class="shine"></span>
    </span>
    <span class="shadow"></span>
    @if (state() === 'listening') {
      <span class="bars"><i></i><i></i><i></i><i></i><i></i></span>
    }
  `,
  styleUrl: './orb.scss',
  host: { '[attr.data-state]': 'state()', 'aria-hidden': 'true' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Orb {
  readonly state = input.required<OrbState>();
  readonly level = input<() => number>(() => 0);

  protected readonly runes = RUNES;
  private smoothed = 0;
  private frame = 0;

  constructor() {
    const host = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const reduceMotion =
      typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    afterNextRender(() => {
      if (reduceMotion) {
        return;
      }
      const follow = () => {
        const target = Math.min(1, Math.max(0, this.level()()));
        this.smoothed += (target - this.smoothed) * SMOOTHING;
        host.style.setProperty('--level', this.smoothed.toFixed(3));
        this.frame = requestAnimationFrame(follow);
      };
      this.frame = requestAnimationFrame(follow);
    });
    inject(DestroyRef).onDestroy(() => cancelAnimationFrame(this.frame));
  }
}
