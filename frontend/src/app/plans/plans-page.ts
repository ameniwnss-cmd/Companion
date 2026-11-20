import { TitleCasePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { MenuPage } from '../layout/menu-page';
import { Button } from '../ui/button';
import { Empty } from '../ui/empty';
import { Filter, FilterOption } from '../ui/filter';
import { Icon } from '../ui/icon';
import { PlansService } from './plans.service';
import { ReminderItem } from './reminder-item';
import { TaskItem } from './task-item';

type TaskFilter = 'all' | 'open' | 'done';

const FILTERS: readonly FilterOption<TaskFilter>[] = [
  { value: 'all', label: 'All quests' },
  { value: 'open', label: 'In progress' },
  { value: 'done', label: 'Completed' },
];

@Component({
  selector: 'app-plans-page',
  imports: [TitleCasePipe, MenuPage, Button, Empty, Filter, Icon, ReminderItem, TaskItem],
  templateUrl: './plans-page.html',
  styleUrl: './plans-page.scss',
  providers: [PlansService],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlansPage implements OnInit {
  protected readonly plans = inject(PlansService);
  protected readonly filters = FILTERS;
  protected readonly filter = signal<TaskFilter>('all');

  protected readonly doneCount = computed(() => this.plans.tasks().filter((t) => t.done).length);
  protected readonly shownTasks = computed(() => {
    const filter = this.filter();
    return this.plans.tasks().filter((t) => filter === 'all' || t.done === (filter === 'done'));
  });
  protected readonly empty = computed(
    () =>
      !this.plans.loading() &&
      !this.plans.error() &&
      this.plans.tasks().length +
        this.plans.reminders().length +
        this.plans.workoutPlans().length ===
        0,
  );

  ngOnInit(): void {
    void this.plans.load();
  }
}
