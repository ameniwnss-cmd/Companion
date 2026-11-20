import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  booleanAttribute,
  computed,
  input,
  output,
} from '@angular/core';
import { Button } from '../ui/button';
import { Check } from '../ui/check';
import { Icon } from '../ui/icon';
import { Task } from './plans.service';
import { clockTime, repeatLabel } from './repeat';

@Component({
  selector: '[app-task-item]',
  imports: [DatePipe, Button, Check, Icon],
  template: `
    <div class="main">
      <app-check [checked]="task().done" (toggled)="toggled.emit()">{{ task().title }}</app-check>
      @if (task().repeat_days; as days) {
        <span class="pixel-label">
          <app-icon name="repeat" />{{ repeats(days) }}
          @if (time(); as at) {
            · {{ at | date: 'h:mm a' }}
          }
        </span>
      } @else if (task().due_at; as due) {
        <span class="pixel-label">Due {{ due | date: dateFormat() }}</span>
      }
    </div>
    @if (removable()) {
      <button
        app-button
        variant="ghost"
        type="button"
        [attr.aria-label]="'Delete task ' + task().title"
        (click)="removed.emit()"
      >
        <app-icon name="trash" />
      </button>
    }
  `,
  styleUrl: './plan-item.scss',
  host: { '[class.done]': 'task().done' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskItem {
  readonly task = input.required<Task>();
  readonly removable = input(false, { transform: booleanAttribute });
  readonly dateFormat = input('EEE d MMM, h:mm a');
  readonly toggled = output();
  readonly removed = output();

  protected readonly repeats = repeatLabel;
  protected readonly time = computed(() => {
    const at = this.task().time_of_day;
    return at ? clockTime(at) : null;
  });
}
