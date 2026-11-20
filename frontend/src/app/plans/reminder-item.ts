import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, booleanAttribute, input, output } from '@angular/core';
import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { Reminder } from './plans.service';

@Component({
  selector: '[app-reminder-item]',
  imports: [DatePipe, Button, Icon],
  template: `
    <span class="time">
      {{ reminder().remind_at | date: 'h:mm a' }}
      <span class="pixel-label">
        {{ reminder().delivered ? 'SENT' : (reminder().remind_at | date: 'EEE d MMM') }}
      </span>
    </span>
    <span class="main">{{ reminder().title }}</span>
    @if (removable()) {
      <button
        app-button
        variant="ghost"
        type="button"
        [attr.aria-label]="'Delete reminder ' + reminder().title"
        (click)="removed.emit()"
      >
        <app-icon name="trash" />
      </button>
    }
  `,
  styleUrl: './plan-item.scss',
  host: { '[class.done]': 'reminder().delivered' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReminderItem {
  readonly reminder = input.required<Reminder>();
  readonly removable = input(false, { transform: booleanAttribute });
  readonly removed = output();
}
