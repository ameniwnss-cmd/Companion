import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RoomScene } from '../scene/room-scene';
import { COMPANION_URL } from '../session/companion-session';
import { Panel } from '../ui/panel';
import { Room } from './room';

@Component({
  selector: 'app-talk-page',
  imports: [RoomScene, Panel, Room],
  template: `
    <app-room-scene />
    <main>
      @if (configured) {
        <app-room />
      } @else {
        <section app-panel class="notice">
          <h1>Companion</h1>
          <p>
            This build has no companion server configured. Run the app locally to talk to your
            companion.
          </p>
        </section>
      }
    </main>
  `,
  styles: `
    main {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      min-height: 100dvh;
    }
    .notice {
      display: grid;
      gap: 0.5rem;
      place-self: center;
      max-width: 28rem;
      margin: 1rem;
      padding: 1.5rem;
      text-align: center;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TalkPage {
  protected readonly configured = inject(COMPANION_URL) !== '';
}
