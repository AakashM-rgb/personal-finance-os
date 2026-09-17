"use client";

import { Button } from "@/components/ui/button";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

interface MonthNavigatorProps {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
}

export function MonthNavigator({ year, month, onChange }: MonthNavigatorProps) {
  function goToPreviousMonth() {
    if (month === 1) onChange(year - 1, 12);
    else onChange(year, month - 1);
  }

  function goToNextMonth() {
    if (month === 12) onChange(year + 1, 1);
    else onChange(year, month + 1);
  }

  function goToToday() {
    const now = new Date();
    onChange(now.getFullYear(), now.getMonth() + 1);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" onClick={goToPreviousMonth} aria-label="Previous month">
        &larr;
      </Button>
      <h2 className="min-w-32 text-center text-lg font-semibold text-zinc-900 sm:min-w-40 dark:text-zinc-50">
        {MONTH_NAMES[month - 1]} {year}
      </h2>
      <Button variant="secondary" onClick={goToNextMonth} aria-label="Next month">
        &rarr;
      </Button>
      <Button variant="ghost" onClick={goToToday}>
        Today
      </Button>
    </div>
  );
}
