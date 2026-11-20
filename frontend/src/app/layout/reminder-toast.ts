import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ReminderAlerts } from '../session/reminder-alerts';
import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { Panel } from '../ui/panel';

@Component({
  selector: 'app-reminder-toast',
  imports: [Button, Icon, Panel],
  template: `
    @if (alerts.current(); as due) {
      <div app-panel class="toast" role="status" data-testid="reminder-alert">
        <app-icon name="bell" />
        <span>{{ due.text }}</span>
        <button
          app-button
          variant="ghost"
          type="button"
          aria-label="Dismiss reminder"
          (click)="alerts.dismiss(due.id)"
        >
          <app-icon name="close" />
        </button>
      </div>
    }
  `,
  styles: `
    :host {
      position: fixed;
      top: 4.75rem;
      right: 1.25rem;
      z-index: 40;
      max-width: min(22rem, calc(100vw - 2rem));
    }
    .toast {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.5rem 0.4rem 0.5rem 0.8rem;
      animation: slide-in 0.4s ease-out both;
    }
    app-icon:first-child {
      color: var(--honey);
      animation: ring 3s infinite;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReminderToast {
  protected readonly alerts = inject(ReminderAlerts);
}
