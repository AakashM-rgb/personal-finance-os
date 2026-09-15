"use client";

import type { CalendarDay, CalendarMonth } from "@/lib/calendar";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface CalendarGridProps {
  data: CalendarMonth;
  onSelectDay: (day: CalendarDay) => void;
}

export function CalendarGrid({ data, onSelectDay }: CalendarGridProps) {
  // JS Date's day-of-week for the 1st of the month tells us how many
  // empty leading cells the grid needs to align day 1 under its weekday.
  const firstWeekday = new Date(`${data.days[0]?.date ?? `${data.year}-${data.month}-01`}T00:00:00`).getDay();
  const leadingBlanks = Array.from({ length: firstWeekday }, (_, i) => i);
  const today = todayIso();

  return (
    <div>
      <div className="grid grid-cols-7 gap-1 text-center text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="py-1">
            {label}
          </div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {leadingBlanks.map((i) => (
          <div key={`blank-${i}`} />
        ))}
        {data.days.map((day) => {
          const hasIncome = day.income_minor > 0;
          const hasExpense = day.expense_minor > 0;
          const hasBills = day.bills.length > 0;
          const isToday = day.date === today;

          return (
            <button
              key={day.date}
              type="button"
              onClick={() => onSelectDay(day)}
              className={cn(
                "flex min-h-16 flex-col items-start gap-0.5 rounded-md border p-1.5 text-left text-xs transition-colors hover:border-zinc-400 dark:hover:border-zinc-600 sm:min-h-20 sm:p-2",
                isToday
                  ? "border-blue-500 bg-blue-50 dark:border-blue-500 dark:bg-blue-950"
                  : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
              )}
            >
              <span
                className={cn(
                  "font-medium",
                  isToday
                    ? "text-blue-700 dark:text-blue-400"
                    : "text-zinc-700 dark:text-zinc-300"
                )}
              >
                {Number(day.date.slice(-2))}
              </span>
              {hasIncome && (
                <span className="w-full truncate text-emerald-600 dark:text-emerald-400">
                  +{formatMoney(day.income_minor, data.currency)}
                </span>
              )}
              {hasExpense && (
                <span className="w-full truncate text-red-600 dark:text-red-400">
                  -{formatMoney(day.expense_minor, data.currency)}
                </span>
              )}
              {hasBills && (
                <span className="w-full truncate text-amber-600 dark:text-amber-400">
                  {day.bills.length} bill{day.bills.length === 1 ? "" : "s"} due
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
