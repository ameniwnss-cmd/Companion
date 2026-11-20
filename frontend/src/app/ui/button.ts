import { ChangeDetectionStrategy, Component, booleanAttribute, input } from '@angular/core';

export type ButtonVariant = 'primary' | 'secondary' | 'tool' | 'tab' | 'ghost' | 'danger';

@Component({
  selector: 'button[app-button], a[app-button]',
  template: '<ng-content />',
  styleUrl: './button.scss',
  host: {
    '[attr.data-variant]': 'variant()',
    '[class.active]': 'active()',
  },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Button {
  readonly variant = input<ButtonVariant>('secondary');
  readonly active = input(false, { transform: booleanAttribute });
}
