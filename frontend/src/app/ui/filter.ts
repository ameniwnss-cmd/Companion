import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';
import { Button } from './button';

export interface FilterOption<T extends string> {
  value: T;
  label: string;
}

@Component({
  selector: 'app-filter',
  imports: [Button],
  template: `
    <div role="group" [attr.aria-label]="label()">
      @for (option of options(); track option.value) {
        <button
          app-button
          variant="tab"
          type="button"
          [active]="option.value === value()"
          [attr.aria-pressed]="option.value === value()"
          (click)="value.set(option.value)"
        >
          {{ option.label }}
        </button>
      }
    </div>
  `,
  styles: `
    div {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin-bottom: 0.8rem;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Filter<T extends string> {
  readonly label = input.required<string>();
  readonly options = input.required<readonly FilterOption<T>[]>();
  readonly value = model.required<T>();
}
