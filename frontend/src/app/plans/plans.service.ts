import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

export interface Task {
  id: string;
  title: string;
  due_at: string | null;
  done: boolean;
  created_at: string;
}

export interface Reminder {
  id: string;
  title: string;
  remind_at: string;
  delivered: boolean;
}

export interface WorkoutSession {
  day: string;
  focus: string;
  minutes: number;
}

export interface WorkoutPlan {
  id: string;
  name: string;
  sessions: WorkoutSession[];
  created_at: string;
}

export const PLANS_UNREACHABLE = 'Could not reach the backend. Is it running?';

type Collection = 'tasks' | 'reminders' | 'workout-plans';

@Injectable()
export class PlansService {
  private readonly http = inject(HttpClient);
  private readonly url = environment.apiUrl;

  readonly tasks = signal<readonly Task[]>([]);
  readonly reminders = signal<readonly Reminder[]>([]);
  readonly workoutPlans = signal<readonly WorkoutPlan[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async load(): Promise<void> {
    await this.run(async () => {
      const [tasks, reminders, workoutPlans] = await Promise.all([
        firstValueFrom(this.http.get<Task[]>(`${this.url}/tasks`)),
        firstValueFrom(this.http.get<Reminder[]>(`${this.url}/reminders`)),
        firstValueFrom(this.http.get<WorkoutPlan[]>(`${this.url}/workout-plans`)),
      ]);
      this.tasks.set(tasks);
      this.reminders.set(reminders);
      this.workoutPlans.set(workoutPlans);
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
        this.workoutPlans.update(keep);
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
