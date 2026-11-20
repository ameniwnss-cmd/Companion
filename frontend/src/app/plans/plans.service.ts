import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Task {
  id: string;
  title: string;
  due_at: string | null;
  repeat_days: string[] | null;
  time_of_day: string | null;
  done: boolean;
  created_at: string;
}

export interface Reminder {
  id: string;
  title: string;
  remind_at: string;
  repeat_days: string[] | null;
  delivered: boolean;
}

export interface PlanDay {
  day: string;
  activity: string;
  minutes: number | null;
}

export interface WeeklyPlan {
  id: string;
  name: string;
  sessions: PlanDay[];
  created_at: string;
}

export const PLANS_UNREACHABLE = 'Could not reach the backend. Is it running?';

type Collection = 'tasks' | 'reminders' | 'weekly-plans';

@Injectable()
export class PlansService {
  private readonly http = inject(HttpClient);
  private readonly url = environment.apiUrl;

  readonly tasks = signal<readonly Task[]>([]);
  readonly reminders = signal<readonly Reminder[]>([]);
  readonly weeklyPlans = signal<readonly WeeklyPlan[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async load(): Promise<void> {
    await this.run(async () => {
      const [tasks, reminders, weeklyPlans] = await Promise.all([
        firstValueFrom(this.http.get<Task[]>(`${this.url}/tasks`)),
        firstValueFrom(this.http.get<Reminder[]>(`${this.url}/reminders`)),
        firstValueFrom(this.http.get<WeeklyPlan[]>(`${this.url}/weekly-plans`)),
      ]);
      this.tasks.set(tasks);
      this.reminders.set(reminders);
      this.weeklyPlans.set(weeklyPlans);
    });
  }

  async setDone(task: Task, done: boolean): Promise<void> {
    await this.run(async () => {
      const updated = await firstValueFrom(
        this.http.patch<Task>(`${this.url}/tasks/${task.id}`, { done }),
      );
      this.tasks.update((all) => all.map((t) => (t.id === task.id ? updated : t)));
    });
  }

  async remove(collection: Collection, id: string): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.http.delete(`${this.url}/${collection}/${id}`));
      const keep = <T extends { id: string }>(all: readonly T[]) => all.filter((x) => x.id !== id);
      if (collection === 'tasks') {
        this.tasks.update(keep);
      } else if (collection === 'reminders') {
        this.reminders.update(keep);
      } else {
        this.weeklyPlans.update(keep);
      }
    });
  }

  private async run(request: () => Promise<void>): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      await request();
    } catch {
      this.error.set(PLANS_UNREACHABLE);
    } finally {
      this.loading.set(false);
    }
  }
}
