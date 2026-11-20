import { ChangeDetectionStrategy, Component, OnInit, computed, inject } from '@angular/core';
import { SideCard } from '../layout/side-card';
import { PlansService } from '../plans/plans.service';
import { ReminderItem } from '../plans/reminder-item';
import { TaskItem } from '../plans/task-item';
import { todayReminders, todayTasks } from '../plans/today';
import { Empty } from '../ui/empty';
import { Conversation } from './conversation';

@Component({
  selector: 'app-room',
  imports: [SideCard, ReminderItem, TaskItem, Empty, Conversation],
  template: `
    <app-conversation class="talk" (plansChanged)="plans.load()" />

    <app-side-card
      class="quests"
      heading="Today's quests"
      icon="sparkles"
      link="/plans"
      linkLabel="Open quest log"
      [count]="tasks().length"
    >
      <ul>
        @for (task of tasks(); track task.id) {
          <li
            app-task-item
            data-testid="today-task"
            dateFormat="EEE h:mm a"
            [task]="task"
            (toggled)="plans.setDone(task, true)"
          ></li>
        } @empty {
          <li><app-empty>All clear. Rest well ♡</app-empty></li>
        }
      </ul>
    </app-side-card>

    <app-side-card
      class="reminders"
      heading="Today's reminders"
      icon="bell"
      link="/plans"
      linkLabel="All reminders"
      [count]="upcoming()"
    >
      <ul>
        @for (reminder of reminders(); track reminder.id) {
          <li app-reminder-item data-testid="today-reminder" [reminder]="reminder"></li>
        } @empty {
          <li><app-empty>All quiet for now.</app-empty></li>
        }
      </ul>
    </app-side-card>
  `,
  styleUrl: './room.scss',
  providers: [PlansService],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Room implements OnInit {
  protected readonly plans = inject(PlansService);
  protected readonly tasks = computed(() => todayTasks(this.plans.tasks(), new Date()));
  protected readonly reminders = computed(() => todayReminders(this.plans.reminders(), new Date()));
  protected readonly upcoming = computed(() => this.reminders().filter((r) => !r.delivered).length);

  ngOnInit(): void {
    void this.plans.load();
  }
}
