import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RoomScene } from '../scene/room-scene';
import { Button } from '../ui/button';
import { Icon, IconName } from '../ui/icon';
import { Panel } from '../ui/panel';

@Component({
  selector: 'app-menu-page',
  imports: [RouterLink, RoomScene, Button, Icon, Panel],
  template: `
    <app-room-scene decorative />
    <main app-panel class="menu">
      <header class="title">
        <div>
          <span class="pixel-label eyebrow">{{ eyebrow() }}</span>
          <h1><app-icon [name]="icon()" />{{ heading() }}</h1>
        </div>
        <a app-button routerLink="/"><app-icon name="arrow-left" />Back to room</a>
      </header>
      @if (error(); as message) {
        <p class="error" role="alert">{{ message }}</p>
      }
      <ng-content />
      <footer class="pixel-label footer">{{ footer() }}</footer>
    </main>
  `,
  styleUrl: './menu-page.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MenuPage {
  readonly eyebrow = input.required<string>();
  readonly heading = input.required<string>();
  readonly icon = input.required<IconName>();
  readonly footer = input.required<string>();
  readonly error = input<string | null>(null);
}
