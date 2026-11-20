import { ChangeDetectionStrategy, Component, booleanAttribute, input } from '@angular/core';

const FIREFLIES = Array.from({ length: 14 }, (_, i) => ({
  left: (i * 37 + 11) % 100,
  top: 20 + ((i * 53) % 65),
  delay: (i * 0.7) % 6,
  duration: 6 + (i % 5),
}));

const LEAVES = Array.from({ length: 7 }, (_, i) => ({
  left: 6 + i * 14,
  delay: i * 2.3,
  duration: 11 + (i % 3) * 3,
}));

@Component({
  selector: 'app-room-scene',
  template: `
    <img class="art" src="room.webp" alt="" draggable="false" />
    <div class="glow lantern-left"></div>
    <div class="glow lantern-right"></div>
    <div class="glow window"></div>
    <div class="vignette"></div>
    @for (fly of fireflies; track $index) {
      <span
        class="firefly"
        [style.left.%]="fly.left"
        [style.top.%]="fly.top"
        [style.animation-delay.s]="fly.delay"
        [style.animation-duration.s]="fly.duration"
      ></span>
    }
    @for (leaf of leaves; track $index) {
      <span
        class="leaf"
        [style.left.%]="leaf.left"
        [style.animation-delay.s]="leaf.delay"
        [style.animation-duration.s]="leaf.duration"
      ></span>
    }
  `,
  styleUrl: './room-scene.scss',
  host: { 'aria-hidden': 'true', '[class.decorative]': 'decorative()' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoomScene {
  readonly decorative = input(false, { transform: booleanAttribute });
  protected readonly fireflies = FIREFLIES;
  protected readonly leaves = LEAVES;
}
