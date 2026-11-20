import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { environment } from '../../environments/environment';
import { Icon, IconName } from '../ui/icon';

interface NavLink {
  path: string;
  label: string;
  icon: IconName;
  exact: boolean;
}

const LINKS: readonly NavLink[] = [
  { path: '/', label: 'My room', icon: 'house', exact: true },
  { path: '/plans', label: 'Quest log', icon: 'quests', exact: false },
  { path: '/memories', label: 'Diary', icon: 'diary', exact: false },
];

@Component({
  selector: 'app-top-bar',
  imports: [RouterLink, RouterLinkActive, Icon],
  template: `
    <a class="brand" routerLink="/">
      <app-icon name="sparkles" />
      <span>companion<small>YOUR LITTLE WORLD</small></span>
    </a>
    <nav aria-label="Main">
      @for (link of links; track link.path) {
        <a
          [routerLink]="link.path"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: link.exact }"
        >
          <app-icon [name]="link.icon" />
          <span class="label">{{ link.label }}</span>
        </a>
      }
      @if (devTools) {
        <a routerLink="/dev" routerLinkActive="active">Dev</a>
      }
    </nav>
  `,
  styleUrl: './top-bar.scss',
  host: { role: 'banner' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TopBar {
  protected readonly links = LINKS;
  protected readonly devTools = environment.devTools;
}
