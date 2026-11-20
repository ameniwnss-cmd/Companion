import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Icon, IconName } from '../ui/icon';
import { Panel } from '../ui/panel';

@Component({
  selector: 'app-side-card',
  imports: [RouterLink, Icon, Panel],
  template: `
    <section app-panel class="card" [attr.aria-label]="heading()">
      <h2>
        <app-icon [name]="icon()" />
        <span class="heading">{{ heading() }}</span>
        <span class="count">{{ count() }}</span>
      </h2>
      <ng-content />
      <a class="more" [routerLink]="link()">{{ linkLabel() }} <app-icon name="arrow-right" /></a>
    </section>
  `,
  styleUrl: './side-card.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SideCard {
  readonly heading = input.required<string>();
  readonly icon = input.required<IconName>();
  readonly count = input.required<number>();
  readonly link = input.required<string>();
  readonly linkLabel = input.required<string>();
}
