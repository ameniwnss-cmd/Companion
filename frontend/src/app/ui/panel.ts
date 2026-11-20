import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: '[app-panel]',
  template: '<ng-content />',
  styles: `
    :host {
      background: var(--paper);
      color: var(--ink);
      border: 3px solid var(--ink);
      border-radius: 6px;
      box-shadow:
        var(--shadow-pixel),
        inset 0 0 0 3px var(--paper-dark);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Panel {}
