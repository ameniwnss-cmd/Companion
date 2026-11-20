import { Reminder, Task } from './plans.service';

function dayBounds(now: Date): { start: number; end: number } {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  return { start: start.getTime(), end: end.getTime() };
}

export function todayTasks(tasks: readonly Task[], now: Date): Task[] {
  const { end } = dayBounds(now);
  return tasks.filter((t) => !t.done && (t.due_at === null || Date.parse(t.due_at) <= end));
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
