import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-check',
  template: `
    <label>
      <input type="checkbox" [checked]="checked()" (change)="toggled.emit()" />
      <span class="text"><ng-content /></span>
    </label>
  `,
  styles: `
    :host {
      display: block;
      min-width: 0;
    }
    label {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      cursor: pointer;
    }
    input {
      flex: none;
      appearance: none;
      width: 1.3rem;
      height: 1.3rem;
      margin: 0;
      border: 2px solid var(--ink);
      background: var(--paper) center / 80% no-repeat;
      cursor: pointer;
    }
    input:checked {
      background-color: var(--mint);
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232a1f14' stroke-width='4' stroke-linecap='square'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E");
    }
    input:focus-visible {
      outline: 3px dashed var(--amber);
      outline-offset: 2px;
    }
    .text {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    input:checked + .text {
      text-decoration: line-through;
      opacity: 0.6;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Check {
  readonly checked = input.required<boolean>();
  readonly toggled = output();
}
