import { Reminder, Task, WeeklyPlan } from './plans.service';
import { repeatLabel } from './repeat';
import { todayPlan, todayReminders, todayTasks } from './today';

const NOW = new Date(2037, 10, 20, 12, 0);

function at(day: number, hour: number): string {
  return new Date(2037, 10, day, hour, 0).toISOString();
}

function task(id: string, due_at: string | null, done = false): Task {
  return {
    id,
    title: id,
    due_at,
    repeat_days: null,
    time_of_day: null,
    done,
    created_at: at(18, 9),
  };
}

function reminder(id: string, remind_at: string, delivered = false): Reminder {
  return { id, title: id, remind_at, repeat_days: null, delivered };
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

describe('repeating tasks', () => {
  it('show up on their days only, until ticked off', () => {
    const fridays = { ...task('fridays', null), repeat_days: ['friday'] };
    const mondays = { ...task('mondays', null), repeat_days: ['monday'] };
    const doneToday = { ...task('done', null, true), repeat_days: ['friday'] };

    expect(todayTasks([fridays, mondays, doneToday], NOW).map((t) => t.id)).toEqual(['fridays']);
  });
});

describe('todayPlan', () => {
  it("lists today's activity from every weekly plan", () => {
    const plans: WeeklyPlan[] = [
      {
        id: 'p1',
        name: 'Job hunt',
        created_at: at(18, 9),
        sessions: [
          { day: 'thursday', activity: 'networking', minutes: null },
          { day: 'friday', activity: 'two applications', minutes: 60 },
        ],
      },
    ];

    expect(todayPlan(plans, NOW)).toEqual([
      { day: 'friday', activity: 'two applications', minutes: 60, plan: 'Job hunt' },
    ]);
  });
});

describe('repeatLabel', () => {
  it('names common patterns and lists the rest in week order', () => {
    const week = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    expect(repeatLabel(week)).toBe('Every day');
    expect(repeatLabel(week.slice(1, 6))).toBe('Every weekday');
    expect(repeatLabel(['sunday', 'saturday'])).toBe('Every weekend');
    expect(repeatLabel(['thursday', 'monday'])).toBe('Every Mon, Thu');
  });
});
