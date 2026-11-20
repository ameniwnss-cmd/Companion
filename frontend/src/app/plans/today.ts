import { PlanDay, Reminder, Task, WeeklyPlan } from './plans.service';
import { weekdayOf } from './repeat';

export interface TodayPlanItem extends PlanDay {
  plan: string;
}

function dayBounds(now: Date): { start: number; end: number } {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  return { start: start.getTime(), end: end.getTime() };
}

export function todayTasks(tasks: readonly Task[], now: Date): Task[] {
  const { end } = dayBounds(now);
  const today = weekdayOf(now);
  return tasks.filter((task) => {
    if (task.done) {
      return false;
    }
    if (task.repeat_days) {
      return task.repeat_days.includes(today);
    }
    return task.due_at === null || Date.parse(task.due_at) <= end;
  });
}

export function todayReminders(reminders: readonly Reminder[], now: Date): Reminder[] {
  const { start, end } = dayBounds(now);
  return reminders
    .filter((r) => {
      const at = Date.parse(r.remind_at);
      return at >= start && at <= end;
    })
    .sort((a, b) => Date.parse(a.remind_at) - Date.parse(b.remind_at));
}

export function todayPlan(plans: readonly WeeklyPlan[], now: Date): TodayPlanItem[] {
  const today = weekdayOf(now);
  return plans.flatMap((plan) =>
    plan.sessions.filter((day) => day.day === today).map((day) => ({ ...day, plan: plan.name })),
  );
}
