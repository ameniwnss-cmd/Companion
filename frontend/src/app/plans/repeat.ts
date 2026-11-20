const BY_DAY_NUMBER = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
] as const;

const WEEK_ORDER = [...BY_DAY_NUMBER.slice(1), BY_DAY_NUMBER[0]];
const WEEKDAYS = WEEK_ORDER.slice(0, 5);
const WEEKEND = WEEK_ORDER.slice(5);

export function weekdayOf(date: Date): string {
  return BY_DAY_NUMBER[date.getDay()];
}

function exactly(chosen: ReadonlySet<string>, days: readonly string[]): boolean {
  return chosen.size === days.length && days.every((day) => chosen.has(day));
}

export function repeatLabel(days: readonly string[]): string {
  const chosen = new Set(days);
  if (exactly(chosen, WEEK_ORDER)) {
    return 'Every day';
  }
  if (exactly(chosen, WEEKDAYS)) {
    return 'Every weekday';
  }
  if (exactly(chosen, WEEKEND)) {
    return 'Every weekend';
  }
  const names = WEEK_ORDER.filter((day) => chosen.has(day)).map(
    (day) => day[0].toUpperCase() + day.slice(1, 3),
  );
  return `Every ${names.join(', ')}`;
}

export function clockTime(timeOfDay: string): Date {
  const [hours, minutes] = timeOfDay.split(':').map(Number);
  return new Date(2000, 0, 1, hours, minutes);
}
