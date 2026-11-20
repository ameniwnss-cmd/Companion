import { Reminder, Task } from './plans.service';
import { todayReminders, todayTasks } from './today';

const NOW = new Date(2037, 10, 20, 12, 0);

function at(day: number, hour: number): string {
  return new Date(2037, 10, day, hour, 0).toISOString();
}

function task(id: string, due_at: string | null, done = false): Task {
  return { id, title: id, due_at, done, created_at: at(18, 9) };
}

function reminder(id: string, remind_at: string, delivered = false): Reminder {
  return { id, title: id, remind_at, delivered };
}

describe('todayTasks', () => {
  it('keeps open tasks that are undated, due today or overdue', () => {
    const tasks = [
      task('undated', null),
      task('today', at(20, 18)),
      task('overdue', at(19, 9)),
      task('tomorrow', at(21, 9)),
      task('finished', at(20, 9), true),
    ];

    expect(todayTasks(tasks, NOW).map((t) => t.id)).toEqual(['undated', 'today', 'overdue']);
  });
});

describe('todayReminders', () => {
  it("keeps today's reminders in time order, including ones already sent", () => {
    const reminders = [
      reminder('evening', at(20, 21)),
      reminder('yesterday', at(19, 9)),
      reminder('morning', at(20, 8), true),
      reminder('tomorrow', at(21, 8)),
    ];

    expect(todayReminders(reminders, NOW).map((r) => r.id)).toEqual(['morning', 'evening']);
  });
});
