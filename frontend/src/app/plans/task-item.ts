import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, booleanAttribute, input, output } from '@angular/core';
import { Button } from '../ui/button';
import { Check } from '../ui/check';
import { Icon } from '../ui/icon';
import { Task } from './plans.service';

@Component({
  selector: '[app-task-item]',
  imports: [DatePipe, Button, Check, Icon],
  template: `
    <div class="main">
      <app-check [checked]="task().done" (toggled)="toggled.emit()">{{ task().title }}</app-check>
      @if (task().due_at; as due) {
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
}
