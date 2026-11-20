import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-empty',
  template: '<p><ng-content /></p>',
  styles: `
    p {
      padding: 0.8rem;
      color: var(--muted);
      font-size: 0.95rem;
      text-align: center;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Empty {}
