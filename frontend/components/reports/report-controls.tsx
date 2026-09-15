"use client";

import { DateRangeSelector } from "@/components/analytics/date-range-selector";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { AnalyticsRange } from "@/lib/analytics";
import type { ReportType } from "@/lib/reports";

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

const RANGE_BASED_TYPES: ReportType[] = ["category", "income", "expense", "savings"];

interface ReportControlsProps {
  reportType: ReportType;
  year: number;
  month: number;
  onYearChange: (year: number) => void;
  onMonthChange: (month: number) => void;
  range: AnalyticsRange;
  customFrom: string;
  customTo: string;
  onRangeChange: (range: AnalyticsRange) => void;
  onCustomFromChange: (value: string) => void;
  onCustomToChange: (value: string) => void;
}

export function ReportControls({
  reportType,
  year,
  month,
  onYearChange,
  onMonthChange,
  range,
  customFrom,
  customTo,
  onRangeChange,
  onCustomFromChange,
  onCustomToChange,
}: ReportControlsProps) {
  if (reportType === "monthly") {
    return (
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="report-month">Month</Label>
          <Select
            id="report-month"
            value={month}
            onChange={(e) => onMonthChange(Number(e.target.value))}
            className="w-40"
          >
            {MONTH_NAMES.map((name, i) => (
              <option key={name} value={i + 1}>
                {name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="report-year">Year</Label>
          <Input
            id="report-year"
            type="number"
            value={year}
            onChange={(e) => onYearChange(Number(e.target.value))}
            className="w-24"
          />
        </div>
      </div>
    );
  }

  if (reportType === "yearly") {
    return (
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="report-year-only">Year</Label>
        <Input
          id="report-year-only"
          type="number"
          value={year}
          onChange={(e) => onYearChange(Number(e.target.value))}
          className="w-24"
        />
      </div>
    );
  }

  if (RANGE_BASED_TYPES.includes(reportType)) {
    return (
      <DateRangeSelector
        range={range}
        customFrom={customFrom}
        customTo={customTo}
        onRangeChange={onRangeChange}
        onCustomFromChange={onCustomFromChange}
        onCustomToChange={onCustomToChange}
      />
    );
  }

  return null;
}
