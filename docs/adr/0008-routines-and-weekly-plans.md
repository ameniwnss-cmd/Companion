# 0008. Routines repeat; weekly plans hold a different activity each day

- Status: Accepted

## Context

Users describe routines ("apply for jobs every weekday at 9") and weekly schedules ("Monday
portfolio, Tuesday two applications"). The first version only had one-off tasks and workout
plans, so the model turned every routine into one task per day: seven near-identical rows that
had to be ticked and deleted one by one.

## Decision

Tasks and reminders can **repeat** on chosen weekdays, with an optional time of day. A repeating
task is a single row: it appears in the day's list on its repeat days, and ticking it off records
the date it was done, so it is open again the next repeat day. A repeating reminder keeps one row
and rolls its next time forward after each delivery. The next time is computed in the user's
timezone, so it stays at the same local time across daylight saving changes.

Workout plans became **weekly plans**: a name and, per weekday, an activity with optional
minutes. A workout schedule is simply one kind of weekly plan, and today's activity from every
plan appears next to today's tasks.

The model chooses between them through the tool descriptions: the same thing on several days is a
repeating task, a different thing on each day is a weekly plan. Days and times are still parsed
by code, never by the model.

## Consequences

- One row per routine instead of one per day, so the quest log stays readable.
- Done state for a repeating task is per day only; there is no history of past days yet, which a
  future streaks feature would need.
- Existing workout plans were migrated in place (`focus` became `activity`).
